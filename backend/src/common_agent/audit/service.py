from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from common_agent.audit.models import (
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditPage,
    AuditPolicy,
    AuditQuery,
)
from common_agent.audit.ports import AuditStore


class AuditCapacityExceeded(RuntimeError):
    """Raised when an append-only audit scope reaches its hard capacity limit."""


class AuditService:
    def __init__(self, store: AuditStore, policy: AuditPolicy | None = None) -> None:
        self._store = store
        self.policy = policy or AuditPolicy()

    async def record(self, entry: AuditEntry) -> AuditEvent:
        return await self._store.append(
            entry,
            retention_until=entry.occurred_at + timedelta(days=self.policy.retention_days),
            max_events_per_scope=self.policy.max_events_per_scope,
        )

    async def page(self, query: AuditQuery) -> AuditPage:
        return await self._store.page(query)

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity:
        return await self._store.verify(tenant_id)
