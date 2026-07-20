from __future__ import annotations

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database


async def delete_demo_knowledge_bases(
    database: Database,
    *knowledge_base_ids: str,
) -> None:
    async with database.session() as session:
        for knowledge_base_id in knowledge_base_ids:
            await session.execute(
                text("DELETE FROM demo_knowledge_bases WHERE id = :knowledge_base_id"),
                {"knowledge_base_id": knowledge_base_id},
            )
        await session.commit()


async def delete_demo_knowledge_bases_named(
    database: Database,
    *knowledge_base_names: str,
) -> None:
    async with database.session() as session:
        for knowledge_base_name in knowledge_base_names:
            await session.execute(
                text("DELETE FROM demo_knowledge_bases WHERE name = :knowledge_base_name"),
                {"knowledge_base_name": knowledge_base_name},
            )
        await session.commit()
