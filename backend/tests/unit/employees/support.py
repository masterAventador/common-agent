from __future__ import annotations

from types import TracebackType
from uuid import UUID

from common_agent.domain.employee import Employee, EmployeeConfiguration
from common_agent.domain.model_configuration import (
    ModelConfiguration,
    ModelConfigurationInput,
)
from common_agent.employees.service import EmployeeService
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.pagination import PageAnchor, PageSlice
from common_agent.ports.employees import EmployeeAlreadyExists
from tests.support.knowledge import KnowledgeProbe


class WorkflowDirectoryProbe:
    def __init__(self) -> None:
        self.available_ids: set[UUID] = set()
        self.requested_ids: list[UUID] = []
        self.request_batches: list[tuple[UUID, ...]] = []

    async def get(self, workflow_id: UUID) -> object:
        self.requested_ids.append(workflow_id)
        if workflow_id not in self.available_ids:
            from common_agent.application.workflow_service import WorkflowNotFound

            raise WorkflowNotFound
        return object()

    async def ensure_exist(self, workflow_ids: tuple[UUID, ...]) -> None:
        self.request_batches.append(workflow_ids)
        self.requested_ids.extend(workflow_ids)
        if any(workflow_id not in self.available_ids for workflow_id in workflow_ids):
            from common_agent.application.workflow_service import WorkflowNotFound

            raise WorkflowNotFound


DEFAULT_MODEL_CONFIGURATION_ID = UUID("5eb782ad-4fd6-40a6-8668-a9b729340ec9")


class ModelConfigurationDirectoryProbe:
    def __init__(self) -> None:
        default = ModelConfiguration.create(
            model_configuration_id=DEFAULT_MODEL_CONFIGURATION_ID,
            configuration=ModelConfigurationInput(
                display_name="Qwen Plus",
                model_identifier="qwen-plus",
                enabled=True,
            ),
        )
        self.values = {default.id: default}
        self.requested_ids: list[UUID] = []

    async def get(self, model_configuration_id: UUID) -> ModelConfiguration:
        self.requested_ids.append(model_configuration_id)
        configured = self.values.get(model_configuration_id)
        if configured is None:
            from common_agent.model_configurations.service import (
                ModelConfigurationNotFound,
            )

            raise ModelConfigurationNotFound
        return configured


class EmployeeRepositoryProbe:
    def __init__(self) -> None:
        self.values: dict[UUID, Employee] = {}

    async def list(self) -> tuple[Employee, ...]:
        return tuple(self.values.values())

    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
    ) -> PageSlice[Employee]:
        values = sorted(
            self.values.values(),
            key=lambda item: (item.created_at, str(item.id)),
            reverse=True,
        )
        if search:
            normalized = search.casefold()
            values = [
                item
                for item in values
                if normalized in f"{item.id} {item.name} {item.description}".casefold()
            ]
        if after is not None:
            values = [
                item
                for item in values
                if (item.created_at, str(item.id)) < (after.created_at, after.id)
            ]
        return PageSlice(items=tuple(values[:limit]), has_more=len(values) > limit)

    async def get(self, employee_id: UUID) -> Employee | None:
        return self.values.get(employee_id)

    async def add(self, employee: Employee) -> None:
        if employee.id in self.values:
            raise EmployeeAlreadyExists
        self.values[employee.id] = employee

    async def update(self, employee: Employee) -> bool:
        if employee.id not in self.values:
            return False
        self.values[employee.id] = employee
        return True


class EmployeeUnitOfWorkProbe:
    def __init__(self, repository: EmployeeRepositoryProbe) -> None:
        self.employees = repository
        self.commit_count = 0

    async def __aenter__(self) -> EmployeeUnitOfWorkProbe:
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


class EmployeeUnitOfWorkFactoryProbe:
    def __init__(self) -> None:
        self.repository = EmployeeRepositoryProbe()
        self.units: list[EmployeeUnitOfWorkProbe] = []

    def __call__(self) -> EmployeeUnitOfWorkProbe:
        unit = EmployeeUnitOfWorkProbe(self.repository)
        self.units.append(unit)
        return unit

    @property
    def commit_count(self) -> int:
        return sum(unit.commit_count for unit in self.units)


def employee_service_with_probes() -> tuple[
    EmployeeService,
    EmployeeUnitOfWorkFactoryProbe,
    KnowledgeProbe,
    WorkflowDirectoryProbe,
    ModelConfigurationDirectoryProbe,
]:
    units = EmployeeUnitOfWorkFactoryProbe()
    knowledge = KnowledgeProbe()
    workflows = WorkflowDirectoryProbe()
    models = ModelConfigurationDirectoryProbe()
    return (
        EmployeeService(
            units,
            KnowledgeBaseService(knowledge),
            workflows=workflows,
            model_configurations=models,
        ),
        units,
        knowledge,
        workflows,
        models,
    )


def employee_configuration(
    knowledge_base_id: str | None = None,
    *,
    allowed_workflow_ids: tuple[UUID, ...] = (),
    default_model_configuration_id: UUID = DEFAULT_MODEL_CONFIGURATION_ID,
) -> EmployeeConfiguration:
    return EmployeeConfiguration(
        name="通用助理",
        description="与业务无关的会话角色",
        system_prompt="根据可用信息回答问题。",
        default_model_configuration_id=default_model_configuration_id,
        knowledge_base_id=knowledge_base_id,
        allowed_workflow_ids=allowed_workflow_ids,
    )
