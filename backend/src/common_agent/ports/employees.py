from __future__ import annotations

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
