from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database


async def delete_employees(database: Database, *employee_ids: UUID | str) -> None:
    async with database.session() as session:
        for employee_id in employee_ids:
            await session.execute(
                text("DELETE FROM employees WHERE id = :employee_id"),
                {"employee_id": str(employee_id)},
            )
        await session.commit()


async def delete_employees_named(database: Database, *employee_names: str) -> None:
    async with database.session() as session:
        for employee_name in employee_names:
            await session.execute(
                text("DELETE FROM employees WHERE name = :employee_name"),
                {"employee_name": employee_name},
            )
        await session.commit()


async def delete_employees_from_database_url(
    database_url: str,
    *employee_ids: UUID | str,
) -> None:
    database = Database(database_url)
    await database.start()
    try:
        await delete_employees(database, *employee_ids)
    finally:
        await database.stop()
