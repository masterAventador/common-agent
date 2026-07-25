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
from common_agent.domain.employee import Employee, EmployeeConfiguration
from common_agent.domain.model_configuration import ModelConfiguration
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.pagination import (
    CursorPage,
    ListPageRequest,
    PageAnchor,
    decode_keyset_cursor,
    encode_keyset_cursor,
)
from common_agent.ports.employees import EmployeeAlreadyExists, EmployeeUnitOfWorkFactory


class EmployeeServiceError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __init__(self) -> None:
        super().__init__(self.message)


class EmployeeNotFound(EmployeeServiceError):
    code = "employee_not_found"
    message = "数字员工不存在"


class EmployeeModelDisabled(EmployeeServiceError):
    code = "employee_model_disabled"
    message = "所选模型已停用，请选择当前可用的模型"  # noqa: RUF001


class WorkflowDirectory(Protocol):
    async def get(self, workflow_id: UUID) -> object: ...

    async def ensure_exist(self, workflow_ids: tuple[UUID, ...]) -> None: ...


class ModelConfigurationDirectory(Protocol):
    async def get(self, model_configuration_id: UUID) -> ModelConfiguration: ...


class EmployeeService:
    def __init__(
        self,
        unit_of_work_factory: EmployeeUnitOfWorkFactory,
        knowledge_bases: KnowledgeBaseService,
        *,
        workflows: WorkflowDirectory,
        model_configurations: ModelConfigurationDirectory,
        guard: ResourceMutationGuard | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._knowledge_bases = knowledge_bases
        self._workflows = workflows
        self._model_configurations = model_configurations
        self._guard = guard or ResourceMutationGuard()

    async def list(self) -> tuple[Employee, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.employees.list()

    async def page(self, page: ListPageRequest) -> CursorPage[Employee]:
        scope = "employees"
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
            result = await unit_of_work.employees.page(
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

    async def get(self, employee_id: UUID) -> Employee:
        async with self._unit_of_work_factory() as unit_of_work:
            employee = await unit_of_work.employees.get(employee_id)
        if employee is None:
            raise EmployeeNotFound
        return employee

    async def create(self, configuration: EmployeeConfiguration) -> Employee:
        async with self._guard.hold(*_configuration_resources(configuration)):
            await self._validate_knowledge_base(configuration.knowledge_base_id)
            await self._validate_workflows(configuration.allowed_workflow_ids)
            model_configuration = await self._validate_model_configuration(
                configuration.default_model_configuration_id
            )
            employee = Employee.create(
                name=configuration.name,
                description=configuration.description,
                system_prompt=configuration.system_prompt,
                default_model_configuration_id=model_configuration.id,
                default_model_identifier=model_configuration.model_identifier,
                knowledge_base_id=configuration.knowledge_base_id,
                allowed_workflow_ids=configuration.allowed_workflow_ids,
                deep_thinking_enabled=configuration.deep_thinking_enabled,
            )
            async with self._unit_of_work_factory() as unit_of_work:
                await unit_of_work.employees.add(employee)
                await unit_of_work.commit()
        return employee

    async def ensure(
        self,
        employee_id: UUID,
        configuration: EmployeeConfiguration,
    ) -> Employee:
        async with self._guard.hold(
            employee_resource(employee_id),
            *_configuration_resources(configuration),
        ):
            async with self._unit_of_work_factory() as unit_of_work:
                existing = await unit_of_work.employees.get(employee_id)
            if existing is not None:
                return existing

            await self._validate_knowledge_base(configuration.knowledge_base_id)
            await self._validate_workflows(configuration.allowed_workflow_ids)
            model_configuration = await self._validate_model_configuration(
                configuration.default_model_configuration_id
            )
            candidate = Employee.create(
                employee_id=employee_id,
                name=configuration.name,
                description=configuration.description,
                system_prompt=configuration.system_prompt,
                default_model_configuration_id=model_configuration.id,
                default_model_identifier=model_configuration.model_identifier,
                knowledge_base_id=configuration.knowledge_base_id,
                allowed_workflow_ids=configuration.allowed_workflow_ids,
                deep_thinking_enabled=configuration.deep_thinking_enabled,
            )
            try:
                async with self._unit_of_work_factory() as unit_of_work:
                    existing = await unit_of_work.employees.get(employee_id)
                    if existing is not None:
                        return existing
                    await unit_of_work.employees.add(candidate)
                    await unit_of_work.commit()
            except EmployeeAlreadyExists:
                return await self.get(employee_id)
            return candidate

    async def update(
        self,
        employee_id: UUID,
        configuration: EmployeeConfiguration,
    ) -> Employee:
        async with self._guard.hold(
            employee_resource(employee_id),
            *_configuration_resources(configuration),
        ):
            current = await self.get(employee_id)
            await self._validate_knowledge_base(configuration.knowledge_base_id)
            await self._validate_workflows(configuration.allowed_workflow_ids)
            model_configuration = await self._validate_model_configuration(
                configuration.default_model_configuration_id,
                existing_model_configuration_id=(current.default_model_configuration_id),
            )
            async with self._unit_of_work_factory() as unit_of_work:
                persisted = await unit_of_work.employees.get(employee_id)
                if persisted is None:
                    raise EmployeeNotFound
                updated = persisted.reconfigure(
                    name=configuration.name,
                    description=configuration.description,
                    system_prompt=configuration.system_prompt,
                    default_model_configuration_id=model_configuration.id,
                    default_model_identifier=model_configuration.model_identifier,
                    knowledge_base_id=configuration.knowledge_base_id,
                    allowed_workflow_ids=configuration.allowed_workflow_ids,
                    deep_thinking_enabled=configuration.deep_thinking_enabled,
                )
                if not await unit_of_work.employees.update(updated):
                    raise EmployeeNotFound
                await unit_of_work.commit()
        return updated

    async def _validate_knowledge_base(self, knowledge_base_id: str | None) -> None:
        if knowledge_base_id is not None:
            await self._knowledge_bases.get_knowledge_base(knowledge_base_id)

    async def _validate_workflows(self, workflow_ids: tuple[UUID, ...]) -> None:
        await self._workflows.ensure_exist(workflow_ids)

    async def _validate_model_configuration(
        self,
        model_configuration_id: UUID,
        *,
        existing_model_configuration_id: UUID | None = None,
    ) -> ModelConfiguration:
        model_configuration = await self._model_configurations.get(model_configuration_id)
        if (
            not model_configuration.enabled
            and model_configuration.id != existing_model_configuration_id
        ):
            raise EmployeeModelDisabled
        return model_configuration


def _configuration_resources(configuration: EmployeeConfiguration) -> tuple[str, ...]:
    resources = [
        model_configuration_resource(configuration.default_model_configuration_id),
        *(workflow_resource(value) for value in configuration.allowed_workflow_ids),
    ]
    if configuration.knowledge_base_id is not None:
        resources.append(knowledge_base_resource(configuration.knowledge_base_id))
    return tuple(resources)
