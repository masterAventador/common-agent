from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from common_agent.application.workflow_contracts import (
    WorkflowExecutionUnavailable,
    WorkflowRunConflict,
    WorkflowRunNotFound,
    WorkflowRunResultInvalid,
)
from common_agent.concurrency import KeyedLockPool
from common_agent.domain.workflow_run import WorkflowAiTargetSummary, WorkflowRun
from common_agent.pagination import (
    CursorPage,
    ListPageRequest,
    PageAnchor,
    decode_keyset_cursor,
    encode_keyset_cursor,
)
from common_agent.ports.workflows import WorkflowRunAlreadyExists, WorkflowUnitOfWorkFactory
from common_agent.tasks import TaskRequest
from common_agent.workflows.errors import WorkflowExecutionStopped
from common_agent.workflows.events import WorkflowEventBroker, WorkflowEventKind
from common_agent.workflows.execution import WorkflowExecutionResult


class WorkflowRunProjection:
    def __init__(
        self,
        unit_of_work_factory: WorkflowUnitOfWorkFactory,
        events: WorkflowEventBroker | None,
        locks: KeyedLockPool[UUID],
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._events = events
        self._locks = locks

    async def get(self, run_id: UUID) -> WorkflowRun:
        async with self._unit_of_work_factory() as unit_of_work:
            run = await unit_of_work.workflow_runs.get(run_id)
        if run is None:
            raise WorkflowRunNotFound
        return run

    async def list_for_conversation(self, conversation_id: UUID) -> tuple[WorkflowRun, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.workflow_runs.list_for_conversation(conversation_id)

    async def page_for_conversation(
        self,
        conversation_id: UUID,
        page: ListPageRequest,
    ) -> CursorPage[WorkflowRun]:
        scope = f"workflow-runs-{conversation_id}"
        after = (
            None
            if page.cursor is None
            else decode_keyset_cursor(
                page.cursor,
                scope=scope,
                search=page.search,
                limit=page.limit,
            )
        )
        async with self._unit_of_work_factory() as unit_of_work:
            result = await unit_of_work.workflow_runs.page_for_conversation(
                conversation_id,
                limit=page.limit,
                search=page.search,
                after=after,
            )
        next_cursor = None
        if result.has_more:
            last = result.items[-1]
            next_cursor = encode_keyset_cursor(
                scope=scope,
                search=page.search,
                limit=page.limit,
                anchor=PageAnchor(created_at=last.created_at, id=str(last.id)),
            )
        return CursorPage(items=result.items, next_cursor=next_cursor)

    async def create(
        self,
        run: WorkflowRun,
        *,
        task_request: TaskRequest | None = None,
        task_max_attempts: int = 3,
    ) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                await unit_of_work.workflow_runs.add(run)
                if task_request is not None:
                    if task_request.aggregate_id != run.id:
                        raise ValueError("workflow task does not match run")
                    await unit_of_work.tasks.enqueue(
                        task_request,
                        max_attempts=task_max_attempts,
                    )
                await unit_of_work.commit()
        except WorkflowRunAlreadyExists:
            raise WorkflowRunConflict from None

    async def mark_running(self, run: WorkflowRun) -> WorkflowRun:
        running = run.start()
        if not await self._update(running):
            raise WorkflowExecutionStopped
        return running

    async def restart_execution(self, run: WorkflowRun) -> WorkflowRun:
        restarted = run.restart_execution()
        if not await self._update(restarted):
            raise WorkflowExecutionStopped
        return restarted

    async def republish_terminal(self, run: WorkflowRun) -> None:
        if run.status.value == "completed":
            await self._event_broker.publish(run=run, kind=WorkflowEventKind.RUN_COMPLETED)
            return
        if run.status.value == "stopped":
            await self._event_broker.publish(run=run, kind=WorkflowEventKind.RUN_STOPPED)
            return
        if run.status.value != "failed":
            raise ValueError("only terminal workflow runs can be republished")
        if run.failed_node_id is not None:
            await self._event_broker.publish(
                run=run,
                kind=WorkflowEventKind.NODE_FAILED,
                node_id=run.failed_node_id,
            )
        await self._event_broker.publish(run=run, kind=WorkflowEventKind.RUN_FAILED)

    async def recover_interrupted(self) -> int:
        async with self._unit_of_work_factory() as unit_of_work:
            active_runs = await unit_of_work.workflow_runs.list_active()
            recovered = []
            for active in active_runs:
                candidate = active.fail("workflow_run_interrupted")
                if await unit_of_work.workflow_runs.update(candidate):
                    recovered.append(candidate)
            if recovered:
                await unit_of_work.commit()

        for run in recovered:
            if run.failed_node_id is not None:
                await self._event_broker.publish(
                    run=run,
                    kind=WorkflowEventKind.NODE_FAILED,
                    node_id=run.failed_node_id,
                )
            await self._event_broker.publish(run=run, kind=WorkflowEventKind.RUN_FAILED)
        return len(recovered)

    async def node_started(self, run_id: UUID, node_id: str) -> None:
        await self._transition_and_publish(
            run_id,
            lambda run: run.start_node(node_id),
            kind=WorkflowEventKind.NODE_STARTED,
            node_id=node_id,
        )

    async def node_completed(self, run_id: UUID, node_id: str) -> None:
        await self._transition_and_publish(
            run_id,
            lambda run: run.complete_node(node_id),
            kind=WorkflowEventKind.NODE_COMPLETED,
            node_id=node_id,
        )

    async def ai_target_resolved(
        self,
        run_id: UUID,
        summary: WorkflowAiTargetSummary,
    ) -> None:
        async with self._locks.hold(run_id):
            current = await self.get(run_id)
            if current.is_terminal:
                raise WorkflowExecutionStopped
            updated = current.record_ai_target(summary)
            if not await self._update(updated):
                raise WorkflowExecutionStopped

    async def complete(self, run_id: UUID, result: WorkflowExecutionResult) -> None:
        async with self._locks.hold(run_id):
            current = await self.get(run_id)
            if current.is_terminal:
                return
            if result.completed_node_ids != current.completed_node_ids or result.step_count != len(
                current.completed_node_ids
            ):
                raise WorkflowRunResultInvalid
            completed = current.complete(result.output)
            if not await self._update(completed):
                return
        await self._event_broker.publish(run=completed, kind=WorkflowEventKind.RUN_COMPLETED)

    async def fail(self, run_id: UUID, error_code: str) -> None:
        async with self._locks.hold(run_id):
            current = await self.get(run_id)
            if current.is_terminal:
                return
            failed = current.fail(error_code)
            if not await self._update(failed):
                return
        if failed.failed_node_id is not None:
            await self._event_broker.publish(
                run=failed,
                kind=WorkflowEventKind.NODE_FAILED,
                node_id=failed.failed_node_id,
            )
        await self._event_broker.publish(run=failed, kind=WorkflowEventKind.RUN_FAILED)

    async def stop(self, run_id: UUID) -> bool:
        async with self._locks.hold(run_id):
            current = await self.get(run_id)
            if current.is_terminal:
                return False
            stopped = current.stop()
            if not await self._update(stopped):
                return False
        await self._event_broker.publish(run=stopped, kind=WorkflowEventKind.RUN_STOPPED)
        return True

    async def _transition_and_publish(
        self,
        run_id: UUID,
        transition: Callable[[WorkflowRun], WorkflowRun],
        *,
        kind: WorkflowEventKind,
        node_id: str,
    ) -> None:
        async with self._locks.hold(run_id):
            current = await self.get(run_id)
            if current.is_terminal:
                raise WorkflowExecutionStopped
            updated = transition(current)
            if not await self._update(updated):
                raise WorkflowExecutionStopped
        await self._event_broker.publish(run=updated, kind=kind, node_id=node_id)

    async def _update(self, run: WorkflowRun) -> bool:
        async with self._unit_of_work_factory() as unit_of_work:
            if not await unit_of_work.workflow_runs.update(run):
                return False
            await unit_of_work.commit()
        return True

    @property
    def _event_broker(self) -> WorkflowEventBroker:
        if self._events is None:
            raise WorkflowExecutionUnavailable
        return self._events


__all__ = ["WorkflowRunProjection"]
