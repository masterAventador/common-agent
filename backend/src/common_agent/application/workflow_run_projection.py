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
from common_agent.domain.workflow_run import WorkflowRun
from common_agent.ports.workflows import WorkflowRunAlreadyExists, WorkflowUnitOfWorkFactory
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

    async def create(self, run: WorkflowRun) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                await unit_of_work.workflow_runs.add(run)
                await unit_of_work.commit()
        except WorkflowRunAlreadyExists:
            raise WorkflowRunConflict from None

    async def mark_running(self, run: WorkflowRun) -> WorkflowRun:
        running = run.start()
        await self._update(running)
        return running

    async def recover_interrupted(self) -> int:
        async with self._unit_of_work_factory() as unit_of_work:
            active_runs = await unit_of_work.workflow_runs.list_active()
            recovered = tuple(run.fail("workflow_run_interrupted") for run in active_runs)
            for run in recovered:
                if not await unit_of_work.workflow_runs.update(run):
                    raise WorkflowRunNotFound
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
            await self._update(completed)
        await self._event_broker.publish(run=completed, kind=WorkflowEventKind.RUN_COMPLETED)

    async def fail(self, run_id: UUID, error_code: str) -> None:
        async with self._locks.hold(run_id):
            current = await self.get(run_id)
            if current.is_terminal:
                return
            failed = current.fail(error_code)
            await self._update(failed)
        if failed.failed_node_id is not None:
            await self._event_broker.publish(
                run=failed,
                kind=WorkflowEventKind.NODE_FAILED,
                node_id=failed.failed_node_id,
            )
        await self._event_broker.publish(run=failed, kind=WorkflowEventKind.RUN_FAILED)

    async def stop(self, run_id: UUID) -> None:
        async with self._locks.hold(run_id):
            current = await self.get(run_id)
            if current.is_terminal:
                return
            stopped = current.stop()
            await self._update(stopped)
        await self._event_broker.publish(run=stopped, kind=WorkflowEventKind.RUN_STOPPED)

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
            await self._update(updated)
        await self._event_broker.publish(run=updated, kind=kind, node_id=node_id)

    async def _update(self, run: WorkflowRun) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            if not await unit_of_work.workflow_runs.update(run):
                raise WorkflowRunNotFound
            await unit_of_work.commit()

    @property
    def _event_broker(self) -> WorkflowEventBroker:
        if self._events is None:
            raise WorkflowExecutionUnavailable
        return self._events


__all__ = ["WorkflowRunProjection"]
