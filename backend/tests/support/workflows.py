from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database


async def delete_workflows(database: Database, *workflow_ids: UUID | str) -> None:
    async with database.session() as session:
        for workflow_id in workflow_ids:
            await session.execute(
                text("DELETE FROM workflows WHERE id = :workflow_id"),
                {"workflow_id": str(workflow_id)},
            )
        await session.commit()


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
