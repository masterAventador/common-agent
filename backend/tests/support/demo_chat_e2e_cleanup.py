from __future__ import annotations

import asyncio
import os

from common_agent.adapters.persistence.database import Database
from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from tests.support.conversations import delete_conversations_for_employee_names
from tests.support.employees import delete_employees, delete_employees_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> None:
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        employee_name = _required("COMMON_AGENT_DEMO_E2E_EMPLOYEE_NAME")
        await delete_conversations_for_employee_names(database, employee_name)
        await delete_employees_named(database, employee_name)
        await delete_employees(database, DEFAULT_KNOWLEDGE_ASSISTANT_ID)
    finally:
        await database.stop()


def main() -> None:
    asyncio.run(_cleanup())
    print("已清理 Demo 聊天 E2E 会话、员工和固定 Seed")


if __name__ == "__main__":
    main()
