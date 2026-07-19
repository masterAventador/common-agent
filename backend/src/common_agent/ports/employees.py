from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.domain.employee import Employee


class EmployeeAlreadyExists(Exception):
    """Raised when an employee identity is already persisted."""


class EmployeeRepository(Protocol):
    async def list(self) -> tuple[Employee, ...]: ...

    async def get(self, employee_id: UUID) -> Employee | None: ...

    async def add(self, employee: Employee) -> None: ...

    async def update(self, employee: Employee) -> bool: ...


class EmployeeUnitOfWork(Protocol):
    @property
    def employees(self) -> EmployeeRepository: ...

    async def __aenter__(self) -> EmployeeUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class EmployeeUnitOfWorkFactory(Protocol):
    def __call__(self) -> EmployeeUnitOfWork: ...
