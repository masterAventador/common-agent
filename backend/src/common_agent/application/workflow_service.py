from __future__ import annotations

from collections.abc import Callable
from uuid import UUID

from common_agent.application.resource_locks import (
    ResourceMutationGuard,
    workflow_resource,
)
from common_agent.application.workflow_catalog import WorkflowAiTargetDirectory, WorkflowCatalog
from common_agent.application.workflow_contracts import (
    WorkflowExecutionUnavailable,
    WorkflowNotFound,
    WorkflowRunConflict,
    WorkflowRunNotActive,
    WorkflowRunNotFound,
    WorkflowRunResultInvalid,
    WorkflowRunStopAccepted,
    WorkflowServiceError,
)
from common_agent.application.workflow_run_projection import WorkflowRunProjection
from common_agent.application.workflow_runs import WorkflowRunCoordinator
from common_agent.concurrency import KeyedLockPool
from common_agent.domain.workflow import WorkflowConfiguration, WorkflowDefinition
from common_agent.domain.workflow_run import (
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunTrigger,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.pagination import CursorPage, ListPageRequest
from common_agent.ports.workflows import WorkflowUnitOfWorkFactory
from common_agent.tasks import DurableTask, TaskExecutionContext, TaskQueue
from common_agent.workflows.events import WorkflowEventBroker
from common_agent.workflows.execution import WorkflowCompiler
from common_agent.workflows.validator import WorkflowValidationIssue


class WorkflowService:
    def __init__(
        self,
        unit_of_work_factory: WorkflowUnitOfWorkFactory,
        knowledge_bases: KnowledgeBaseService,
        *,
        ai_targets: WorkflowAiTargetDirectory | None = None,
        compiler: WorkflowCompiler | None = None,
        events: WorkflowEventBroker | None = None,
        guard: ResourceMutationGuard | None = None,
        tasks: TaskQueue | None = None,
        tenant_id_provider: Callable[[], UUID] | None = None,
        task_max_attempts: int = 3,
    ) -> None:
        self._guard = guard or ResourceMutationGuard()
        self._catalog = WorkflowCatalog(
            unit_of_work_factory,
            knowledge_bases,
            ai_targets=ai_targets,
            guard=self._guard,
        )
        locks: KeyedLockPool[UUID] = KeyedLockPool()
        projection = WorkflowRunProjection(unit_of_work_factory, events, locks)
        self._runs = WorkflowRunCoordinator(
            self._catalog,
            projection,
            locks,
            compiler=compiler,
            events=events,
            tasks=tasks,
            tenant_id_provider=tenant_id_provider,
            task_max_attempts=task_max_attempts,
        )

    async def list(self) -> tuple[WorkflowDefinition, ...]:
        return await self._catalog.list()

    async def page(self, page: ListPageRequest) -> CursorPage[WorkflowDefinition]:
        return await self._catalog.page(page)

    async def get(self, workflow_id: UUID) -> WorkflowDefinition:
        return await self._catalog.get(workflow_id)

    async def get_many(self, workflow_ids: tuple[UUID, ...]) -> tuple[WorkflowDefinition, ...]:
        return await self._catalog.get_many(workflow_ids)

    async def ensure_exist(self, workflow_ids: tuple[UUID, ...]) -> None:
        await self._catalog.ensure_exist(workflow_ids)

    async def validate(
        self,
        configuration: WorkflowConfiguration,
    ) -> tuple[WorkflowValidationIssue, ...]:
        return await self._catalog.validate(configuration)

    async def create(self, configuration: WorkflowConfiguration) -> WorkflowDefinition:
        return await self._catalog.create(configuration)

    async def update(
        self,
        workflow_id: UUID,
        configuration: WorkflowConfiguration,
    ) -> WorkflowDefinition:
        return await self._catalog.update(workflow_id, configuration)

    async def get_run(self, run_id: UUID) -> WorkflowRun:
        return await self._runs.get(run_id)

    async def list_runs_for_conversation(self, conversation_id: UUID) -> tuple[WorkflowRun, ...]:
        return await self._runs.list_for_conversation(conversation_id)

    async def page_runs_for_conversation(
        self,
        conversation_id: UUID,
        page: ListPageRequest,
    ) -> CursorPage[WorkflowRun]:
        return await self._runs.page_for_conversation(conversation_id, page)

    async def start_run(
        self,
        workflow_id: UUID,
        *,
        run_id: UUID,
        input: str,
        trigger: WorkflowRunTrigger,
        origin: WorkflowRunOrigin | None = None,
    ) -> WorkflowRun:
        async with self._guard.hold(workflow_resource(workflow_id)):
            return await self._runs.start(
                workflow_id,
                run_id=run_id,
                input=input,
                trigger=trigger,
                origin=origin,
            )

    async def stop_run(self, run_id: UUID) -> WorkflowRunStopAccepted:
        return await self._runs.stop(run_id)

    async def wait_for_run(self, run_id: UUID) -> WorkflowRun:
        return await self._runs.wait(run_id)

    async def recover_interrupted(self) -> int:
        return await self._runs.recover_interrupted()

    async def execute_workflow_task(
        self,
        task: DurableTask,
        context: TaskExecutionContext,
    ) -> None:
        await self._runs.execute_task(task, context)

    async def aclose(self) -> None:
        await self._runs.aclose()


__all__ = [
    "WorkflowExecutionUnavailable",
    "WorkflowNotFound",
    "WorkflowRunConflict",
    "WorkflowRunNotActive",
    "WorkflowRunNotFound",
    "WorkflowRunResultInvalid",
    "WorkflowRunStopAccepted",
    "WorkflowService",
    "WorkflowServiceError",
]
