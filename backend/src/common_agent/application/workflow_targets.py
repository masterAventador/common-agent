from __future__ import annotations

from uuid import UUID

from common_agent.domain.employee import Employee
from common_agent.domain.model_configuration import ModelConfiguration
from common_agent.model_configurations.service import ModelConfigurationService
from common_agent.ports.employees import EmployeeUnitOfWorkFactory


class WorkflowEmployeeTargetNotFound(Exception):
    pass


class WorkflowAiTargetDirectory:
    """Tenant-scoped read model shared by workflow validation and execution."""

    def __init__(
        self,
        employees: EmployeeUnitOfWorkFactory,
        model_configurations: ModelConfigurationService,
    ) -> None:
        self._employees = employees
        self._model_configurations = model_configurations

    async def get_employee(self, employee_id: UUID) -> Employee:
        async with self._employees() as unit_of_work:
            employee = await unit_of_work.employees.get(employee_id)
        if employee is None:
            raise WorkflowEmployeeTargetNotFound
        return employee

    async def get_model_configuration(
        self,
        model_configuration_id: UUID,
    ) -> ModelConfiguration:
        return await self._model_configurations.get(model_configuration_id)


__all__ = ["WorkflowAiTargetDirectory", "WorkflowEmployeeTargetNotFound"]
