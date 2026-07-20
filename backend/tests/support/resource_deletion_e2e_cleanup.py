from __future__ import annotations

import asyncio
import os

from common_agent.adapters.persistence.database import Database
from tests.support.conversations import delete_conversations_for_employee_names
from tests.support.employees import delete_employees_named
from tests.support.ragflow import delete_datasets_named
from tests.support.workflows import delete_workflows_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> tuple[int, int]:
    employee_name = _required("COMMON_AGENT_E2E_DELETE_EMPLOYEE_NAME")
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        await delete_conversations_for_employee_names(database, employee_name)
        await delete_employees_named(database, employee_name)
        workflows_deleted = await delete_workflows_named(
            database,
            _required("COMMON_AGENT_E2E_DELETE_WORKFLOW_NAME"),
        )
    finally:
        await database.stop()

    knowledge_deleted = await delete_datasets_named(
        _required("RAGFLOW_BASE_URL"),
        _required("RAGFLOW_API_KEY"),
        _required("COMMON_AGENT_E2E_DELETE_KNOWLEDGE_NAME"),
    )
    return workflows_deleted, knowledge_deleted


def main() -> None:
    workflows_deleted, knowledge_deleted = asyncio.run(_cleanup())
    print(f"已清理删除 E2E 兜底数据: 工作流={workflows_deleted}, 知识库={knowledge_deleted}")


if __name__ == "__main__":
    main()
