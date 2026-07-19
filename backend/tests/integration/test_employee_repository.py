from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeRepository
from common_agent.domain.employee import Employee
from common_agent.ports.employees import EmployeeAlreadyExists
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


async def _delete_employees(database: Database, *employee_ids: object) -> None:
    async with database.session() as session:
        for employee_id in employee_ids:
            await session.execute(
                text("DELETE FROM employees WHERE id = :employee_id"),
                {"employee_id": str(employee_id)},
            )
        await session.commit()


def test_employee_repository_round_trip_survives_database_restart() -> None:
    employee = Employee.create(
        name=f"repository-{uuid4().hex}",
        description="通用会话角色",
        system_prompt="优先使用可靠上下文回答。",
        knowledge_base_id=f"ragflow-{uuid4().hex}",
        allowed_workflow_ids=[uuid4(), uuid4()],
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
                await _delete_employees(cleanup_database, employee.id)

    assert asyncio.run(exercise()) == employee


def test_employee_repository_lists_and_updates_without_owning_transactions() -> None:
    first = Employee.create(name=f"first-{uuid4().hex}", system_prompt="第一条通用指令")
    second = Employee.create(name=f"second-{uuid4().hex}", system_prompt="第二条通用指令")
    changed = second.reconfigure(
        name=second.name,
        description="已更新",
        system_prompt="更新后的通用指令",
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
                await _delete_employees(database, first.id, second.id)

    employees, missing = asyncio.run(exercise())
    assert first in employees
    assert changed in employees
    assert second not in employees
    assert missing is None


def test_employee_repository_rollback_does_not_persist_pending_employee() -> None:
    employee = Employee.create(name=f"rollback-{uuid4().hex}", system_prompt="通用指令")

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
    employee = Employee.create(name=f"duplicate-{uuid4().hex}", system_prompt="通用指令")

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
                await _delete_employees(database, employee.id)

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
