from __future__ import annotations

from types import TracebackType
from uuid import UUID

from common_agent.domain.employee import Employee, EmployeeConfiguration
from common_agent.employees.service import EmployeeService
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.employees import EmployeeAlreadyExists
from tests.support.knowledge import KnowledgeProbe


class WorkflowDirectoryProbe:
    def __init__(self) -> None:
        self.available_ids: set[UUID] = set()
        self.requested_ids: list[UUID] = []

    async def get(self, workflow_id: UUID) -> object:
        self.requested_ids.append(workflow_id)
        if workflow_id not in self.available_ids:
            from common_agent.application.workflow_service import WorkflowNotFound

            raise WorkflowNotFound
        return object()


class EmployeeRepositoryProbe:
    def __init__(self) -> None:
        self.values: dict[UUID, Employee] = {}

    async def list(self) -> tuple[Employee, ...]:
        return tuple(self.values.values())

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
]:
    units = EmployeeUnitOfWorkFactoryProbe()
    knowledge = KnowledgeProbe()
    workflows = WorkflowDirectoryProbe()
    return (
        EmployeeService(units, KnowledgeBaseService(knowledge), workflows=workflows),
        units,
        knowledge,
        workflows,
    )


def employee_configuration(
    knowledge_base_id: str | None = None,
    *,
    allowed_workflow_ids: tuple[UUID, ...] = (),
) -> EmployeeConfiguration:
    return EmployeeConfiguration(
        name="通用助理",
        description="与业务无关的会话角色",
        system_prompt="根据可用信息回答问题。",
        knowledge_base_id=knowledge_base_id,
        allowed_workflow_ids=allowed_workflow_ids,
    )
