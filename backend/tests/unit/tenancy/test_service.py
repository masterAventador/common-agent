from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

import pytest

from common_agent.model_configurations.seeds import (
    COMMON_MODEL_CONFIGURATION_SEEDS,
    seed_common_model_configurations_for_tenants,
)
from common_agent.tenancy.models import TenantAccess, TenantRole
from common_agent.tenancy.service import TenancyError, TenancyService
from tests.unit.model_configurations.support import (
    TenantAwareRepositoryHub,
    build_tenant_scoped_service,
)

USER_ID = UUID("20000000-0000-4000-8000-000000000001")
TENANT_A = UUID("10000000-0000-4000-8000-000000000001")
TENANT_B = UUID("10000000-0000-4000-8000-000000000002")

# 本用例只验证"新工作区拿到完整预置目录", 目录内容由 seeds 单独断言,
# 因此直接派生, 避免同一份清单在两处硬编码后漂移。
_SEED_IDENTIFIERS = {seed.model_identifier for seed in COMMON_MODEL_CONFIGURATION_SEEDS}


class FakeTenancyStore:
    def __init__(self, accesses: tuple[TenantAccess, ...]) -> None:
        self.accesses = accesses

    async def list_access(self, user_id: UUID) -> tuple[TenantAccess, ...]:
        return tuple(access for access in self.accesses if access.user_id == user_id)

    async def find_access(self, user_id: UUID, tenant_id: UUID) -> TenantAccess | None:
        return next(
            (
                access
                for access in self.accesses
                if access.user_id == user_id and access.tenant_id == tenant_id
            ),
            None,
        )

    async def create_tenant(
        self,
        *,
        owner_user_id: UUID,
        organization_id: UUID,
        name: str,
        now: datetime,
    ) -> TenantAccess:
        raise NotImplementedError


def test_single_membership_is_selected_when_header_is_absent() -> None:
    async def exercise() -> None:
        expected = TenantAccess(TENANT_A, USER_ID, TenantRole.OWNER)

        assert (
            await TenancyService(FakeTenancyStore((expected,))).resolve(USER_ID, None) == expected
        )

    asyncio.run(exercise())


def test_multiple_memberships_require_an_explicit_tenant() -> None:
    async def exercise() -> None:
        service = TenancyService(
            FakeTenancyStore(
                (
                    TenantAccess(TENANT_A, USER_ID, TenantRole.OWNER),
                    TenantAccess(TENANT_B, USER_ID, TenantRole.EDITOR),
                )
            )
        )

        with pytest.raises(TenancyError, match="tenant_selection_required"):
            await service.resolve(USER_ID, None)

    asyncio.run(exercise())


def test_non_member_tenant_is_rejected() -> None:
    async def exercise() -> None:
        service = TenancyService(
            FakeTenancyStore((TenantAccess(TENANT_A, USER_ID, TenantRole.OWNER),))
        )

        with pytest.raises(TenancyError, match="tenant_access_denied"):
            await service.resolve(USER_ID, TENANT_B)

    asyncio.run(exercise())


def test_viewer_cannot_write_and_editor_cannot_administer() -> None:
    async def exercise() -> None:
        viewer = TenantAccess(TENANT_A, USER_ID, TenantRole.VIEWER)
        editor = TenantAccess(TENANT_B, USER_ID, TenantRole.EDITOR)
        service = TenancyService(FakeTenancyStore((viewer, editor)))

        with pytest.raises(TenancyError, match="tenant_write_forbidden"):
            await service.resolve(USER_ID, TENANT_A, write=True)
        with pytest.raises(TenancyError, match="tenant_admin_forbidden"):
            await service.resolve(USER_ID, TENANT_B, administer=True)

    asyncio.run(exercise())


def test_new_tenant_runs_platform_catalog_initializer_before_returning() -> None:
    initialized: list[UUID] = []
    expected = TenantAccess(TENANT_B, USER_ID, TenantRole.OWNER)

    class CreatingStore(FakeTenancyStore):
        async def create_tenant(
            self,
            *,
            owner_user_id: UUID,
            organization_id: UUID,
            name: str,
            now: datetime,
        ) -> TenantAccess:
            del organization_id, name, now
            assert owner_user_id == USER_ID
            return expected

    async def initialize(tenant_id: UUID) -> None:
        initialized.append(tenant_id)

    async def exercise() -> None:
        created = await TenancyService(
            CreatingStore(()),
            tenant_initializer=initialize,
        ).create_tenant(
            owner_user_id=USER_ID,
            organization_id=UUID(int=3),
            name="新租户",
        )
        assert created == expected

    asyncio.run(exercise())
    assert initialized == [TENANT_B]


def test_new_tenant_initializer_seeds_full_model_catalog() -> None:
    """新建工作区经 tenant_initializer 后, 该工作区应自动获得全部预置模型。"""
    expected = TenantAccess(TENANT_B, USER_ID, TenantRole.OWNER)
    hub = TenantAwareRepositoryHub()
    service = build_tenant_scoped_service(hub)

    class CreatingStore(FakeTenancyStore):
        async def create_tenant(
            self,
            *,
            owner_user_id: UUID,
            organization_id: UUID,
            name: str,
            now: datetime,
        ) -> TenantAccess:
            del owner_user_id, organization_id, name, now
            return expected

    async def initialize(tenant_id: UUID) -> None:
        await seed_common_model_configurations_for_tenants(service, (tenant_id,))

    async def exercise() -> None:
        await TenancyService(
            CreatingStore(()),
            tenant_initializer=initialize,
        ).create_tenant(
            owner_user_id=USER_ID,
            organization_id=UUID(int=3),
            name="安师大实打实的",
        )

    asyncio.run(exercise())

    identifiers = {item.model_identifier for item in hub.repository_for(TENANT_B).items.values()}
    assert identifiers == _SEED_IDENTIFIERS
