from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.models import EmployeeRow
from common_agent.domain.employee import Employee
from common_agent.ports.employees import EmployeeAlreadyExists


class SqlAlchemyEmployeeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> tuple[Employee, ...]:
        result = await self._session.scalars(
            select(EmployeeRow).order_by(EmployeeRow.created_at, EmployeeRow.id)
        )
        return tuple(_to_domain(row) for row in result)

    async def get(self, employee_id: UUID) -> Employee | None:
        row = await self._session.get(EmployeeRow, str(employee_id))
        return None if row is None else _to_domain(row)

    async def add(self, employee: Employee) -> None:
        self._session.add(EmployeeRow(**_to_values(employee)))
        try:
            await self._session.flush()
        except IntegrityError:
            raise EmployeeAlreadyExists from None

    async def update(self, employee: Employee) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(EmployeeRow)
                .where(EmployeeRow.id == str(employee.id))
                .values(**_to_values(employee))
            ),
        )
        return bool(result.rowcount)


def _to_values(employee: Employee) -> dict[str, object]:
    return {
        "id": str(employee.id),
        "name": employee.name,
        "description": employee.description,
        "system_prompt": employee.system_prompt,
        "knowledge_base_id": employee.knowledge_base_id,
        "allowed_workflow_ids": [str(workflow_id) for workflow_id in employee.allowed_workflow_ids],
        "created_at": _without_timezone(employee.created_at),
        "updated_at": _without_timezone(employee.updated_at),
    }


def _to_domain(row: EmployeeRow) -> Employee:
    return Employee(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        system_prompt=row.system_prompt,
        knowledge_base_id=row.knowledge_base_id,
        allowed_workflow_ids=tuple(UUID(value) for value in row.allowed_workflow_ids),
        created_at=_with_utc(row.created_at),
        updated_at=_with_utc(row.updated_at),
    )


def _without_timezone(value: datetime) -> datetime:
    return value.astimezone(UTC).replace(tzinfo=None)


def _with_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC)
