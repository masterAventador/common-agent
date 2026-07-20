from __future__ import annotations

from types import TracebackType
from uuid import UUID

from common_agent.application.workflow_service import WorkflowService
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    StartNodeConfig,
    WorkflowConfiguration,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowNodeType,
)
from common_agent.domain.workflow_run import WorkflowRun, WorkflowRunStatus
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.workflows import WorkflowAlreadyExists, WorkflowRunAlreadyExists
from tests.support.knowledge import KnowledgeProbe


class WorkflowRepositoryProbe:
    def __init__(self) -> None:
        self.values: dict[UUID, WorkflowDefinition] = {}

    async def list(self) -> tuple[WorkflowDefinition, ...]:
        return tuple(self.values.values())

    async def get(self, workflow_id: UUID) -> WorkflowDefinition | None:
        return self.values.get(workflow_id)

    async def add(self, workflow: WorkflowDefinition) -> None:
        if workflow.id in self.values:
            raise WorkflowAlreadyExists
        self.values[workflow.id] = workflow

    async def update(self, workflow: WorkflowDefinition) -> bool:
        if workflow.id not in self.values:
            return False
        self.values[workflow.id] = workflow
        return True


class WorkflowRunRepositoryProbe:
    def __init__(self) -> None:
        self.values: dict[UUID, WorkflowRun] = {}

    async def get(self, run_id: UUID) -> WorkflowRun | None:
        return self.values.get(run_id)

    async def list_active(self) -> tuple[WorkflowRun, ...]:
        return tuple(
            run
            for run in self.values.values()
            if run.status in {WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING}
        )

    async def list_for_conversation(self, conversation_id: UUID) -> tuple[WorkflowRun, ...]:
        return tuple(
            run
            for run in self.values.values()
            if run.origin is not None and run.origin.conversation_id == conversation_id
        )

    async def add(self, run: WorkflowRun) -> None:
        if run.id in self.values:
            raise WorkflowRunAlreadyExists
        self.values[run.id] = run

    async def update(self, run: WorkflowRun) -> bool:
        if run.id not in self.values:
            return False
        self.values[run.id] = run
        return True


class WorkflowUnitOfWorkProbe:
    def __init__(
        self,
        repository: WorkflowRepositoryProbe,
        run_repository: WorkflowRunRepositoryProbe,
    ) -> None:
        self.workflows = repository
        self.workflow_runs = run_repository
        self.commit_count = 0

    async def __aenter__(self) -> WorkflowUnitOfWorkProbe:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    async def commit(self) -> None:
        self.commit_count += 1


class WorkflowUnitOfWorkFactoryProbe:
    def __init__(self) -> None:
        self.repository = WorkflowRepositoryProbe()
        self.run_repository = WorkflowRunRepositoryProbe()
        self.units: list[WorkflowUnitOfWorkProbe] = []

    def __call__(self) -> WorkflowUnitOfWorkProbe:
        unit = WorkflowUnitOfWorkProbe(self.repository, self.run_repository)
        self.units.append(unit)
        return unit

    @property
    def commit_count(self) -> int:
        return sum(unit.commit_count for unit in self.units)


def workflow_service_with_probes() -> tuple[
    WorkflowService,
    WorkflowUnitOfWorkFactoryProbe,
    KnowledgeProbe,
]:
    units = WorkflowUnitOfWorkFactoryProbe()
    knowledge = KnowledgeProbe()
    return WorkflowService(units, KnowledgeBaseService(knowledge)), units, knowledge


def workflow_configuration(
    *,
    knowledge_base_id: str | None = None,
    include_end: bool = True,
) -> WorkflowConfiguration:
    processing = (
        WorkflowNode(
            id="retrieve",
            type=WorkflowNodeType.KNOWLEDGE_RETRIEVAL,
            position=WorkflowNodePosition(x=240, y=80),
            config=KnowledgeRetrievalNodeConfig(knowledge_base_id=knowledge_base_id),
        )
        if knowledge_base_id is not None
        else WorkflowNode(
            id="chat",
            type=WorkflowNodeType.AI_CHAT,
            position=WorkflowNodePosition(x=240, y=80),
            config=AiChatNodeConfig(prompt="根据工作流输入回答"),
        )
    )
    nodes = [
        WorkflowNode(
            id="start",
            type=WorkflowNodeType.START,
            position=WorkflowNodePosition(x=0, y=80),
            config=StartNodeConfig(),
        ),
        processing,
    ]
    edges = [WorkflowEdge(id="edge-1", source="start", target=processing.id)]
    if include_end:
        nodes.append(
            WorkflowNode(
                id="end",
                type=WorkflowNodeType.END,
                position=WorkflowNodePosition(x=480, y=80),
                config=EndNodeConfig(),
            )
        )
        edges.append(WorkflowEdge(id="edge-2", source=processing.id, target="end"))
    return WorkflowConfiguration(
        name="通用工作流",
        description="与业务无关的流程",
        nodes=tuple(nodes),
        edges=tuple(edges),
    )
