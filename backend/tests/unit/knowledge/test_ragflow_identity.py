from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID

import pytest

from common_agent.adapters.security.ragflow_identity import AesGcmRagFlowIdentityCipher
from common_agent.knowledge.ragflow_identity import (
    LegacyRagFlowIdentityMigrationRequired,
    ProvisionedRagFlowIdentity,
    RagFlowTenantIdentity,
    RagFlowTenantIdentityService,
    RagFlowTenantIdentityStatus,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID

TENANT_B = UUID("10000000-0000-4000-8000-000000000002")
NOW = datetime(2026, 7, 23, tzinfo=UTC)


class _Store:
    def __init__(self) -> None:
        self.rows: dict[UUID, RagFlowTenantIdentity] = {}
        self.foreign_legacy_owners: tuple[UUID, ...] = ()

    async def get(self, tenant_id: UUID) -> RagFlowTenantIdentity | None:
        return self.rows.get(tenant_id)

    async def reserve(self, identity: RagFlowTenantIdentity) -> RagFlowTenantIdentity:
        return self.rows.setdefault(identity.tenant_id, identity)

    async def activate(self, identity: RagFlowTenantIdentity) -> None:
        self.rows[identity.tenant_id] = identity

    async def legacy_ownership_tenant_ids(self) -> tuple[UUID, ...]:
        return self.foreign_legacy_owners


class _Provisioner:
    def __init__(self) -> None:
        self.provisions: list[tuple[str, str]] = []
        self.adoptions: list[tuple[str, str]] = []
        self.fail_once = False

    async def provision(
        self,
        *,
        account_email: str,
        account_password: str,
    ) -> ProvisionedRagFlowIdentity:
        self.provisions.append((account_email, account_password))
        if self.fail_once:
            self.fail_once = False
            raise RuntimeError("temporary")
        return ProvisionedRagFlowIdentity(
            account_email=account_email,
            ragflow_tenant_id=f"ragflow-{len(self.provisions)}",
            api_key=f"ragflow-token-{len(self.provisions)}",
        )

    async def adopt(
        self,
        api_key: str,
        *,
        account_password: str,
    ) -> ProvisionedRagFlowIdentity:
        self.adoptions.append((api_key, account_password))
        return ProvisionedRagFlowIdentity(
            account_email="common-agent@local.test",
            ragflow_tenant_id="legacy-ragflow-tenant",
            api_key=api_key,
        )


def _service(
    store: _Store,
    provisioner: _Provisioner,
    *,
    legacy_api_key: str = "",
) -> RagFlowTenantIdentityService:
    return RagFlowTenantIdentityService(
        store,
        cipher=AesGcmRagFlowIdentityCipher(
            keys={"active": b"a" * 32},
            active_key_id="active",
        ),
        provisioner=provisioner,
        legacy_api_key=legacy_api_key,
        clock=lambda: NOW,
    )


def test_default_workspace_adopts_the_existing_ragflow_account_without_copying_data() -> None:
    async def exercise() -> None:
        store = _Store()
        provisioner = _Provisioner()
        service = _service(store, provisioner, legacy_api_key="ragflow-existing")

        identity = await service.ensure(DEFAULT_TENANT_ID)

        assert len(provisioner.adoptions) == 1
        assert provisioner.adoptions[0][0] == "ragflow-existing"
        assert len(provisioner.adoptions[0][1]) >= 32
        assert provisioner.provisions == []
        assert identity.status is RagFlowTenantIdentityStatus.ACTIVE
        assert identity.account_email == "common-agent@local.test"
        assert await service.api_key_for(DEFAULT_TENANT_ID) == "ragflow-existing"
        assert b"ragflow-existing" not in identity.encrypted_api_key.ciphertext

    asyncio.run(exercise())


def test_new_workspace_gets_a_stable_dedicated_account_and_retry_is_idempotent() -> None:
    async def exercise() -> None:
        store = _Store()
        provisioner = _Provisioner()
        provisioner.fail_once = True
        service = _service(store, provisioner)

        with pytest.raises(RuntimeError, match="temporary"):
            await service.ensure(TENANT_B)
        reserved = store.rows[TENANT_B]
        assert reserved.status is RagFlowTenantIdentityStatus.PROVISIONING
        assert reserved.encrypted_api_key is None

        identity = await service.ensure(TENANT_B)

        assert identity.status is RagFlowTenantIdentityStatus.ACTIVE
        assert provisioner.provisions[0] == provisioner.provisions[1]
        assert identity.account_email == f"common-agent-{TENANT_B.hex}@local.test"
        assert await service.api_key_for(TENANT_B) == "ragflow-token-2"

    asyncio.run(exercise())


def test_unclaimed_non_default_legacy_mapping_fails_closed_before_provisioning() -> None:
    async def exercise() -> None:
        store = _Store()
        store.foreign_legacy_owners = (TENANT_B,)
        provisioner = _Provisioner()
        service = _service(store, provisioner, legacy_api_key="ragflow-existing")

        with pytest.raises(LegacyRagFlowIdentityMigrationRequired):
            await service.ensure_all((DEFAULT_TENANT_ID, TENANT_B))

        assert provisioner.adoptions == []
        assert provisioner.provisions == []

    asyncio.run(exercise())
