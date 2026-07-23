from __future__ import annotations

from uuid import UUID

from sqlalchemy import distinct, select
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    RagFlowKnowledgeBaseOwnershipRow,
    RagFlowTenantIdentityRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.knowledge.ragflow_identity import (
    EncryptedRagFlowApiKey,
    RagFlowTenantIdentity,
    RagFlowTenantIdentityStatus,
)


class SqlAlchemyRagFlowTenantIdentityStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(self, tenant_id: UUID) -> RagFlowTenantIdentity | None:
        async with self._database.session() as session:
            row = await session.get(RagFlowTenantIdentityRow, str(tenant_id))
            return _to_identity(row) if row is not None else None

    async def reserve(self, identity: RagFlowTenantIdentity) -> RagFlowTenantIdentity:
        try:
            async with self._database.session() as session:
                session.add(
                    RagFlowTenantIdentityRow(
                        tenant_id=str(identity.tenant_id),
                        account_email=identity.account_email.casefold(),
                        ragflow_tenant_id=None,
                        status=RagFlowTenantIdentityStatus.PROVISIONING.value,
                        format_version=None,
                        encryption_key_id=identity.encryption_key_id,
                        nonce=None,
                        ciphertext=None,
                        created_at=to_database_datetime(identity.created_at),
                        updated_at=to_database_datetime(identity.updated_at),
                    )
                )
                await session.commit()
        except IntegrityError:
            pass
        reserved = await self.get(identity.tenant_id)
        if reserved is None:
            raise RuntimeError("RAGFlow 租户身份预留失败")
        return reserved

    async def activate(self, identity: RagFlowTenantIdentity) -> None:
        encrypted = identity.encrypted_api_key
        if (
            identity.status is not RagFlowTenantIdentityStatus.ACTIVE
            or identity.ragflow_tenant_id is None
            or encrypted is None
        ):
            raise ValueError("只能激活完整的 RAGFlow 租户身份")
        async with self._database.session() as session:
            row = await session.scalar(
                select(RagFlowTenantIdentityRow)
                .where(RagFlowTenantIdentityRow.tenant_id == str(identity.tenant_id))
                .with_for_update()
            )
            if (
                row is None
                or row.account_email != identity.account_email.casefold()
                or row.encryption_key_id != identity.encryption_key_id
            ):
                raise RuntimeError("RAGFlow 租户身份激活目标不一致")
            row.ragflow_tenant_id = identity.ragflow_tenant_id
            row.status = identity.status.value
            row.format_version = encrypted.format_version
            row.nonce = encrypted.nonce
            row.ciphertext = encrypted.ciphertext
            row.updated_at = to_database_datetime(identity.updated_at)
            await session.commit()

    async def legacy_ownership_tenant_ids(self) -> tuple[UUID, ...]:
        async with self._database.session() as session:
            values = await session.scalars(
                select(distinct(RagFlowKnowledgeBaseOwnershipRow.tenant_id)).order_by(
                    RagFlowKnowledgeBaseOwnershipRow.tenant_id
                )
            )
            return tuple(UUID(value) for value in values)


def _to_identity(row: RagFlowTenantIdentityRow) -> RagFlowTenantIdentity:
    encrypted = (
        None
        if row.format_version is None or row.nonce is None or row.ciphertext is None
        else EncryptedRagFlowApiKey(
            format_version=row.format_version,
            key_id=row.encryption_key_id,
            nonce=bytes(row.nonce),
            ciphertext=bytes(row.ciphertext),
        )
    )
    return RagFlowTenantIdentity(
        tenant_id=UUID(row.tenant_id),
        account_email=row.account_email,
        ragflow_tenant_id=row.ragflow_tenant_id,
        status=RagFlowTenantIdentityStatus(row.status),
        encryption_key_id=row.encryption_key_id,
        encrypted_api_key=encrypted,
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )


__all__ = ["SqlAlchemyRagFlowTenantIdentityStore"]
