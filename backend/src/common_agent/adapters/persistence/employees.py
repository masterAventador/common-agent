from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    EmployeeRow,
    ModelConfigurationReferenceRow,
    ModelConfigurationRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.domain.employee import Employee
from common_agent.pagination import PageAnchor, PageSlice, canonical_uuid_search
from common_agent.ports.employees import EmployeeAlreadyExists, EmployeeRepository
from common_agent.tenancy.context import current_tenant


class SqlAlchemyEmployeeRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self._session = session
        self._tenant_id = str(tenant_id or current_tenant().tenant_id)

    async def list(self) -> tuple[Employee, ...]:
        result = await self._session.execute(
            _employee_statement()
            .where(EmployeeRow.tenant_id == self._tenant_id)
            .order_by(EmployeeRow.created_at, EmployeeRow.id)
        )
        return tuple(_to_domain(row, model_identifier) for row, model_identifier in result)

    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
    ) -> PageSlice[Employee]:
        statement = _employee_statement().where(EmployeeRow.tenant_id == self._tenant_id)
        if search:
            searched_id = canonical_uuid_search(search)
            statement = statement.where(
                EmployeeRow.id == searched_id
                if searched_id is not None
                else EmployeeRow.name.startswith(search, autoescape=True)
            )
        if after is not None:
            after_time = to_database_datetime(after.created_at)
            statement = statement.where(
                or_(
                    EmployeeRow.created_at < after_time,
                    and_(
                        EmployeeRow.created_at == after_time,
                        EmployeeRow.id < after.id,
                    ),
                )
            )
        rows = tuple(
            await self._session.execute(
                statement.order_by(
                    EmployeeRow.created_at.desc(),
                    EmployeeRow.id.desc(),
                ).limit(limit + 1)
            )
        )
        return PageSlice(
            items=tuple(
                _to_domain(row, model_identifier) for row, model_identifier in rows[:limit]
            ),
            has_more=len(rows) > limit,
        )

    async def get(self, employee_id: UUID) -> Employee | None:
        result = await self._session.execute(
            _employee_statement().where(
                EmployeeRow.id == str(employee_id),
                EmployeeRow.tenant_id == self._tenant_id,
            )
        )
        row = result.first()
        return None if row is None else _to_domain(row[0], row[1])

    async def add(self, employee: Employee) -> None:
        self._session.add(EmployeeRow(tenant_id=self._tenant_id, **_to_values(employee)))
        self._session.add(
            ModelConfigurationReferenceRow(
                tenant_id=self._tenant_id,
                model_configuration_id=str(employee.default_model_configuration_id),
                resource_type="employee",
                resource_id=str(employee.id),
                created_at=to_database_datetime(employee.created_at),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            raise EmployeeAlreadyExists from None

    async def update(self, employee: Employee) -> bool:
        try:
            result = cast(
                CursorResult[Any],
                await self._session.execute(
                    update(EmployeeRow)
                    .where(
                        EmployeeRow.id == str(employee.id),
                        EmployeeRow.tenant_id == self._tenant_id,
                    )
                    .values(**_to_values(employee))
                ),
            )
            if not result.rowcount:
                return False
            await self._session.execute(
                delete(ModelConfigurationReferenceRow).where(
                    ModelConfigurationReferenceRow.tenant_id == self._tenant_id,
                    ModelConfigurationReferenceRow.resource_type == "employee",
                    ModelConfigurationReferenceRow.resource_id == str(employee.id),
                )
            )
            self._session.add(
                ModelConfigurationReferenceRow(
                    tenant_id=self._tenant_id,
                    model_configuration_id=str(employee.default_model_configuration_id),
                    resource_type="employee",
                    resource_id=str(employee.id),
                    created_at=to_database_datetime(employee.updated_at),
                )
            )
            await self._session.flush()
        except IntegrityError:
            raise EmployeeAlreadyExists from None
        return True


class SqlAlchemyEmployeeUnitOfWork:
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._employees: EmployeeRepository | None = None

    @property
    def employees(self) -> EmployeeRepository:
        if self._employees is None:
            raise RuntimeError("数字员工事务尚未开始")
        return self._employees

    async def __aenter__(self) -> SqlAlchemyEmployeeUnitOfWork:
        if self._context is not None:
            raise RuntimeError("数字员工事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._employees = SqlAlchemyEmployeeRepository(session, self._tenant_id)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._context
        self._context = None
        self._session = None
        self._employees = None
        if context is None:
            raise RuntimeError("数字员工事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        session = self._session
        if session is None:
            raise RuntimeError("数字员工事务尚未开始")
        await session.commit()


class SqlAlchemyEmployeeUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyEmployeeUnitOfWork:
        return SqlAlchemyEmployeeUnitOfWork(self._database, self._tenant_id_provider())


def _to_values(employee: Employee) -> dict[str, object]:
    return {
        "id": str(employee.id),
        "name": employee.name,
        "description": employee.description,
        "system_prompt": employee.system_prompt,
        "default_model_configuration_id": str(employee.default_model_configuration_id),
        "knowledge_base_id": employee.knowledge_base_id,
        "allowed_workflow_ids": [str(workflow_id) for workflow_id in employee.allowed_workflow_ids],
        "created_at": to_database_datetime(employee.created_at),
        "updated_at": to_database_datetime(employee.updated_at),
    }


def _employee_statement() -> Any:
    return select(EmployeeRow, ModelConfigurationRow.model_identifier).join(
        ModelConfigurationRow,
        and_(
            ModelConfigurationRow.tenant_id == EmployeeRow.tenant_id,
            ModelConfigurationRow.id == EmployeeRow.default_model_configuration_id,
        ),
    )


def _to_domain(row: EmployeeRow, model_identifier: str) -> Employee:
    return Employee(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        system_prompt=row.system_prompt,
        default_model_configuration_id=UUID(row.default_model_configuration_id),
        default_model_identifier=model_identifier,
        knowledge_base_id=row.knowledge_base_id,
        allowed_workflow_ids=tuple(UUID(value) for value in row.allowed_workflow_ids),
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )
