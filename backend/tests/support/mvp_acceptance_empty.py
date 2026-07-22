from __future__ import annotations

import asyncio
import os

import httpx
from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID

_MVP_KNOWLEDGE_PREFIX = "common-agent-q6-04-knowledge-"


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _assert_empty() -> None:
    database = Database(_required("COMMON_AGENT_DATABASE_URL"))
    await database.start()
    try:
        async with database.session() as session:
            employee_ids = set(
                (await session.execute(text("SELECT id FROM employees ORDER BY id"))).scalars()
            )
            if employee_ids - {str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)}:
                raise RuntimeError("MVP 验收前存在非 Seed 数字员工")
            for table in (
                "conversations",
                "messages",
                "message_citations",
                "workflows",
                "workflow_nodes",
                "workflow_edges",
                "workflow_runs",
            ):
                count = int(
                    (await session.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
                )
                if count != 0:
                    raise RuntimeError(f"MVP 验收前 {table} 不是空表")
    finally:
        await database.stop()

    async with httpx.AsyncClient(base_url=_required("RAGFLOW_BASE_URL"), timeout=60.0) as client:
        response = await client.get(
            "/api/v1/datasets",
            headers={"Authorization": f"Bearer {_required('RAGFLOW_API_KEY')}"},
            params={"page": 1, "page_size": 100, "orderby": "create_time", "desc": "true"},
        )
        response.raise_for_status()
        payload = response.json()
        if payload["code"] != 0:
            raise RuntimeError("MVP 验收前无法读取 RAGFlow 数据集")
        if any(
            isinstance(dataset, dict)
            and str(dataset.get("name", "")).startswith(_MVP_KNOWLEDGE_PREFIX)
            for dataset in payload["data"]
        ):
            raise RuntimeError("MVP 验收前 RAGFlow 仍存在同命名空间的测试知识库")


def main() -> None:
    asyncio.run(_assert_empty())
    print("MVP 验收隔离数据库与知识库测试命名空间门禁通过")


if __name__ == "__main__":
    main()
