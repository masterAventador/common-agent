from __future__ import annotations

import asyncio
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from common_agent.domain.workflow import (
    KnowledgeRetrievalNodeConfig,
    WorkflowConfiguration,
    WorkflowDefinition,
)
from common_agent.domain.workflow_run import (
    WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH,
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunTrigger,
)
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.workflows import WorkflowRunAlreadyExists, WorkflowUnitOfWorkFactory
from common_agent.runtimes.base import RuntimeStopToken
from common_agent.workflows.compiler import WorkflowCompiler
from common_agent.workflows.errors import WorkflowExecutionStopped
from common_agent.workflows.events import WorkflowEventBroker, WorkflowEventKind
from common_agent.workflows.state import WorkflowExecutionObserver, WorkflowExecutionResult
from common_agent.workflows.validator import (
    WorkflowGraphInvalid,
    WorkflowValidationCode,
    WorkflowValidationIssue,
    validate_workflow_graph,
)


class WorkflowServiceError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __init__(self) -> None:
        super().__init__(self.message)


class WorkflowNotFound(WorkflowServiceError):
    code = "workflow_not_found"
    message = "工作流不存在"


class WorkflowRunNotFound(WorkflowServiceError):
    code = "workflow_run_not_found"
    message = "工作流运行不存在"


class WorkflowRunConflict(WorkflowServiceError):
    code = "workflow_run_conflict"
    message = "工作流运行请求已经提交"


class WorkflowRunNotActive(WorkflowServiceError):
    code = "workflow_run_not_active"
    message = "工作流运行当前不可停止"


class WorkflowExecutionUnavailable(WorkflowServiceError):
    code = "workflow_execution_unavailable"
    message = "工作流执行服务暂时不可用"
    retryable = True


class WorkflowRunResultInvalid(Exception):
    code = "workflow_run_result_invalid"


@dataclass(frozen=True, slots=True)
class WorkflowRunStopAccepted:
    run_id: UUID


@dataclass(slots=True)
class _ActiveWorkflowRun:
    stop: RuntimeStopToken
    task: asyncio.Task[None] | None = None


@dataclass(slots=True)
class _WorkflowRunObserver(WorkflowExecutionObserver):
    service: WorkflowService
    run_id: UUID

    async def node_started(self, node_id: str) -> None:
        await self.service._persist_node_started(self.run_id, node_id)

    async def node_completed(self, node_id: str) -> None:
        await self.service._persist_node_completed(self.run_id, node_id)


