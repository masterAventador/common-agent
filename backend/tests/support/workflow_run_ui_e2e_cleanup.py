from __future__ import annotations

import asyncio
import os

from common_agent.adapters.persistence.database import Database
from tests.support.ragflow import delete_datasets_named
from tests.support.workflows import delete_workflows_named


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> tuple[int, int]:
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        workflows_deleted = await delete_workflows_named(
            database,
            _required("COMMON_AGENT_E2E_WORKFLOW_RUN_NAME"),
            _required("COMMON_AGENT_E2E_WORKFLOW_STOP_NAME"),
            _required("COMMON_AGENT_E2E_WORKFLOW_FAILURE_NAME"),
        )
    finally:
        await database.stop()

    datasets_deleted = await delete_datasets_named(
        _required("RAGFLOW_BASE_URL"),
        _required("RAGFLOW_API_KEY"),
        _required("COMMON_AGENT_E2E_WORKFLOW_FAILURE_KNOWLEDGE_NAME"),
    )
    return workflows_deleted, datasets_deleted


def main() -> None:
    workflows_deleted, datasets_deleted = asyncio.run(_cleanup())
    print(f"已清理手动运行 UI E2E 数据: 工作流={workflows_deleted}, 知识库={datasets_deleted}")


if __name__ == "__main__":
    main()
