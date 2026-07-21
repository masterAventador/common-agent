from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    OrganizationRow,
    TenantMembershipRow,
    TenantRow,
)
from common_agent.adapters.persistence.timestamps import to_database_datetime
from common_agent.tenancy.models import TenantAccess, TenantRole
from common_agent.tenancy.ports import TenantAlreadyExists


class SqlAlchemyTenancyStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def list_access(self, user_id: UUID) -> tuple[TenantAccess, ...]:
        async with self._database.session() as session:
            rows = await session.execute(
                select(TenantMembershipRow, TenantRow, OrganizationRow)
                .join(TenantRow, TenantRow.id == TenantMembershipRow.tenant_id)
                .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
                .where(TenantMembershipRow.user_id == str(user_id))
                .order_by(OrganizationRow.name, TenantRow.name, TenantRow.id)
            )
            return tuple(_to_access(user_id, *row) for row in rows)

    async def list_tenant_ids(self) -> tuple[UUID, ...]:
        async with self._database.session() as session:
            values = await session.scalars(select(TenantRow.id).order_by(TenantRow.id))
            return tuple(UUID(value) for value in values)

    async def find_access(self, user_id: UUID, tenant_id: UUID) -> TenantAccess | None:
        async with self._database.session() as session:
            result = await session.execute(
                select(TenantMembershipRow, TenantRow, OrganizationRow)
                .join(TenantRow, TenantRow.id == TenantMembershipRow.tenant_id)
                .join(OrganizationRow, OrganizationRow.id == TenantRow.organization_id)
                .where(
                    TenantMembershipRow.user_id == str(user_id),
                    TenantMembershipRow.tenant_id == str(tenant_id),
                )
            )
            row = result.one_or_none()
            return None if row is None else _to_access(user_id, *row)

    async def create_tenant(
        self,
        *,
        owner_user_id: UUID,
        organization_id: UUID,
        name: str,
        now: datetime,
    ) -> TenantAccess:
        normalized_name = name.strip()
        if not 1 <= len(normalized_name) <= 100:
            raise ValueError("tenant_name")
        tenant_id = uuid4()
        database_now = to_database_datetime(now)
        try:
            async with self._database.session() as session:
                authorized = await session.scalar(
                    select(TenantMembershipRow.tenant_id)
                    .join(TenantRow, TenantRow.id == TenantMembershipRow.tenant_id)
                    .where(
                        TenantMembershipRow.user_id == str(owner_user_id),
                        TenantMembershipRow.role == TenantRole.OWNER.value,
                        TenantRow.organization_id == str(organization_id),
                    )
                    .limit(1)
                )
                if authorized is None:
                    raise PermissionError("tenant_admin_forbidden")
                tenant = TenantRow(
                    id=str(tenant_id),
                    organization_id=str(organization_id),
                    name=normalized_name,
                    created_at=database_now,
                )
                session.add(tenant)
                await session.flush()
                session.add(
                    TenantMembershipRow(
                        tenant_id=str(tenant_id),
                        user_id=str(owner_user_id),
                        role=TenantRole.OWNER.value,
                        created_at=database_now,
                    )
                )
                await session.commit()
        except IntegrityError as error:
            if _mysql_error_code(error) == 1062:
                raise TenantAlreadyExists from None
            raise
        access = await self.find_access(owner_user_id, tenant_id)
        if access is None:
            raise RuntimeError("租户创建后无法读取")
        return access


def _to_access(
    user_id: UUID,
    membership: TenantMembershipRow,
    tenant: TenantRow,
    organization: OrganizationRow,
) -> TenantAccess:
    return TenantAccess(
        tenant_id=UUID(tenant.id),
        user_id=user_id,
        role=TenantRole(membership.role),
        tenant_name=tenant.name,
        organization_id=UUID(organization.id),
        organization_name=organization.name,
    )


def _mysql_error_code(error: IntegrityError) -> int | None:
    arguments = getattr(error.orig, "args", ())
    return arguments[0] if arguments and isinstance(arguments[0], int) else None


__all__ = ["SqlAlchemyTenancyStore"]
