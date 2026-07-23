from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import UUID

from common_agent.concurrency import CoordinatedLockPool, DistributedLockProvider
from common_agent.tenancy.constants import DEFAULT_TENANT_ID

RAGFLOW_IDENTITY_FORMAT_VERSION = 1


class RagFlowTenantIdentityStatus(StrEnum):
    PROVISIONING = "provisioning"
    ACTIVE = "active"


@dataclass(frozen=True, slots=True)
class EncryptedRagFlowApiKey:
    format_version: int
    key_id: str
    nonce: bytes = field(repr=False)
    ciphertext: bytes = field(repr=False)


@dataclass(frozen=True, slots=True)
class RagFlowTenantIdentity:
    tenant_id: UUID
    account_email: str
    ragflow_tenant_id: str | None
    status: RagFlowTenantIdentityStatus
    encryption_key_id: str
    encrypted_api_key: EncryptedRagFlowApiKey | None = field(repr=False)
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class ProvisionedRagFlowIdentity:
    account_email: str
    ragflow_tenant_id: str
    api_key: str = field(repr=False)


class RagFlowIdentityCipher(Protocol):
    @property
    def active_key_id(self) -> str: ...

    def derive_account_password(self, tenant_id: UUID, *, key_id: str) -> str: ...

    def encrypt_token(
        self,
        platform_tenant_id: UUID,
        account_email: str,
        ragflow_tenant_id: str,
        token: str,
    ) -> EncryptedRagFlowApiKey: ...

    def decrypt_token(
        self,
        platform_tenant_id: UUID,
        account_email: str,
        ragflow_tenant_id: str,
        encrypted: EncryptedRagFlowApiKey,
    ) -> str: ...


class RagFlowTenantIdentityStore(Protocol):
    async def get(self, tenant_id: UUID) -> RagFlowTenantIdentity | None: ...

    async def reserve(self, identity: RagFlowTenantIdentity) -> RagFlowTenantIdentity: ...

    async def activate(self, identity: RagFlowTenantIdentity) -> None: ...

    async def legacy_ownership_tenant_ids(self) -> tuple[UUID, ...]: ...


class RagFlowAccountProvisioner(Protocol):
    async def provision(
        self,
        *,
        account_email: str,
        account_password: str,
    ) -> ProvisionedRagFlowIdentity: ...

    async def adopt(
        self,
        api_key: str,
        *,
        account_password: str,
    ) -> ProvisionedRagFlowIdentity: ...


class RagFlowTenantIdentityUnavailable(RuntimeError):
    code = "ragflow_tenant_identity_unavailable"


class LegacyRagFlowIdentityMigrationRequired(RuntimeError):
    code = "ragflow_legacy_identity_migration_required"


