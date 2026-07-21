from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from common_agent.tenancy.models import TenantAccess


class TenantAlreadyExists(Exception):
    """Raised when a tenant name already exists inside an organization."""


class TenancyStore(Protocol):
    async def list_access(self, user_id: UUID) -> tuple[TenantAccess, ...]: ...

    async def find_access(self, user_id: UUID, tenant_id: UUID) -> TenantAccess | None: ...

    async def create_tenant(
        self,
        *,
        owner_user_id: UUID,
        organization_id: UUID,
        name: str,
        now: datetime,
    ) -> TenantAccess: ...


__all__ = ["TenancyStore", "TenantAlreadyExists"]
