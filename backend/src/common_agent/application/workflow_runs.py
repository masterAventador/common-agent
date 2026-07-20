from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Protocol
from uuid import UUID

from common_agent.application.workflow_contracts import (
    WorkflowExecutionUnavailable,
    WorkflowRunNotActive,
    WorkflowRunStopAccepted,
)
from common_agent.application.workflow_run_projection import WorkflowRunProjection
from common_agent.concurrency import KeyedLockPool
from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import (
    WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH,
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunTrigger,
)
from common_agent.observability import bind_observation_context, log_event
from common_agent.pagination import CursorPage, ListPageRequest
from common_agent.workflows.errors import WorkflowExecutionStopped
from common_agent.workflows.events import WorkflowEventBroker, WorkflowEventKind
from common_agent.workflows.execution import (
    WorkflowCompiler,
    WorkflowExecutionObserver,
    WorkflowExecutionStopToken,
)

_LOGGER = logging.getLogger("common_agent.workflows")


class WorkflowDirectory(Protocol):
    async def get(self, workflow_id: UUID) -> WorkflowDefinition: ...


@dataclass(slots=True)
class _ActiveWorkflowRun:
    stop: WorkflowExecutionStopToken
    task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class _WorkflowRunObserver(WorkflowExecutionObserver):
    projection: WorkflowRunProjection
    run_id: UUID

    async def node_started(self, node_id: str) -> None:
        await self.projection.node_started(self.run_id, node_id)

    async def node_completed(self, node_id: str) -> None:
        await self.projection.node_completed(self.run_id, node_id)


class WorkflowRunCoordinator:
    def __init__(
        self,
        directory: WorkflowDirectory,
        projection: WorkflowRunProjection,
        locks: KeyedLockPool[UUID],
        *,
        compiler: WorkflowCompiler | None,
        events: WorkflowEventBroker | None,
    ) -> None:
        self._directory = directory
        self._projection = projection
        self._locks = locks
        self._compiler = compiler
        self._events = events
        self._active: dict[UUID, _ActiveWorkflowRun] = {}
        self._closed = False

    async def get(self, run_id: UUID) -> WorkflowRun:
        return await self._run_projection.get(run_id)

    async def list_for_conversation(self, conversation_id: UUID) -> tuple[WorkflowRun, ...]:
        return await self._run_projection.list_for_conversation(conversation_id)

    async def page_for_conversation(
        self,
        conversation_id: UUID,
        page: ListPageRequest,
    ) -> CursorPage[WorkflowRun]:
        return await self._run_projection.page_for_conversation(conversation_id, page)

    async def start(
        self,
        workflow_id: UUID,
        *,
        run_id: UUID,
        input: str,
        trigger: WorkflowRunTrigger,
        origin: WorkflowRunOrigin | None,
    ) -> WorkflowRun:
        self.ensure_available()
        async with self._locks.hold(run_id):
            workflow = await self._directory.get(workflow_id)
            pending = WorkflowRun.create(
                workflow_id=workflow.id,
                trigger=trigger,
                input=input,
                origin=origin,
                run_id=run_id,
            )
            await self._run_projection.create(pending)
            running = await self._run_projection.mark_running(pending)
            stop = WorkflowExecutionStopToken()
            active = _ActiveWorkflowRun(stop=stop)
            self._active[run_id] = active
            await self._event_broker.publish(run=running, kind=WorkflowEventKind.RUN_STARTED)
            active.task = asyncio.create_task(
                self._execute(workflow, running, stop),
                name=f"workflow-{workflow.id}-run-{run_id}",
            )
            return running

    async def stop(self, run_id: UUID) -> WorkflowRunStopAccepted:
        async with self._locks.hold(run_id):
            run = await self.get(run_id)
            active = self._active.get(run_id)
            if run.is_terminal or active is None:
                raise WorkflowRunNotActive
            active.stop.request_stop()
            return WorkflowRunStopAccepted(run_id=run_id)

    async def wait(self, run_id: UUID) -> WorkflowRun:
        active = self._active.get(run_id)
        if active is None or active.task is None:
            return await self.get(run_id)
        await asyncio.shield(active.task)
        return await self.get(run_id)

    async def recover_interrupted(self) -> int:
        self.ensure_available()
        return await self._run_projection.recover_interrupted()

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        active_runs = tuple(self._active.values())
        for active in active_runs:
            active.stop.request_stop()
        tasks = tuple(active.task for active in active_runs if active.task is not None)
        if not tasks:
            return
        _, pending = await asyncio.wait(tasks, timeout=10)
        for task in pending:
            task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

    def ensure_available(self) -> None:
        if self._closed or self._compiler is None or self._events is None:
            raise WorkflowExecutionUnavailable

    async def _execute(
        self,
        workflow: WorkflowDefinition,
        run: WorkflowRun,
        stop: WorkflowExecutionStopToken,
    ) -> None:
        started_at = monotonic()
        outcome_status = "failed"
        outcome_error: str | None = "workflow_execution_failed"
        origin = run.origin
        with bind_observation_context(
            conversation_id=origin.conversation_id if origin is not None else None,
            message_id=origin.assistant_message_id if origin is not None else None,
            workflow_id=workflow.id,
            run_id=run.id,
        ):
            log_event(_LOGGER, "workflow.run.started", status="running")
            try:
                result = await self._workflow_compiler.compile(workflow).invoke(
                    run.input,
                    observer=_WorkflowRunObserver(self._run_projection, run.id),
                    stop=stop,
                )
                await self._run_projection.complete(run.id, result)
                outcome_status = "completed"
                outcome_error = None
            except WorkflowExecutionStopped:
                outcome_status = "stopped"
                outcome_error = None
                await self._run_projection.stop(run.id)
            except asyncio.CancelledError:
                outcome_status = "stopped"
                outcome_error = None
                stop.request_stop()
                await self._run_projection.stop(run.id)
                raise
            except Exception as error:
                outcome_error = _safe_run_error_code(error)
                await self._run_projection.fail(run.id, outcome_error)
            finally:
                log_event(
                    _LOGGER,
                    "workflow.run.finished",
                    level=(logging.ERROR if outcome_status == "failed" else logging.INFO),
                    status=outcome_status,
                    error_code=outcome_error,
                    duration_ms=max(0.0, (monotonic() - started_at) * 1000),
                )
                async with self._locks.hold(run.id):
                    self._active.pop(run.id, None)

    @property
    def _workflow_compiler(self) -> WorkflowCompiler:
        if self._compiler is None:
            raise WorkflowExecutionUnavailable
        return self._compiler

    @property
    def _event_broker(self) -> WorkflowEventBroker:
        if self._events is None:
            raise WorkflowExecutionUnavailable
        return self._events

    @property
    def _run_projection(self) -> WorkflowRunProjection:
        return self._projection


def _safe_run_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if not isinstance(code, str):
        return "workflow_execution_failed"
    normalized = code.strip()
    if not normalized or len(normalized) > WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH:
        return "workflow_execution_failed"
    return normalized


__all__ = ["WorkflowDirectory", "WorkflowRunCoordinator"]
