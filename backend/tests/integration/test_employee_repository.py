from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeRepository
from common_agent.domain.employee import Employee
from common_agent.pagination import PageAnchor
from common_agent.ports.employees import EmployeeAlreadyExists
from tests.support.employees import default_employee_model_fields, delete_employees
from tests.support.settings import TEST_DATABASE_URL


def _database_url() -> str:
    return os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)


@asynccontextmanager
async def _database() -> AsyncIterator[Database]:
    database = Database(_database_url())
    await database.start()
    try:
        yield database
    finally:
        await database.stop()


def test_employee_repository_round_trip_survives_database_restart() -> None:
    employee = Employee.create(
        name=f"repository-{uuid4().hex}",
        description="通用会话角色",
        system_prompt="优先使用可靠上下文回答。",
        knowledge_base_id=f"ragflow-{uuid4().hex}",
        allowed_workflow_ids=[uuid4(), uuid4()],
        **default_employee_model_fields(),
    )

    async def exercise() -> Employee | None:
        try:
            async with _database() as first, first.session() as session:
                repository = SqlAlchemyEmployeeRepository(session)
                await repository.add(employee)
                await session.commit()

            async with _database() as second, second.session() as session:
                repository = SqlAlchemyEmployeeRepository(session)
                return await repository.get(employee.id)
        finally:
            async with _database() as cleanup_database:
                await delete_employees(cleanup_database, employee.id)

    assert asyncio.run(exercise()) == employee


def test_employee_repository_lists_and_updates_without_owning_transactions() -> None:
    first = Employee.create(
        name=f"first-{uuid4().hex}",
        system_prompt="第一条通用指令",
        **default_employee_model_fields(),
    )
    second = Employee.create(
        name=f"second-{uuid4().hex}",
        system_prompt="第二条通用指令",
        **default_employee_model_fields(),
    )
    changed = second.reconfigure(
        name=second.name,
        description="已更新",
        system_prompt="更新后的通用指令",
        default_model_configuration_id=second.default_model_configuration_id,
        default_model_identifier=second.default_model_identifier,
        knowledge_base_id=f"ragflow-{uuid4().hex}",
        allowed_workflow_ids=[uuid4()],
    )

    async def exercise() -> tuple[tuple[Employee, ...], Employee | None]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    repository = SqlAlchemyEmployeeRepository(session)
                    await repository.add(first)
                    await repository.add(second)
                    await session.commit()

                async with database.session() as session:
                    repository = SqlAlchemyEmployeeRepository(session)
                    assert await repository.update(changed) is True
                    await session.commit()

                async with database.session() as session:
                    repository = SqlAlchemyEmployeeRepository(session)
                    employees = await repository.list()
                    missing = await repository.get(uuid4())
                    return employees, missing
            finally:
                await delete_employees(database, first.id, second.id)

    employees, missing = asyncio.run(exercise())
    assert first in employees
    assert changed in employees
    assert second not in employees
    assert missing is None


def test_employee_repository_keyset_page_survives_concurrent_insert_and_anchor_delete() -> None:
    created_at = datetime(2026, 7, 21, 1, tzinfo=UTC)
    employees = tuple(
        Employee.create(
            employee_id=UUID(int=index),
            name=f"page-needle-{index}",
            system_prompt="分页测试",
            now=created_at,
            **default_employee_model_fields(),
        )
        for index in range(1, 6)
    )
    newer = Employee.create(
        employee_id=UUID(int=6),
        name="page-needle-newer",
        system_prompt="分页测试",
        now=created_at + timedelta(seconds=1),
        **default_employee_model_fields(),
    )

    async def exercise() -> tuple[tuple[UUID, ...], tuple[UUID, ...], tuple[UUID, ...]]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    repository = SqlAlchemyEmployeeRepository(session)
                    for employee in employees:
                        await repository.add(employee)
                    await session.commit()

                async with database.session() as session:
                    first = await SqlAlchemyEmployeeRepository(session).page(
                        limit=2,
                        search="page-needle",
                        after=None,
                    )

                first_anchor = first.items[-1]
                await delete_employees(database, first_anchor.id)
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(newer)
                    await session.commit()

                async with database.session() as session:
                    repository = SqlAlchemyEmployeeRepository(session)
                    second = await repository.page(
                        limit=2,
                        search="page-needle",
                        after=PageAnchor(
                            created_at=first_anchor.created_at,
                            id=str(first_anchor.id),
                        ),
                    )
                    second_anchor = second.items[-1]
                    third = await repository.page(
                        limit=2,
                        search="page-needle",
                        after=PageAnchor(
                            created_at=second_anchor.created_at,
                            id=str(second_anchor.id),
                        ),
                    )
                return (
                    tuple(item.id for item in first.items),
                    tuple(item.id for item in second.items),
                    tuple(item.id for item in third.items),
                )
            finally:
                await delete_employees(database, *(employee.id for employee in employees), newer.id)

    first_ids, second_ids, third_ids = asyncio.run(exercise())
    assert first_ids == (UUID(int=5), UUID(int=4))
    assert second_ids == (UUID(int=3), UUID(int=2))
    assert third_ids == (UUID(int=1),)
    assert UUID(int=6) not in first_ids + second_ids + third_ids


def test_employee_repository_rollback_does_not_persist_pending_employee() -> None:
    employee = Employee.create(
        name=f"rollback-{uuid4().hex}",
        system_prompt="通用指令",
        **default_employee_model_fields(),
    )

    async def exercise() -> Employee | None:
        async with _database() as database:
            with pytest.raises(RuntimeError, match="force rollback"):
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    raise RuntimeError("force rollback")

            async with database.session() as session:
                return await SqlAlchemyEmployeeRepository(session).get(employee.id)

    assert asyncio.run(exercise()) is None


def test_employee_repository_maps_duplicate_identity_without_committing() -> None:
    employee = Employee.create(
        name=f"duplicate-{uuid4().hex}",
        system_prompt="通用指令",
        **default_employee_model_fields(),
    )

    async def exercise() -> Employee | None:
        async with _database() as database:
            try:
                async with database.session() as session:
                    repository = SqlAlchemyEmployeeRepository(session)
                    await repository.add(employee)
                    await session.commit()

                with pytest.raises(EmployeeAlreadyExists):
                    async with database.session() as session:
                        await SqlAlchemyEmployeeRepository(session).add(employee)

                async with database.session() as session:
                    return await SqlAlchemyEmployeeRepository(session).get(employee.id)
            finally:
                await delete_employees(database, employee.id)

    assert asyncio.run(exercise()) == employee


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("name", ""),
        ("name", " leading"),
        ("system_prompt", ""),
        ("knowledge_base_id", ""),
    ],
)
def test_employee_mysql_constraints_reject_invalid_direct_writes(column: str, value: str) -> None:
    employee_id = str(uuid4())

    async def exercise() -> None:
        async with _database() as database:
            values = {
                "id": employee_id,
                "name": "valid-name",
                "description": "",
                "system_prompt": "valid prompt",
                "knowledge_base_id": None,
                "allowed_workflow_ids": "[]",
            }
            values[column] = value
            with pytest.raises(DBAPIError):
                async with database.session() as session:
                    await session.execute(
                        text(
                            "INSERT INTO employees "
                            "(id, name, description, system_prompt, knowledge_base_id, "
                            "allowed_workflow_ids, created_at, updated_at) VALUES "
                            "(:id, :name, :description, :system_prompt, :knowledge_base_id, "
                            ":allowed_workflow_ids, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
                        ),
                        values,
                    )

    asyncio.run(exercise())
