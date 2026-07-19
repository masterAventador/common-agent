from __future__ import annotations

import asyncio
import os

from common_agent.adapters.persistence.database import Database
from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from tests.support.employees import delete_employees, delete_employees_named
from tests.support.ragflow import delete_datasets_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> tuple[int, int]:
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        await delete_employees_named(database, _required("COMMON_AGENT_E2E_EMPLOYEE_NAME"))
        await delete_employees(database, DEFAULT_KNOWLEDGE_ASSISTANT_ID)
    finally:
        await database.stop()

    base_url = _required("RAGFLOW_BASE_URL")
    api_key = _required("RAGFLOW_API_KEY")
    knowledge_deleted = await delete_datasets_named(
        base_url,
        api_key,
        _required("COMMON_AGENT_E2E_KNOWLEDGE_NAME"),
    )
    employee_knowledge_deleted = await delete_datasets_named(
        base_url,
        api_key,
        _required("COMMON_AGENT_E2E_EMPLOYEE_KNOWLEDGE_NAME"),
    )
    return knowledge_deleted, employee_knowledge_deleted


def main() -> None:
    knowledge_deleted, employee_knowledge_deleted = asyncio.run(_cleanup())
    print(
        f"已清理平台 E2E 数据: 知识库={knowledge_deleted}, 员工知识库={employee_knowledge_deleted}"
    )


if __name__ == "__main__":
    main()
