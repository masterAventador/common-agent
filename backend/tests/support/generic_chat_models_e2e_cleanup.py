from __future__ import annotations

import asyncio
import os

from sqlalchemy import select

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import ConversationRow
from tests.support.conversations import delete_conversations
from tests.support.model_configuration_e2e_state import delete_model_configurations_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> tuple[int, int]:
    model_name = _required("COMMON_AGENT_E2E_GENERIC_CHAT_MODEL_NAME")
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        async with database.session() as session:
            conversation_ids = tuple(
                await session.scalars(
                    select(ConversationRow.id).where(
                        ConversationRow.source == "generic",
                        ConversationRow.title.startswith(model_name, autoescape=True),
                    )
                )
            )
        await delete_conversations(database, *conversation_ids)
        models = await delete_model_configurations_named(database, model_name)
        return len(conversation_ids), models
    finally:
        await database.stop()


def main() -> None:
    conversations, models = asyncio.run(_cleanup())
    print(f"已清理通用会话切模 E2E 数据: 会话={conversations},模型配置={models}")


if __name__ == "__main__":
    main()
