from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID

from common_agent.tenancy.models import TenantAccess
from common_agent.tenancy.ports import TenancyStore, TenantAlreadyExists


class TenancyError(Exception):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TenancyService:
    def __init__(
        self,
        store: TenancyStore,
        *,
        clock: Callable[[], datetime] | None = None,
        tenant_initializer: Callable[[UUID], Awaitable[None]] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._tenant_initializer = tenant_initializer

    async def list_access(self, user_id: UUID) -> tuple[TenantAccess, ...]:
        return await self._store.list_access(user_id)

    async def resolve(
        self,
        user_id: UUID,
        tenant_id: UUID | None,
        *,
        write: bool = False,
        administer: bool = False,
    ) -> TenantAccess:
        if tenant_id is None:
            accesses = await self._store.list_access(user_id)
            if not accesses:
                raise TenancyError("tenant_access_denied")
            if len(accesses) != 1:
                raise TenancyError("tenant_selection_required")
            access = accesses[0]
        else:
            resolved = await self._store.find_access(user_id, tenant_id)
            if resolved is None:
                raise TenancyError("tenant_access_denied")
            access = resolved

        if administer and not access.role.can_administer:
            raise TenancyError("tenant_admin_forbidden")
        if write and not access.role.can_write:
            raise TenancyError("tenant_write_forbidden")
        return access

    async def create_tenant(
        self,
        *,
        owner_user_id: UUID,
        organization_id: UUID,
        name: str,
    ) -> TenantAccess:
        try:
            created = await self._store.create_tenant(
                owner_user_id=owner_user_id,
                organization_id=organization_id,
                name=name,
                now=self._clock(),
            )
            if self._tenant_initializer is not None:
                await self._tenant_initializer(created.tenant_id)
            return created
        except PermissionError:
            raise TenancyError("tenant_admin_forbidden") from None
        except TenantAlreadyExists:
            raise TenancyError("tenant_conflict") from None


__all__ = ["TenancyError", "TenancyService"]
