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


async def delete_conversations_for_employee_names(
    database: Database,
    *employee_names: str,
) -> None:
    conversation_ids: list[str] = []
    async with database.session() as session:
        for employee_name in employee_names:
            result = await session.execute(
                text(
                    "SELECT conversations.id FROM conversations "
                    "INNER JOIN employees ON employees.id = conversations.employee_id "
                    "WHERE employees.name = :employee_name"
                ),
                {"employee_name": employee_name},
            )
            conversation_ids.extend(result.scalars())
    await delete_conversations(database, *conversation_ids)
