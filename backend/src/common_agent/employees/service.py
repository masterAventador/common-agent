from __future__ import annotations

from uuid import UUID

from common_agent.domain.employee import Employee, EmployeeConfiguration
from common_agent.knowledge.service import KnowledgeBaseService
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


class EmployeeService:
    def __init__(
        self,
        unit_of_work_factory: EmployeeUnitOfWorkFactory,
        knowledge_bases: KnowledgeBaseService,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._knowledge_bases = knowledge_bases

    async def list(self) -> tuple[Employee, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.employees.list()

    async def get(self, employee_id: UUID) -> Employee:
        async with self._unit_of_work_factory() as unit_of_work:
            employee = await unit_of_work.employees.get(employee_id)
        if employee is None:
            raise EmployeeNotFound
        return employee

    async def create(self, configuration: EmployeeConfiguration) -> Employee:
        await self._validate_knowledge_base(configuration.knowledge_base_id)
        employee = Employee.create(
            name=configuration.name,
            description=configuration.description,
            system_prompt=configuration.system_prompt,
            knowledge_base_id=configuration.knowledge_base_id,
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
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.employees.get(employee_id)
        if existing is not None:
            return existing

        await self._validate_knowledge_base(configuration.knowledge_base_id)
        candidate = Employee.create(
            employee_id=employee_id,
            name=configuration.name,
            description=configuration.description,
            system_prompt=configuration.system_prompt,
            knowledge_base_id=configuration.knowledge_base_id,
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
        await self.get(employee_id)
        await self._validate_knowledge_base(configuration.knowledge_base_id)
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.employees.get(employee_id)
            if current is None:
                raise EmployeeNotFound
            updated = current.reconfigure(
                name=configuration.name,
                description=configuration.description,
                system_prompt=configuration.system_prompt,
                knowledge_base_id=configuration.knowledge_base_id,
                allowed_workflow_ids=current.allowed_workflow_ids,
            )
            if not await unit_of_work.employees.update(updated):
                raise EmployeeNotFound
            await unit_of_work.commit()
        return updated

    async def _validate_knowledge_base(self, knowledge_base_id: str | None) -> None:
        if knowledge_base_id is not None:
            await self._knowledge_bases.get_knowledge_base(knowledge_base_id)
