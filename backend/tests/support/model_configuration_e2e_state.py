from __future__ import annotations

import argparse
import asyncio
import os
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ModelConfigurationReferenceRow,
    ModelConfigurationRow,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID


async def _set_reference(configuration_id: UUID, *, present: bool) -> None:
    database = Database(os.environ["COMMON_AGENT_DATABASE_URL"])
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                delete(ModelConfigurationReferenceRow).where(
                    ModelConfigurationReferenceRow.tenant_id == str(DEFAULT_TENANT_ID),
                    ModelConfigurationReferenceRow.model_configuration_id == str(configuration_id),
                    ModelConfigurationReferenceRow.resource_type == "employee",
                    ModelConfigurationReferenceRow.resource_id
                    == "model-configuration-e2e-reference",
                )
            )
            if present:
                session.add(
                    ModelConfigurationReferenceRow(
                        tenant_id=str(DEFAULT_TENANT_ID),
                        model_configuration_id=str(configuration_id),
                        resource_type="employee",
                        resource_id="model-configuration-e2e-reference",
                        created_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
            await session.commit()
    finally:
        await database.stop()


async def delete_model_configurations_named(database: Database, *names: str) -> int:
    async with database.session() as session:
        configuration_ids = tuple(
            await session.scalars(
                select(ModelConfigurationRow.id).where(
                    ModelConfigurationRow.tenant_id == str(DEFAULT_TENANT_ID),
                    ModelConfigurationRow.display_name.in_(names),
                )
            )
        )
        if not configuration_ids:
            return 0
        await session.execute(
            delete(ModelConfigurationReferenceRow).where(
                ModelConfigurationReferenceRow.tenant_id == str(DEFAULT_TENANT_ID),
                ModelConfigurationReferenceRow.model_configuration_id.in_(configuration_ids),
            )
        )
        await session.execute(
            delete(ModelConfigurationRow).where(
                ModelConfigurationRow.tenant_id == str(DEFAULT_TENANT_ID),
                ModelConfigurationRow.id.in_(configuration_ids),
            )
        )
        await session.commit()
        return len(configuration_ids)


async def delete_model_configurations_named_from_database_url(
    database_url: str,
    *names: str,
) -> int:
    database = Database(database_url)
    await database.start()
    try:
        return await delete_model_configurations_named(database, *names)
    finally:
        await database.stop()


async def _cleanup() -> None:
    model_name = os.environ["COMMON_AGENT_E2E_MODEL_NAME"]
    database = Database(os.environ["COMMON_AGENT_DATABASE_URL"])
    await database.start()
    try:
        await delete_model_configurations_named(database, model_name, f"{model_name}-已停用")
    finally:
        await database.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("add-reference", "remove-reference", "cleanup"))
    parser.add_argument("configuration_id", nargs="?")
    args = parser.parse_args()
    if args.action == "cleanup":
        asyncio.run(_cleanup())
        return
    if args.configuration_id is None:
        parser.error("configuration_id is required")
    configuration_id = UUID(args.configuration_id)
    asyncio.run(_set_reference(configuration_id, present=args.action == "add-reference"))


if __name__ == "__main__":
    main()