class WorkflowService:
    def __init__(
        self,
        unit_of_work_factory: WorkflowUnitOfWorkFactory,
        knowledge_bases: KnowledgeBaseService,
        *,
        compiler: WorkflowCompiler | None = None,
        events: WorkflowEventBroker | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._knowledge_bases = knowledge_bases
        self._compiler = compiler
        self._events = events
        self._run_locks: defaultdict[UUID, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._active_runs: dict[UUID, _ActiveWorkflowRun] = {}
        self._closed = False

    async def list(self) -> tuple[WorkflowDefinition, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.workflows.list()

    async def get(self, workflow_id: UUID) -> WorkflowDefinition:
        async with self._unit_of_work_factory() as unit_of_work:
            workflow = await unit_of_work.workflows.get(workflow_id)
        if workflow is None:
            raise WorkflowNotFound
        return workflow

    async def validate(
        self,
        configuration: WorkflowConfiguration,
    ) -> tuple[WorkflowValidationIssue, ...]:
        structural_issues = validate_workflow_graph(configuration.nodes, configuration.edges)
        if structural_issues:
            return structural_issues

        references: dict[str, list[str]] = {}
        for node in configuration.nodes:
            config = node.config
            if isinstance(config, KnowledgeRetrievalNodeConfig):
                references.setdefault(config.knowledge_base_id, []).append(node.id)

        issues: list[WorkflowValidationIssue] = []
        for knowledge_base_id, node_ids in references.items():
            try:
                await self._knowledge_bases.get_knowledge_base(knowledge_base_id)
            except KnowledgeBaseNotFound:
                issues.extend(
                    WorkflowValidationIssue(
                        code=WorkflowValidationCode.KNOWLEDGE_BASE_NOT_FOUND,
                        message="知识检索节点引用的知识库不存在或已失效",
                        node_id=node_id,
                    )
                    for node_id in node_ids
                )
        return tuple(issues)

    async def create(self, configuration: WorkflowConfiguration) -> WorkflowDefinition:
        await self._ensure_valid(configuration)
        workflow = WorkflowDefinition.create(
            name=configuration.name,
            description=configuration.description,
            nodes=configuration.nodes,
            edges=configuration.edges,
        )
        async with self._unit_of_work_factory() as unit_of_work:
            await unit_of_work.workflows.add(workflow)
            await unit_of_work.commit()
        return workflow

    async def update(
        self,
        workflow_id: UUID,
        configuration: WorkflowConfiguration,
    ) -> WorkflowDefinition:
        await self.get(workflow_id)
        await self._ensure_valid(configuration)
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.workflows.get(workflow_id)
            if current is None:
                raise WorkflowNotFound
            updated = current.reconfigure(
                name=configuration.name,
                description=configuration.description,
                nodes=configuration.nodes,
                edges=configuration.edges,
            )
            if not await unit_of_work.workflows.update(updated):
                raise WorkflowNotFound
            await unit_of_work.commit()
        return updated

    async def get_run(self, run_id: UUID) -> WorkflowRun:
        async with self._unit_of_work_factory() as unit_of_work:
            run = await unit_of_work.workflow_runs.get(run_id)
        if run is None:
            raise WorkflowRunNotFound
        return run

    async def list_runs_for_conversation(self, conversation_id: UUID) -> tuple[WorkflowRun, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.workflow_runs.list_for_conversation(conversation_id)

    async def start_run(
        self,
        workflow_id: UUID,
        *,
        run_id: UUID,
        input: str,
        trigger: WorkflowRunTrigger,
        origin: WorkflowRunOrigin | None = None,
    ) -> WorkflowRun:
        self._ensure_execution_available()
        async with self._run_locks[run_id]:
            workflow = await self.get(workflow_id)
            pending = WorkflowRun.create(
                workflow_id=workflow.id,
                trigger=trigger,
                input=input,
                origin=origin,
                run_id=run_id,
            )
            try:
                async with self._unit_of_work_factory() as unit_of_work:
                    await unit_of_work.workflow_runs.add(pending)
                    await unit_of_work.commit()
            except WorkflowRunAlreadyExists:
                raise WorkflowRunConflict from None

            running = pending.start()
            async with self._unit_of_work_factory() as unit_of_work:
                if not await unit_of_work.workflow_runs.update(running):
                    raise WorkflowRunNotFound
                await unit_of_work.commit()

            stop = RuntimeStopToken()
            active = _ActiveWorkflowRun(stop=stop)
            self._active_runs[run_id] = active
            await self._event_broker.publish(
                run=running,
                kind=WorkflowEventKind.RUN_STARTED,
            )
            active.task = asyncio.create_task(
                self._execute_run(workflow, running, stop),
                name=f"workflow-{workflow.id}-run-{run_id}",
            )
            return running

    async def stop_run(self, run_id: UUID) -> WorkflowRunStopAccepted:
        async with self._run_locks[run_id]:
            run = await self.get_run(run_id)
            active = self._active_runs.get(run_id)
            if run.is_terminal or active is None:
                raise WorkflowRunNotActive
            active.stop.request_stop()
            return WorkflowRunStopAccepted(run_id=run_id)

    async def wait_for_run(self, run_id: UUID) -> WorkflowRun:
        active = self._active_runs.get(run_id)
        if active is None or active.task is None:
            return await self.get_run(run_id)
        await asyncio.shield(active.task)
        return await self.get_run(run_id)

    async def recover_interrupted(self) -> int:
        self._ensure_execution_available()
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

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        active_runs = tuple(self._active_runs.values())
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

    async def _execute_run(
        self,
        workflow: WorkflowDefinition,
        run: WorkflowRun,
        stop: RuntimeStopToken,
    ) -> None:
        try:
            compiler = self._workflow_compiler
            result = await compiler.compile(workflow).invoke(
                run.input,
                observer=_WorkflowRunObserver(self, run.id),
                stop=stop,
            )
            await self._persist_completed(run.id, result)
        except WorkflowExecutionStopped:
            await self._persist_stopped(run.id)
        except asyncio.CancelledError:
            stop.request_stop()
            await self._persist_stopped(run.id)
            raise
        except Exception as error:
            await self._persist_failure(run.id, _safe_run_error_code(error))
        finally:
            async with self._run_locks[run.id]:
                self._active_runs.pop(run.id, None)

    async def _persist_node_started(self, run_id: UUID, node_id: str) -> None:
        await self._transition_and_publish(
            run_id,
            lambda run: run.start_node(node_id),
            kind=WorkflowEventKind.NODE_STARTED,
            node_id=node_id,
        )

    async def _persist_node_completed(self, run_id: UUID, node_id: str) -> None:
        await self._transition_and_publish(
            run_id,
            lambda run: run.complete_node(node_id),
            kind=WorkflowEventKind.NODE_COMPLETED,
            node_id=node_id,
        )

    async def _persist_completed(
        self,
        run_id: UUID,
        result: WorkflowExecutionResult,
    ) -> None:
        async with self._run_locks[run_id]:
            current = await self.get_run(run_id)
            if current.is_terminal:
                return
            if result.completed_node_ids != current.completed_node_ids or result.step_count != len(
                current.completed_node_ids
            ):
                raise WorkflowRunResultInvalid
            completed = current.complete(result.output)
            await self._update_run(completed)
        await self._event_broker.publish(
            run=completed,
            kind=WorkflowEventKind.RUN_COMPLETED,
        )

    async def _persist_failure(self, run_id: UUID, error_code: str) -> None:
        async with self._run_locks[run_id]:
            current = await self.get_run(run_id)
            if current.is_terminal:
                return
            failed = current.fail(error_code)
            await self._update_run(failed)
        if failed.failed_node_id is not None:
            await self._event_broker.publish(
                run=failed,
                kind=WorkflowEventKind.NODE_FAILED,
                node_id=failed.failed_node_id,
            )
        await self._event_broker.publish(run=failed, kind=WorkflowEventKind.RUN_FAILED)

    async def _persist_stopped(self, run_id: UUID) -> None:
        async with self._run_locks[run_id]:
            current = await self.get_run(run_id)
            if current.is_terminal:
                return
            stopped = current.stop()
            await self._update_run(stopped)
        await self._event_broker.publish(run=stopped, kind=WorkflowEventKind.RUN_STOPPED)

    async def _transition_and_publish(
        self,
        run_id: UUID,
        transition: Callable[[WorkflowRun], WorkflowRun],
        *,
        kind: WorkflowEventKind,
        node_id: str,
    ) -> None:
        async with self._run_locks[run_id]:
            current = await self.get_run(run_id)
            if current.is_terminal:
                raise WorkflowExecutionStopped
            updated = transition(current)
            await self._update_run(updated)
        await self._event_broker.publish(run=updated, kind=kind, node_id=node_id)

    async def _update_run(self, run: WorkflowRun) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            if not await unit_of_work.workflow_runs.update(run):
                raise WorkflowRunNotFound
            await unit_of_work.commit()

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

    def _ensure_execution_available(self) -> None:
        if self._closed or self._compiler is None or self._events is None:
            raise WorkflowExecutionUnavailable

    async def _ensure_valid(self, configuration: WorkflowConfiguration) -> None:
        issues = await self.validate(configuration)
        if issues:
            raise WorkflowGraphInvalid(issues)


def _safe_run_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    if not isinstance(code, str):
        return "workflow_execution_failed"
    normalized = code.strip()
    if not normalized or len(normalized) > WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH:
        return "workflow_execution_failed"
    return normalized
