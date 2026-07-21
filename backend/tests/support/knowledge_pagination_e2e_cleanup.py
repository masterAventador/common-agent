from __future__ import annotations

import asyncio
import os

from sqlalchemy import delete

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import RagFlowKnowledgeBaseOwnershipRow
from tests.support.ragflow import delete_datasets_prefixed


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


async def _cleanup() -> int:
    dataset_ids = await delete_datasets_prefixed(
        _required("RAGFLOW_BASE_URL"),
        _required("RAGFLOW_API_KEY"),
        _required("COMMON_AGENT_E2E_KNOWLEDGE_PAGE_PREFIX"),
    )
    if dataset_ids:
        database = Database(_required("COMMON_AGENT_DATABASE_URL"))
        await database.start()
        try:
            async with database.session() as session:
                await session.execute(
                    delete(RagFlowKnowledgeBaseOwnershipRow).where(
                        RagFlowKnowledgeBaseOwnershipRow.knowledge_base_id.in_(dataset_ids)
                    )
                )
                await session.commit()
        finally:
            await database.stop()
    return len(dataset_ids)


def main() -> None:
    print(f"已清理知识库大分页 E2E 数据: 知识库={asyncio.run(_cleanup())}")


if __name__ == "__main__":
    main()
