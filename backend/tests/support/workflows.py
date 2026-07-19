from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import CursorResult

from common_agent.adapters.persistence.database import Database


async def delete_workflows(database: Database, *workflow_ids: UUID | str) -> None:
    async with database.session() as session:
        for workflow_id in workflow_ids:
            await session.execute(
                text("DELETE FROM workflows WHERE id = :workflow_id"),
                {"workflow_id": str(workflow_id)},
            )
        await session.commit()


async def delete_workflows_named(database: Database, *workflow_names: str) -> int:
    deleted = 0
    async with database.session() as session:
        for workflow_name in workflow_names:
            result = cast(
                CursorResult[Any],
                await session.execute(
                    text("DELETE FROM workflows WHERE name = :workflow_name"),
                    {"workflow_name": workflow_name},
                ),
            )
            deleted += result.rowcount
        await session.commit()
    return deleted


async def delete_workflows_from_database_url(
    database_url: str,
    *workflow_ids: UUID | str,
) -> None:
    database = Database(database_url)
    await database.start()
    try:
        await delete_workflows(database, *workflow_ids)
    finally:
        await database.stop()
