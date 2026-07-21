from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from uuid import UUID

from common_agent.concurrency import CoordinatedLockPool
from common_agent.tasks.models import DurableTask, TaskKind
from common_agent.tasks.ports import TaskQueue


class TaskRetryableError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = _error_code(code)
        super().__init__(self.code)


class TaskFatalError(RuntimeError):
    def __init__(self, code: str) -> None:
        self.code = _error_code(code)
        super().__init__(self.code)


class TaskCancelled(RuntimeError):
    code = "task_cancelled"


class TaskExecutionContext:
    def __init__(self, *, stop_requested: bool = False) -> None:
        self._stop = asyncio.Event()
        self._lease_lost = False
        if stop_requested:
            self._stop.set()

    @property
    def stop_requested(self) -> bool:
        return self._stop.is_set()

    @property
    def is_requested(self) -> bool:
        return self.stop_requested

    @property
    def lease_lost(self) -> bool:
        return self._lease_lost

    async def wait_for_stop(self) -> None:
        await self._stop.wait()

    async def wait(self) -> None:
        await self.wait_for_stop()

    def request_stop(self) -> None:
        self._stop.set()

    def _mark_lease_lost(self) -> None:
        self._lease_lost = True


TaskHandler = Callable[[DurableTask, TaskExecutionContext], Awaitable[None]]
Clock = Callable[[], datetime]


class TaskWorker:
    def __init__(
        self,
        queue: TaskQueue,
        *,
        handlers: Mapping[TaskKind, TaskHandler],
        worker_id: str,
        lease_for: timedelta = timedelta(seconds=30),
        base_retry_delay: timedelta = timedelta(seconds=1),
        maximum_retry_delay: timedelta = timedelta(minutes=5),
        heartbeat_interval: timedelta | None = None,
        execution_guard: CoordinatedLockPool | None = None,
        clock: Clock | None = None,
    ) -> None:
        if not worker_id.strip() or worker_id != worker_id.strip() or len(worker_id) > 128:
            raise ValueError("worker_id must be safe non-empty text")
        if not handlers:
            raise ValueError("handlers must not be empty")
        if lease_for < timedelta(seconds=3) or lease_for > timedelta(hours=1):
            raise ValueError("lease_for must be between 3 seconds and 1 hour")
        if base_retry_delay <= timedelta(0):
            raise ValueError("base_retry_delay must be positive")
        if maximum_retry_delay < base_retry_delay or maximum_retry_delay > timedelta(hours=24):
            raise ValueError("maximum_retry_delay must be bounded and not below base delay")
        active_heartbeat_interval = heartbeat_interval or lease_for / 3
        if active_heartbeat_interval <= timedelta(0) or active_heartbeat_interval * 2 >= lease_for:
            raise ValueError("heartbeat_interval must be positive and less than half the lease")
        self._queue = queue
        self._handlers = dict(handlers)
        self._worker_id = worker_id
        self._lease_for = lease_for
        self._base_retry_delay = base_retry_delay
        self._maximum_retry_delay = maximum_retry_delay
        self._heartbeat_interval = active_heartbeat_interval
        self._execution_guard = execution_guard
        self._clock = clock or (lambda: datetime.now(UTC))

    async def run_once(self) -> bool:
        task = await self._queue.claim(
            worker_id=self._worker_id,
            now=self._clock(),
            lease_for=self._lease_for,
            kinds=frozenset(self._handlers),
        )
        if task is None:
            return False
        if task.lease_token is None:
            raise RuntimeError("claimed task is missing lease token")
        lease_token = task.lease_token
        context = TaskExecutionContext(stop_requested=task.stop_requested)
        handler_task: asyncio.Future[None] | None = None
        heartbeat: asyncio.Task[None] | None = None
        try:
            handler = self._handlers.get(task.request.kind)
            if handler is None:
                raise TaskFatalError("task_handler_missing")
            handler_task = asyncio.ensure_future(
                self._execute_handler(task, context, lease_token, handler)
            )
            heartbeat = asyncio.create_task(
                self._heartbeat(task, context, lease_token, handler_task),
                name=f"task-heartbeat-{task.request.task_id}",
            )
            await handler_task
        except asyncio.CancelledError:
            if context.lease_lost:
                return True
            raise
        except TaskCancelled:
            await self._queue.cancel(
                task.request.task_id,
                worker_id=self._worker_id,
                lease_token=lease_token,
                now=self._clock(),
            )
        except TaskFatalError as error:
            await self._queue.fail(
                task.request.task_id,
                worker_id=self._worker_id,
                lease_token=lease_token,
                error_code=error.code,
                now=self._clock(),
            )
        except TaskRetryableError as error:
            await self._retry_or_fail(task, lease_token, error.code)
        except Exception:
            await self._retry_or_fail(task, lease_token, "task_execution_failed")
        else:
            await self._queue.complete(
                task.request.task_id,
                worker_id=self._worker_id,
                lease_token=lease_token,
                now=self._clock(),
            )
        finally:
            if handler_task is not None and not handler_task.done():
                handler_task.cancel()
                with suppress(asyncio.CancelledError):
                    await handler_task
            if heartbeat is not None:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
        return True

    async def _execute_handler(
        self,
        task: DurableTask,
        context: TaskExecutionContext,
        lease_token: UUID,
        handler: TaskHandler,
    ) -> None:
        guard = self._execution_guard
        if guard is None:
            await handler(task, context)
            return
        key = f"task:{task.request.tenant_id}:{task.request.task_id}"
        async with guard.hold(key):
            lease = await self._queue.heartbeat(
                task.request.task_id,
                worker_id=self._worker_id,
                lease_token=lease_token,
                now=self._clock(),
                lease_for=self._lease_for,
            )
            if not lease.owned:
                context._mark_lease_lost()
                raise asyncio.CancelledError
            if lease.stop_requested:
                context.request_stop()
            await handler(task, context)

    async def _retry_or_fail(
        self,
        task: DurableTask,
        lease_token: UUID,
        error_code: str,
    ) -> None:
        now = self._clock()
        if task.attempts >= task.max_attempts:
            await self._queue.fail(
                task.request.task_id,
                worker_id=self._worker_id,
                lease_token=lease_token,
                error_code=error_code,
                now=now,
            )
            return
        multiplier = 2 ** max(0, task.attempts - 1)
        delay = min(self._base_retry_delay * multiplier, self._maximum_retry_delay)
        await self._queue.retry(
            task.request.task_id,
            worker_id=self._worker_id,
            lease_token=lease_token,
            error_code=error_code,
            available_at=now + delay,
            now=now,
        )

    async def _heartbeat(
        self,
        task: DurableTask,
        context: TaskExecutionContext,
        lease_token: UUID,
        handler_task: asyncio.Future[None],
    ) -> None:
        interval = self._heartbeat_interval.total_seconds()
        try:
            while True:
                await asyncio.sleep(interval)
                lease = await self._queue.heartbeat(
                    task.request.task_id,
                    worker_id=self._worker_id,
                    lease_token=lease_token,
                    now=self._clock(),
                    lease_for=self._lease_for,
                )
                if not lease.owned:
                    context._mark_lease_lost()
                    handler_task.cancel()
                    return
                if lease.stop_requested:
                    context.request_stop()
        except asyncio.CancelledError:
            raise
        except Exception:
            context._mark_lease_lost()
            handler_task.cancel()


