from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TenantRole(StrEnum):
    OWNER = "owner"
    EDITOR = "editor"
    VIEWER = "viewer"

    @property
    def can_read(self) -> bool:
        return True

    @property
    def can_write(self) -> bool:
        return self in {TenantRole.OWNER, TenantRole.EDITOR}

    @property
    def can_administer(self) -> bool:
        return self is TenantRole.OWNER


@dataclass(frozen=True, slots=True)
class TenantAccess:
    tenant_id: UUID
    user_id: UUID
    role: TenantRole
    tenant_name: str = ""
    organization_id: UUID | None = None
    organization_name: str = ""


@dataclass(frozen=True, slots=True)
class Tenant:
    id: UUID
    organization_id: UUID
    name: str
    created_at: datetime


__all__ = ["Tenant", "TenantAccess", "TenantRole"]
