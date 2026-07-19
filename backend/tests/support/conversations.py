from __future__ import annotations

from uuid import UUID

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database


async def delete_conversations(database: Database, *conversation_ids: UUID | str) -> None:
    async with database.session() as session:
        for conversation_id in conversation_ids:
            await session.execute(
                text(
                    "DELETE FROM message_citations WHERE message_id IN "
                    "(SELECT id FROM messages WHERE conversation_id = :conversation_id)"
                ),
                {"conversation_id": str(conversation_id)},
            )
            await session.execute(
                text("DELETE FROM messages WHERE conversation_id = :conversation_id"),
                {"conversation_id": str(conversation_id)},
            )
            await session.execute(
                text("DELETE FROM conversations WHERE id = :conversation_id"),
                {"conversation_id": str(conversation_id)},
            )
        await session.commit()