class TaskWorkerPool:
    def __init__(
        self,
        workers: tuple[TaskWorker, ...],
        *,
        poll_interval_seconds: float = 0.25,
    ) -> None:
        if not workers:
            raise ValueError("workers must not be empty")
        if not 0 < poll_interval_seconds <= 10:
            raise ValueError("poll_interval_seconds must be between 0 and 10")
        self._workers = workers
        self._poll_interval_seconds = poll_interval_seconds

    async def run(self, stop: asyncio.Event) -> None:
        slots = tuple(
            asyncio.create_task(
                self._run_slot(worker, stop, index=index),
                name=f"durable-task-worker-{index}",
            )
            for index, worker in enumerate(self._workers)
        )
        stop_waiter = asyncio.create_task(stop.wait(), name="durable-task-worker-stop")
        try:
            done, _ = await asyncio.wait(
                (*slots, stop_waiter),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_waiter not in done:
                completed_slot = next(task for task in done if task in slots)
                await completed_slot
        finally:
            stop_waiter.cancel()
            for slot in slots:
                slot.cancel()
            await asyncio.gather(stop_waiter, *slots, return_exceptions=True)

    async def _run_slot(
        self,
        worker: TaskWorker,
        stop: asyncio.Event,
        *,
        index: int,
    ) -> None:
        del index
        while not stop.is_set():
            handled = await worker.run_once()
            if handled:
                continue
            with suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=self._poll_interval_seconds)


def _error_code(value: str) -> str:
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > 128
        or any(character in normalized for character in "\r\n\0")
    ):
        raise ValueError("task error code must be safe non-empty text")
    return normalized


__all__ = [
    "TaskCancelled",
    "TaskExecutionContext",
    "TaskFatalError",
    "TaskHandler",
    "TaskRetryableError",
    "TaskWorker",
    "TaskWorkerPool",
]
