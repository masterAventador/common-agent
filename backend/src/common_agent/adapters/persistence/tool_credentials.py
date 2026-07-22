from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import McpSourceCredentialRow, McpSourceRow
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.ports.tool_credentials import (
    StoredMcpCredential,
    ToolCredentialRepository,
)
from common_agent.tenancy.context import current_tenant
from common_agent.tools.credentials import EncryptedMcpCredential, McpCredentialKind
from common_agent.tools.models import McpSourceType


class SqlAlchemyToolCredentialRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = str(tenant_id)

    async def source_type(self, source_id: UUID) -> McpSourceType | None:
        value = await self._session.scalar(
            select(McpSourceRow.source_type).where(
                McpSourceRow.tenant_id == self._tenant_id,
                McpSourceRow.id == str(source_id),
            )
        )
        return McpSourceType(value) if value is not None else None

    async def get(self, source_id: UUID) -> StoredMcpCredential | None:
        row = await self._session.scalar(
            select(McpSourceCredentialRow).where(
                McpSourceCredentialRow.tenant_id == self._tenant_id,
                McpSourceCredentialRow.source_id == str(source_id),
            )
        )
        return _to_stored(row) if row is not None else None

    async def put(self, credential: StoredMcpCredential) -> None:
        row = await self._session.scalar(
            select(McpSourceCredentialRow)
            .where(
                McpSourceCredentialRow.tenant_id == self._tenant_id,
                McpSourceCredentialRow.source_id == str(credential.source_id),
            )
            .with_for_update()
        )
        if row is None:
            row = McpSourceCredentialRow(
                tenant_id=self._tenant_id,
                source_id=str(credential.source_id),
                credential_type=credential.kind.value,
                format_version=credential.encrypted.format_version,
                key_id=credential.encrypted.key_id,
                nonce=credential.encrypted.nonce,
                ciphertext=credential.encrypted.ciphertext,
                header_names=list(credential.header_names),
                created_at=to_database_datetime(credential.created_at),
                updated_at=to_database_datetime(credential.updated_at),
            )
            self._session.add(row)
        else:
            row.credential_type = credential.kind.value
            row.format_version = credential.encrypted.format_version
            row.key_id = credential.encrypted.key_id
            row.nonce = credential.encrypted.nonce
            row.ciphertext = credential.encrypted.ciphertext
            row.header_names = list(credential.header_names)
            row.updated_at = to_database_datetime(credential.updated_at)
        await self._session.flush()

    async def delete(self, source_id: UUID) -> None:
        await self._session.execute(
            delete(McpSourceCredentialRow).where(
                McpSourceCredentialRow.tenant_id == self._tenant_id,
                McpSourceCredentialRow.source_id == str(source_id),
            )
        )
        await self._session.flush()


class SqlAlchemyToolCredentialUnitOfWork:
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._repository: ToolCredentialRepository | None = None

    @property
    def credentials(self) -> ToolCredentialRepository:
        if self._repository is None:
            raise RuntimeError("MCP 凭据事务尚未开始")
        return self._repository

    async def __aenter__(self) -> SqlAlchemyToolCredentialUnitOfWork:
        if self._context is not None:
            raise RuntimeError("MCP 凭据事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._repository = SqlAlchemyToolCredentialRepository(session, self._tenant_id)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._context
        self._context = None
        self._session = None
        self._repository = None
        if context is None:
            raise RuntimeError("MCP 凭据事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("MCP 凭据事务尚未开始")
        await self._session.commit()


class SqlAlchemyToolCredentialUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyToolCredentialUnitOfWork:
        return SqlAlchemyToolCredentialUnitOfWork(
            self._database,
            self._tenant_id_provider(),
        )


def _to_stored(row: McpSourceCredentialRow) -> StoredMcpCredential:
    return StoredMcpCredential(
        source_id=UUID(row.source_id),
        kind=McpCredentialKind(row.credential_type),
        encrypted=EncryptedMcpCredential(
            format_version=row.format_version,
            key_id=row.key_id,
            nonce=bytes(row.nonce),
            ciphertext=bytes(row.ciphertext),
        ),
        header_names=tuple(row.header_names),
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )


__all__ = [
    "SqlAlchemyToolCredentialRepository",
    "SqlAlchemyToolCredentialUnitOfWork",
    "SqlAlchemyToolCredentialUnitOfWorkFactory",
]
