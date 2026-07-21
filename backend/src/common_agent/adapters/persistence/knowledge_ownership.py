from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.dialects.mysql import insert as mysql_insert
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import RagFlowKnowledgeBaseOwnershipRow
from common_agent.adapters.persistence.timestamps import to_database_datetime


class SqlAlchemyKnowledgeOwnershipStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_ids(self, tenant_id: UUID) -> frozenset[str]:
        async with self._database.session() as session:
            values = await session.scalars(
                select(RagFlowKnowledgeBaseOwnershipRow.knowledge_base_id).where(
                    RagFlowKnowledgeBaseOwnershipRow.tenant_id == str(tenant_id)
                )
            )
            return frozenset(values)

    async def owns(self, tenant_id: UUID, knowledge_base_id: str) -> bool:
        async with self._database.session() as session:
            value = await session.scalar(
                select(RagFlowKnowledgeBaseOwnershipRow.knowledge_base_id).where(
                    RagFlowKnowledgeBaseOwnershipRow.tenant_id == str(tenant_id),
                    RagFlowKnowledgeBaseOwnershipRow.knowledge_base_id == knowledge_base_id,
                )
            )
            return value is not None

    async def claim(
        self,
        tenant_id: UUID,
        knowledge_base_id: str,
        *,
        now: datetime,
    ) -> bool:
        try:
            async with self._database.session() as session:
                session.add(
                    RagFlowKnowledgeBaseOwnershipRow(
                        tenant_id=str(tenant_id),
                        knowledge_base_id=knowledge_base_id,
                        created_at=to_database_datetime(now),
                    )
                )
                await session.commit()
            return True
        except IntegrityError:
            return False

    async def release(self, tenant_id: UUID, knowledge_base_id: str) -> None:
        async with self._database.session() as session:
            await session.execute(
                delete(RagFlowKnowledgeBaseOwnershipRow).where(
                    RagFlowKnowledgeBaseOwnershipRow.tenant_id == str(tenant_id),
                    RagFlowKnowledgeBaseOwnershipRow.knowledge_base_id == knowledge_base_id,
                )
            )
            await session.commit()

    async def claim_legacy(
        self,
        tenant_id: UUID,
        knowledge_base_ids: tuple[str, ...],
        *,
        now: datetime,
    ) -> None:
        if not knowledge_base_ids:
            return
        values = [
            {
                "tenant_id": str(tenant_id),
                "knowledge_base_id": knowledge_base_id,
                "created_at": to_database_datetime(now),
            }
            for knowledge_base_id in knowledge_base_ids
        ]
        async with self._database.session() as session:
            await session.execute(
                mysql_insert(RagFlowKnowledgeBaseOwnershipRow).values(values).prefix_with("IGNORE")
            )
            await session.commit()


__all__ = ["SqlAlchemyKnowledgeOwnershipStore"]
