from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID, uuid4

import pytest

from common_agent.concurrency import CoordinatedLockPool
from common_agent.tasks import (
    ConversationReplyPayload,
    DurableTask,
    TaskBacklog,
    TaskCancelled,
    TaskEnqueueResult,
    TaskExecutionContext,
    TaskKind,
    TaskLeaseState,
    TaskRequest,
    TaskRetryableError,
    TaskState,
    TaskWorker,
    TaskWorkerPool,
)

NOW = datetime(2026, 7, 21, 7, 0, tzinfo=UTC)


class QueueProbe:
    def __init__(self, task: DurableTask) -> None:
        self.task = task
        self.claimed = False
        self.retried: list[tuple[UUID, str, datetime]] = []
        self.completed: list[UUID] = []
        self.cancelled: list[UUID] = []
        self.claimed_kinds: frozenset[TaskKind] | None = None

    async def enqueue(
        self,
        request: TaskRequest,
        *,
        max_attempts: int,
    ) -> TaskEnqueueResult:
        raise AssertionError("not expected")

    async def get(self, task_id: UUID) -> DurableTask:
        raise AssertionError("not expected")

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_for: timedelta,
        kinds: frozenset[TaskKind] | None = None,
    ) -> DurableTask | None:
        self.claimed_kinds = kinds
        if self.claimed:
            return None
        self.claimed = True
        return self.task

    async def heartbeat(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
        lease_for: timedelta,
    ) -> TaskLeaseState:
        return TaskLeaseState(owned=True, stop_requested=False)

    async def complete(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> bool:
        self.completed.append(task_id)
        return True

    async def retry(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        error_code: str,
        available_at: datetime,
        now: datetime,
    ) -> bool:
        self.retried.append((task_id, error_code, available_at))
        return True

    async def fail(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        error_code: str,
        now: datetime,
    ) -> bool:
        raise AssertionError("not expected")

    async def cancel(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> bool:
        self.cancelled.append(task_id)
        return True

    async def request_stop(self, task_id: UUID, *, now: datetime) -> DurableTask:
        raise AssertionError("not expected")

    async def request_stop_for_aggregate(
        self,
        *,
        tenant_id: UUID,
        kind: TaskKind,
        aggregate_id: UUID,
        now: datetime,
    ) -> DurableTask:
        raise AssertionError("not expected")

    async def backlog(self) -> TaskBacklog:
        raise AssertionError("not expected")



@contextmanager
def caplog_at_error() -> Iterator[list[logging.LogRecord]]:
    """采集 worker 日志器在 ERROR 级别输出的记录。"""
    logger = logging.getLogger("common_agent.tasks.worker")
    records: list[logging.LogRecord] = []

    class Collector(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = Collector(level=logging.ERROR)
    logger.addHandler(handler)
    previous = logger.level
    logger.setLevel(logging.ERROR)
    try:
        yield records
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)

def _task(*, attempts: int = 1, max_attempts: int = 3) -> DurableTask:
    conversation_id = uuid4()
    request = TaskRequest(
        task_id=uuid4(),
        tenant_id=uuid4(),
        kind=TaskKind.CONVERSATION_REPLY,
        idempotency_key=f"conversation:{conversation_id}:reply",
        aggregate_id=conversation_id,
        payload=ConversationReplyPayload(
            conversation_id=conversation_id,
            turn_id=uuid4(),
            user_message_id=uuid4(),
            assistant_message_id=uuid4(),
            retry=False,
        ),
        created_at=NOW,
    )
    return DurableTask(
        request=request,
        state=TaskState.RUNNING,
        attempts=attempts,
        max_attempts=max_attempts,
        available_at=NOW,
        lease_owner="worker-a",
        lease_token=uuid4(),
        lease_until=NOW + timedelta(seconds=30),
        stop_requested=False,
        error_code=None,
        updated_at=NOW,
    )


def test_worker_rejects_unsafe_or_inconsistent_runtime_configuration() -> None:
    task = _task()
    queue = QueueProbe(task)

    async def handle(claimed: DurableTask, context: TaskExecutionContext) -> None:
        del claimed, context

    handlers = {TaskKind.CONVERSATION_REPLY: handle}
    with pytest.raises(ValueError, match="worker_id"):
        TaskWorker(queue, handlers=handlers, worker_id=" ")
    with pytest.raises(ValueError, match="handlers"):
        TaskWorker(queue, handlers={}, worker_id="worker-a")
    with pytest.raises(ValueError, match="lease_for"):
        TaskWorker(
            queue,
            handlers=handlers,
            worker_id="worker-a",
            lease_for=timedelta(seconds=2),
        )
    with pytest.raises(ValueError, match="base_retry_delay"):
        TaskWorker(
            queue,
            handlers=handlers,
            worker_id="worker-a",
            base_retry_delay=timedelta(0),
        )
    with pytest.raises(ValueError, match="maximum_retry_delay"):
        TaskWorker(
            queue,
            handlers=handlers,
            worker_id="worker-a",
            base_retry_delay=timedelta(seconds=2),
            maximum_retry_delay=timedelta(seconds=1),
        )
    with pytest.raises(ValueError, match="heartbeat_interval"):
        TaskWorker(
            queue,
            handlers=handlers,
            worker_id="worker-a",
            lease_for=timedelta(seconds=4),
            heartbeat_interval=timedelta(seconds=2),
        )


def test_worker_completes_a_claimed_task_once() -> None:
    async def scenario() -> None:
        task = _task()
        queue = QueueProbe(task)
        handled: list[UUID] = []

        async def handle(claimed: DurableTask, context: TaskExecutionContext) -> None:
            assert context.stop_requested is False
            handled.append(claimed.request.task_id)

        worker = TaskWorker(
            queue,
            handlers={TaskKind.CONVERSATION_REPLY: handle},
            worker_id="worker-a",
            lease_for=timedelta(seconds=30),
            clock=lambda: NOW,
        )
        assert await worker.run_once() is True
        assert await worker.run_once() is False
        assert handled == [task.request.task_id]
        assert queue.claimed_kinds == frozenset({TaskKind.CONVERSATION_REPLY})
        assert queue.completed == [task.request.task_id]

    asyncio.run(scenario())


def test_worker_retries_with_bounded_exponential_backoff() -> None:
    async def scenario() -> None:
        task = _task(attempts=2, max_attempts=4)
        queue = QueueProbe(task)

        async def handle(claimed: DurableTask, context: TaskExecutionContext) -> None:
            raise TaskRetryableError("model_temporarily_unavailable")

        worker = TaskWorker(
            queue,
            handlers={TaskKind.CONVERSATION_REPLY: handle},
            worker_id="worker-a",
            lease_for=timedelta(seconds=30),
            base_retry_delay=timedelta(seconds=5),
            maximum_retry_delay=timedelta(seconds=60),
            clock=lambda: NOW,
        )
        assert await worker.run_once() is True
        assert queue.retried == [
            (task.request.task_id, "model_temporarily_unavailable", NOW + timedelta(seconds=10))
        ]

    asyncio.run(scenario())


def test_worker_logs_unexpected_handler_failure_before_retrying() -> None:
    """未预期异常必须留下堆栈, 否则任务失败后无从排查根因。"""

    async def scenario() -> None:
        task = _task(attempts=1, max_attempts=3)
        queue = QueueProbe(task)

        async def handle(claimed: DurableTask, context: TaskExecutionContext) -> None:
            raise RuntimeError("下游依赖返回了非预期结构")

        worker = TaskWorker(
            queue,
            handlers={TaskKind.CONVERSATION_REPLY: handle},
            worker_id="worker-a",
            lease_for=timedelta(seconds=30),
            base_retry_delay=timedelta(seconds=5),
            maximum_retry_delay=timedelta(seconds=60),
            clock=lambda: NOW,
        )
        with caplog_at_error() as records:
            assert await worker.run_once() is True

        assert queue.retried and queue.retried[0][1] == "task_execution_failed"
        assert any(
            "下游依赖返回了非预期结构" in (record.exc_text or "")
            or record.exc_info is not None
            for record in records
        ), "未预期异常必须带堆栈写入日志"

    asyncio.run(scenario())


def test_worker_persists_cancelled_state_and_context_implements_stop_signals() -> None:
    async def scenario() -> None:
        task = _task()
        queue = QueueProbe(task)

        async def handle(claimed: DurableTask, context: TaskExecutionContext) -> None:
            del claimed
            assert context.is_requested is False
            context.request_stop()
            await context.wait()
            raise TaskCancelled

        worker = TaskWorker(
            queue,
            handlers={TaskKind.CONVERSATION_REPLY: handle},
            worker_id="worker-a",
            lease_for=timedelta(seconds=30),
            clock=lambda: NOW,
        )

        assert await worker.run_once() is True
        assert queue.cancelled == [task.request.task_id]
        assert queue.completed == []

    asyncio.run(scenario())


def test_worker_cancels_stale_handler_without_writing_after_lease_loss() -> None:
    class LeaseLostQueue(QueueProbe):
        async def heartbeat(
            self,
            task_id: UUID,
            *,
            worker_id: str,
            lease_token: UUID,
            now: datetime,
            lease_for: timedelta,
        ) -> TaskLeaseState:
            return TaskLeaseState(owned=False, stop_requested=False)

    async def scenario() -> None:
        task = _task()
        queue = LeaseLostQueue(task)
        handler_cancelled = asyncio.Event()

        async def handle(claimed: DurableTask, context: TaskExecutionContext) -> None:
            del claimed, context
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                handler_cancelled.set()
                raise

        worker = TaskWorker(
            queue,
            handlers={TaskKind.CONVERSATION_REPLY: handle},
            worker_id="worker-a",
            lease_for=timedelta(seconds=3),
            heartbeat_interval=timedelta(milliseconds=10),
            clock=lambda: NOW,
        )

        assert await asyncio.wait_for(worker.run_once(), timeout=0.2) is True
        assert handler_cancelled.is_set()
        assert queue.completed == []
        assert queue.cancelled == []
        assert queue.retried == []

    asyncio.run(scenario())


def test_workers_serialize_same_task_across_process_lock_providers() -> None:
    class SharedProvider:
        def __init__(self) -> None:
            self.lock = asyncio.Lock()

        @asynccontextmanager
        async def hold(self, keys: tuple[str, ...]) -> AsyncIterator[None]:
            assert len(keys) == 1
            assert keys[0].startswith("task:")
            async with self.lock:
                yield

    async def scenario() -> None:
        task = _task()
        provider = SharedProvider()
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        second_started = asyncio.Event()

        async def first_handler(claimed: DurableTask, context: TaskExecutionContext) -> None:
            del claimed, context
            first_started.set()
            await release_first.wait()

        async def second_handler(claimed: DurableTask, context: TaskExecutionContext) -> None:
            del claimed, context
            second_started.set()

        first = TaskWorker(
            QueueProbe(task),
            handlers={TaskKind.CONVERSATION_REPLY: first_handler},
            worker_id="worker-a",
            execution_guard=CoordinatedLockPool(distributed=provider),
            clock=lambda: NOW,
        )
        second = TaskWorker(
            QueueProbe(task),
            handlers={TaskKind.CONVERSATION_REPLY: second_handler},
            worker_id="worker-b",
            execution_guard=CoordinatedLockPool(distributed=provider),
            clock=lambda: NOW,
        )
        first_task = asyncio.create_task(first.run_once())
        await first_started.wait()
        second_task = asyncio.create_task(second.run_once())
        await asyncio.sleep(0)
        assert second_started.is_set() is False
        release_first.set()
        first_result, second_result = await asyncio.gather(first_task, second_task)
        assert first_result is True
        assert second_result is True
        assert second_started.is_set()

    asyncio.run(scenario())


def test_worker_that_loses_lease_while_waiting_never_runs_business_handler() -> None:
    class SharedProvider:
        def __init__(self) -> None:
            self.lock = asyncio.Lock()

        @asynccontextmanager
        async def hold(self, keys: tuple[str, ...]) -> AsyncIterator[None]:
            del keys
            async with self.lock:
                yield

    class LeaseLostQueue(QueueProbe):
        async def heartbeat(
            self,
            task_id: UUID,
            *,
            worker_id: str,
            lease_token: UUID,
            now: datetime,
            lease_for: timedelta,
        ) -> TaskLeaseState:
            del task_id, worker_id, lease_token, now, lease_for
            return TaskLeaseState(owned=False, stop_requested=False)

    async def scenario() -> None:
        task = _task()
        provider = SharedProvider()
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        stale_handler_called = False

        async def first_handler(claimed: DurableTask, context: TaskExecutionContext) -> None:
            del claimed, context
            first_started.set()
            await release_first.wait()

        async def stale_handler(claimed: DurableTask, context: TaskExecutionContext) -> None:
            nonlocal stale_handler_called
            del claimed, context
            stale_handler_called = True

        first = TaskWorker(
            QueueProbe(task),
            handlers={TaskKind.CONVERSATION_REPLY: first_handler},
            worker_id="worker-current",
            execution_guard=CoordinatedLockPool(distributed=provider),
            lease_for=timedelta(seconds=3),
            heartbeat_interval=timedelta(seconds=1),
            clock=lambda: NOW,
        )
        stale = TaskWorker(
            LeaseLostQueue(task),
            handlers={TaskKind.CONVERSATION_REPLY: stale_handler},
            worker_id="worker-stale",
            execution_guard=CoordinatedLockPool(distributed=provider),
            lease_for=timedelta(seconds=3),
            heartbeat_interval=timedelta(milliseconds=10),
            clock=lambda: NOW,
        )
        first_task = asyncio.create_task(first.run_once())
        await first_started.wait()
        assert await asyncio.wait_for(stale.run_once(), timeout=0.2) is True
        assert stale_handler_called is False
        release_first.set()
        assert await first_task is True

    asyncio.run(scenario())


def test_worker_pool_polls_until_stopped_and_closes_every_slot() -> None:
    class WorkerProbe:
        def __init__(self, stop: asyncio.Event) -> None:
            self.stop = stop
            self.calls = 0

        async def run_once(self) -> bool:
            self.calls += 1
            await asyncio.sleep(0)
            if self.calls >= 2:
                self.stop.set()
            return self.calls == 1

    async def scenario() -> None:
        stop = asyncio.Event()
        probes = (WorkerProbe(stop), WorkerProbe(stop))
        pool = TaskWorkerPool(
            tuple(cast(TaskWorker, probe) for probe in probes),
            poll_interval_seconds=0.001,
        )

        await asyncio.wait_for(pool.run(stop), timeout=1)

        assert all(probe.calls >= 1 for probe in probes)

    asyncio.run(scenario())


def test_worker_pool_cancels_inflight_claims_on_process_shutdown() -> None:
    class BlockingWorker:
        def __init__(self) -> None:
            self.started = asyncio.Event()
            self.cancelled = False

        async def run_once(self) -> bool:
            self.started.set()
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.cancelled = True
                raise
            return True

    async def scenario() -> None:
        stop = asyncio.Event()
        probe = BlockingWorker()
        pool = TaskWorkerPool(
            (cast(TaskWorker, probe),),
            poll_interval_seconds=0.001,
        )
        running = asyncio.create_task(pool.run(stop))
        await asyncio.wait_for(probe.started.wait(), timeout=1)

        stop.set()
        await asyncio.wait_for(running, timeout=1)

        assert probe.cancelled is True

    asyncio.run(scenario())
