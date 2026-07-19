from __future__ import annotations

from uuid import UUID

from common_agent.domain.workflow import (
    KnowledgeRetrievalNodeConfig,
    WorkflowConfiguration,
    WorkflowDefinition,
)
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.workflows import WorkflowUnitOfWorkFactory
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


class WorkflowService:
    def __init__(
        self,
        unit_of_work_factory: WorkflowUnitOfWorkFactory,
        knowledge_bases: KnowledgeBaseService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._knowledge_bases = knowledge_bases

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

    async def _ensure_valid(self, configuration: WorkflowConfiguration) -> None:
        issues = await self.validate(configuration)
        if issues:
            raise WorkflowGraphInvalid(issues)
