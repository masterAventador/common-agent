from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID


class KnowledgeOwnershipStore(Protocol):
    async def list_ids(self, tenant_id: UUID) -> frozenset[str]: ...

    async def owns(self, tenant_id: UUID, knowledge_base_id: str) -> bool: ...

    async def claim(
        self,
        tenant_id: UUID,
        knowledge_base_id: str,
        *,
        now: datetime,
    ) -> bool: ...

    async def release(self, tenant_id: UUID, knowledge_base_id: str) -> None: ...

    async def claim_legacy(
        self,
        tenant_id: UUID,
        knowledge_base_ids: tuple[str, ...],
        *,
        now: datetime,
    ) -> None: ...


__all__ = ["KnowledgeOwnershipStore"]
