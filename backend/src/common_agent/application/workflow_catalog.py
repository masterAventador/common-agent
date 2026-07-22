from __future__ import annotations

from typing import Protocol
from uuid import UUID

from common_agent.application.resource_locks import (
    ResourceMutationGuard,
    employee_resource,
    knowledge_base_resource,
    model_configuration_resource,
    workflow_resource,
)
from common_agent.application.workflow_contracts import WorkflowNotFound
from common_agent.application.workflow_targets import WorkflowEmployeeTargetNotFound
from common_agent.domain.employee import Employee
from common_agent.domain.model_configuration import ModelConfiguration
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EmployeeAiChatTarget,
    KnowledgeRetrievalNodeConfig,
    WorkflowConfiguration,
    WorkflowDefinition,
)
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.model_configurations.service import ModelConfigurationNotFound
from common_agent.pagination import (
    CursorPage,
    ListPageRequest,
    PageAnchor,
    decode_keyset_cursor,
    encode_keyset_cursor,
)
from common_agent.ports.workflows import WorkflowUnitOfWorkFactory
from common_agent.workflows.validator import (
    WorkflowGraphInvalid,
    WorkflowValidationCode,
    WorkflowValidationIssue,
    validate_workflow_graph,
)


class WorkflowCatalog:
    def __init__(
        self,
        unit_of_work_factory: WorkflowUnitOfWorkFactory,
        knowledge_bases: KnowledgeBaseService,
        *,
        ai_targets: WorkflowAiTargetDirectory | None = None,
        guard: ResourceMutationGuard | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._knowledge_bases = knowledge_bases
        self._ai_targets = ai_targets
        self._guard = guard or ResourceMutationGuard()

    async def list(self) -> tuple[WorkflowDefinition, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.workflows.list()

    async def page(self, page: ListPageRequest) -> CursorPage[WorkflowDefinition]:
        scope = "workflows"
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
            result = await unit_of_work.workflows.page(
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

    async def get(self, workflow_id: UUID) -> WorkflowDefinition:
        async with self._unit_of_work_factory() as unit_of_work:
            workflow = await unit_of_work.workflows.get(workflow_id)
        if workflow is None:
            raise WorkflowNotFound
        return workflow

    async def ensure_exist(self, workflow_ids: tuple[UUID, ...]) -> None:
        if not workflow_ids:
            return
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.workflows.existing_ids(workflow_ids)
        if existing != frozenset(workflow_ids):
            raise WorkflowNotFound

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
        issues.extend(await self._validate_ai_targets(configuration))
        return tuple(issues)

    async def _validate_ai_targets(
        self,
        configuration: WorkflowConfiguration,
    ) -> tuple[WorkflowValidationIssue, ...]:
        issues: list[WorkflowValidationIssue] = []
        employees: dict[UUID, Employee | None] = {}
        models: dict[UUID, ModelConfiguration | None] = {}
        for node in configuration.nodes:
            config = node.config
            if not isinstance(config, AiChatNodeConfig):
                continue
            if config.target is None:
                if self._ai_targets is None:
                    continue
                issues.append(
                    WorkflowValidationIssue(
                        code=WorkflowValidationCode.AI_TARGET_REQUIRED,
                        message="AI 对话节点必须选择数字员工或模型",
                        node_id=node.id,
                    )
                )
                continue
            if self._ai_targets is None:
                continue
            if isinstance(config.target, EmployeeAiChatTarget):
                employee_id = config.target.employee_id
                if employee_id not in employees:
                    try:
                        employees[employee_id] = await self._ai_targets.get_employee(employee_id)
                    except WorkflowEmployeeTargetNotFound:
                        employees[employee_id] = None
                employee = employees[employee_id]
                if employee is None:
                    issues.append(
                        WorkflowValidationIssue(
                            code=WorkflowValidationCode.EMPLOYEE_NOT_FOUND,
                            message="AI 对话节点引用的数字员工不存在",
                            node_id=node.id,
                        )
                    )
                    continue
                model_configuration_id = employee.default_model_configuration_id
            else:
                model_configuration_id = config.target.model_configuration_id
            if model_configuration_id not in models:
                try:
                    models[model_configuration_id] = await self._ai_targets.get_model_configuration(
                        model_configuration_id
                    )
                except ModelConfigurationNotFound:
                    models[model_configuration_id] = None
            model = models[model_configuration_id]
            if model is None:
                issues.append(
                    WorkflowValidationIssue(
                        code=WorkflowValidationCode.MODEL_CONFIGURATION_NOT_FOUND,
                        message="AI 对话节点引用的模型配置不存在",
                        node_id=node.id,
                    )
                )
                continue
            if not model.enabled:
                issues.append(
                    WorkflowValidationIssue(
                        code=WorkflowValidationCode.MODEL_CONFIGURATION_DISABLED,
                        message="AI 对话节点引用的模型配置已停用",
                        node_id=node.id,
                    )
                )
        return tuple(issues)

    async def create(self, configuration: WorkflowConfiguration) -> WorkflowDefinition:
        async with self._guard.hold(*_configuration_resources(configuration)):
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
        async with self._guard.hold(
            workflow_resource(workflow_id),
            *_configuration_resources(configuration),
        ):
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


def _knowledge_resources(configuration: WorkflowConfiguration) -> tuple[str, ...]:
    return tuple(
        knowledge_base_resource(node.config.knowledge_base_id)
        for node in configuration.nodes
        if isinstance(node.config, KnowledgeRetrievalNodeConfig)
    )


def _configuration_resources(configuration: WorkflowConfiguration) -> tuple[str, ...]:
    resources = list(_knowledge_resources(configuration))
    for node in configuration.nodes:
        config = node.config
        if not isinstance(config, AiChatNodeConfig) or config.target is None:
            continue
        if isinstance(config.target, EmployeeAiChatTarget):
            resources.append(employee_resource(config.target.employee_id))
        else:
            resources.append(model_configuration_resource(config.target.model_configuration_id))
    return tuple(resources)


class WorkflowAiTargetDirectory(Protocol):
    async def get_employee(self, employee_id: UUID) -> Employee: ...

    async def get_model_configuration(
        self,
        model_configuration_id: UUID,
    ) -> ModelConfiguration: ...


__all__ = ["WorkflowAiTargetDirectory", "WorkflowCatalog"]
