from __future__ import annotations

import asyncio
import os

from common_agent.adapters.persistence.database import Database
from tests.support.conversations import delete_conversations_for_employee_names
from tests.support.employees import delete_employees_named
from tests.support.ragflow import delete_datasets_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> int:
    employee_name = _required("COMMON_AGENT_E2E_BATCH_EMPLOYEE_NAME")
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        await delete_conversations_for_employee_names(
            database,
            employee_name,
        )
        await delete_employees_named(database, employee_name)
    finally:
        await database.stop()
    knowledge_deleted = await delete_datasets_named(
        _required("RAGFLOW_BASE_URL"),
        _required("RAGFLOW_API_KEY"),
        _required("COMMON_AGENT_E2E_BATCH_KNOWLEDGE_NAME"),
    )
    return knowledge_deleted


def main() -> None:
    knowledge_deleted = asyncio.run(_cleanup())
    print(f"已清理知识库批量上传 E2E 数据: 知识库={knowledge_deleted}")


if __name__ == "__main__":
    main()