class RagFlowTenantIdentityService:
    def __init__(
        self,
        store: RagFlowTenantIdentityStore,
        *,
        cipher: RagFlowIdentityCipher,
        provisioner: RagFlowAccountProvisioner,
        legacy_api_key: str = "",
        clock: Callable[[], datetime] | None = None,
        distributed_locks: DistributedLockProvider | None = None,
    ) -> None:
        self._store = store
        self._cipher = cipher
        self._provisioner = provisioner
        self._legacy_api_key = legacy_api_key.strip()
        self._clock = clock or (lambda: datetime.now(UTC))
        self._locks = CoordinatedLockPool(distributed=distributed_locks)

    async def ensure_all(self, tenant_ids: tuple[UUID, ...]) -> None:
        await self.validate_legacy_migration()
        for tenant_id in tenant_ids:
            await self.ensure(tenant_id)

    async def validate_legacy_migration(self) -> None:
        legacy_owners = await self._store.legacy_ownership_tenant_ids()
        for tenant_id in legacy_owners:
            if tenant_id != DEFAULT_TENANT_ID and await self._store.get(tenant_id) is None:
                raise LegacyRagFlowIdentityMigrationRequired(
                    "检测到无法安全归属到独立 RAGFlow 租户的旧知识库映射"
                )

    async def ensure(self, tenant_id: UUID) -> RagFlowTenantIdentity:
        async with self._locks.hold(f"ragflow-tenant-identity:{tenant_id}"):
            existing = await self._store.get(tenant_id)
            if existing is not None and existing.status is RagFlowTenantIdentityStatus.ACTIVE:
                return existing

            if (
                existing is None
                and tenant_id == DEFAULT_TENANT_ID
                and self._legacy_api_key
            ):
                now = self._clock()
                legacy_reserved = await self._store.reserve(
                    RagFlowTenantIdentity(
                        tenant_id=tenant_id,
                        account_email="common-agent@local.test",
                        ragflow_tenant_id=None,
                        status=RagFlowTenantIdentityStatus.PROVISIONING,
                        encryption_key_id=self._cipher.active_key_id,
                        encrypted_api_key=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
                provisioned = await self._provisioner.adopt(
                    self._legacy_api_key,
                    account_password=self._cipher.derive_account_password(
                        tenant_id,
                        key_id=legacy_reserved.encryption_key_id,
                    ),
                )
                return await self._activate(legacy_reserved, provisioned)

            reserved: RagFlowTenantIdentity | None = existing
            if reserved is None:
                now = self._clock()
                reserved = await self._store.reserve(
                    RagFlowTenantIdentity(
                        tenant_id=tenant_id,
                        account_email=_account_email(tenant_id),
                        ragflow_tenant_id=None,
                        status=RagFlowTenantIdentityStatus.PROVISIONING,
                        encryption_key_id=self._cipher.active_key_id,
                        encrypted_api_key=None,
                        created_at=now,
                        updated_at=now,
                    )
                )
            provisioned = await self._provisioner.provision(
                account_email=reserved.account_email,
                account_password=self._cipher.derive_account_password(
                    tenant_id,
                    key_id=reserved.encryption_key_id,
                ),
            )
            if provisioned.account_email.casefold() != reserved.account_email.casefold():
                raise RagFlowTenantIdentityUnavailable("RAGFlow 账号身份与预留记录不一致")
            return await self._activate(reserved, provisioned)

    async def api_key_for(self, tenant_id: UUID) -> str:
        identity = await self._store.get(tenant_id)
        if identity is None or identity.status is not RagFlowTenantIdentityStatus.ACTIVE:
            identity = await self.ensure(tenant_id)
        if (
            identity.status is not RagFlowTenantIdentityStatus.ACTIVE
            or identity.ragflow_tenant_id is None
            or identity.encrypted_api_key is None
        ):
            raise RagFlowTenantIdentityUnavailable("当前工作区没有可用的 RAGFlow 身份")
        return self._cipher.decrypt_token(
            tenant_id,
            identity.account_email,
            identity.ragflow_tenant_id,
            identity.encrypted_api_key,
        )

    async def _activate(
        self,
        reserved: RagFlowTenantIdentity,
        provisioned: ProvisionedRagFlowIdentity,
    ) -> RagFlowTenantIdentity:
        activated = replace(
            reserved,
            account_email=provisioned.account_email,
            ragflow_tenant_id=provisioned.ragflow_tenant_id,
            status=RagFlowTenantIdentityStatus.ACTIVE,
            encrypted_api_key=self._cipher.encrypt_token(
                reserved.tenant_id,
                provisioned.account_email,
                provisioned.ragflow_tenant_id,
                provisioned.api_key,
            ),
            updated_at=self._clock(),
        )
        await self._store.activate(activated)
        return activated


def _account_email(tenant_id: UUID) -> str:
    return f"common-agent-{tenant_id.hex}@local.test"


__all__ = [
    "RAGFLOW_IDENTITY_FORMAT_VERSION",
    "EncryptedRagFlowApiKey",
    "LegacyRagFlowIdentityMigrationRequired",
    "ProvisionedRagFlowIdentity",
    "RagFlowAccountProvisioner",
    "RagFlowIdentityCipher",
    "RagFlowTenantIdentity",
    "RagFlowTenantIdentityService",
    "RagFlowTenantIdentityStatus",
    "RagFlowTenantIdentityStore",
    "RagFlowTenantIdentityUnavailable",
]
