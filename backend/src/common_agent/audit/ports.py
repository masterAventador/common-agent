from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from common_agent.audit.models import (
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditPage,
    AuditQuery,
)


class AuditStore(Protocol):
    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent: ...

    async def page(self, query: AuditQuery) -> AuditPage: ...

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity: ...
