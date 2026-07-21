from __future__ import annotations

from typing import TypedDict
from uuid import UUID

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from common_agent.model_configurations.defaults import (
    PLATFORM_DEFAULT_MODEL_IDENTIFIER,
    platform_default_model_configuration_id,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID

DEFAULT_TEST_MODEL_CONFIGURATION_ID = platform_default_model_configuration_id(DEFAULT_TENANT_ID)


class EmployeeModelFields(TypedDict):
    default_model_configuration_id: UUID
    default_model_identifier: str


def default_employee_model_fields() -> EmployeeModelFields:
    return {
        "default_model_configuration_id": DEFAULT_TEST_MODEL_CONFIGURATION_ID,
        "default_model_identifier": PLATFORM_DEFAULT_MODEL_IDENTIFIER,
    }


async def delete_employees(database: Database, *employee_ids: UUID | str) -> None:
    async with database.session() as session:
        for employee_id in employee_ids:
            await session.execute(
                text(
                    "DELETE FROM model_configuration_references "
                    "WHERE resource_type = 'employee' AND resource_id = :employee_id"
                ),
                {"employee_id": str(employee_id)},
            )
            await session.execute(
                text("DELETE FROM employees WHERE id = :employee_id"),
                {"employee_id": str(employee_id)},
            )
        await session.commit()


async def delete_employees_named(database: Database, *employee_names: str) -> None:
    async with database.session() as session:
        for employee_name in employee_names:
            await session.execute(
                text(
                    "DELETE refs FROM model_configuration_references refs "
                    "INNER JOIN employees ON employees.tenant_id = refs.tenant_id "
                    "AND employees.id = refs.resource_id "
                    "WHERE refs.resource_type = 'employee' "
                    "AND employees.name = :employee_name"
                ),
                {"employee_name": employee_name},
            )
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
