from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import cast
from uuid import UUID

from sqlalchemy import delete, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ConversationToolGrantRow,
    EmployeeToolGrantRow,
    McpSourceCredentialRow,
    McpSourceRow,
    ToolCapabilityRow,
    ToolCollectionSourceRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.ports.external_mcp import (
    ExternalMcpRepository,
    ExternalMcpRepositoryConflict,
)
from common_agent.tenancy.context import current_tenant
from common_agent.tools.external_mcp import ExternalMcpSnapshot, ExternalMcpSyncResult
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolCapabilityStatus,
)


class SqlAlchemyExternalMcpRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = str(tenant_id)

    async def list_sources(self) -> tuple[ExternalMcpSnapshot, ...]:
        sources = tuple(
            await self._session.scalars(
                select(McpSourceRow)
                .where(
                    McpSourceRow.tenant_id == self._tenant_id,
                    McpSourceRow.source_type == McpSourceType.EXTERNAL.value,
                )
                .order_by(McpSourceRow.created_at, McpSourceRow.id)
            )
        )
        capabilities = tuple(
            await self._session.scalars(
                select(ToolCapabilityRow)
                .where(
                    ToolCapabilityRow.tenant_id == self._tenant_id,
                    ToolCapabilityRow.source_id.in_([row.id for row in sources]),
                )
                .order_by(ToolCapabilityRow.created_at, ToolCapabilityRow.id)
            )
        )
        by_source: dict[str, list[ToolCapability]] = {}
        for row in capabilities:
            by_source.setdefault(row.source_id, []).append(_capability_to_domain(row))
        return tuple(
            ExternalMcpSnapshot(
                _source_to_domain(row),
                tuple(by_source.get(row.id, ())),
            )
            for row in sources
        )

    async def snapshot(
        self,
        source_id: UUID,
        *,
        for_update: bool = False,
    ) -> ExternalMcpSnapshot | None:
        source_statement = select(McpSourceRow).where(
            McpSourceRow.tenant_id == self._tenant_id,
            McpSourceRow.id == str(source_id),
            McpSourceRow.source_type == McpSourceType.EXTERNAL.value,
        )
        capability_statement = (
            select(ToolCapabilityRow)
            .where(
                ToolCapabilityRow.tenant_id == self._tenant_id,
                ToolCapabilityRow.source_id == str(source_id),
            )
            .order_by(ToolCapabilityRow.created_at, ToolCapabilityRow.id)
        )
        if for_update:
            source_statement = source_statement.with_for_update()
            capability_statement = capability_statement.with_for_update()
        source = await self._session.scalar(source_statement)
        if source is None:
            return None
        capabilities = tuple(await self._session.scalars(capability_statement))
        return ExternalMcpSnapshot(
            _source_to_domain(source),
            tuple(_capability_to_domain(row) for row in capabilities),
        )

    async def source_name_exists(self, name: str, excluding: UUID | None = None) -> bool:
        statement = select(McpSourceRow.id).where(
            McpSourceRow.tenant_id == self._tenant_id,
            McpSourceRow.name == name,
        )
        if excluding is not None:
            statement = statement.where(McpSourceRow.id != str(excluding))
        return await self._session.scalar(statement) is not None

    async def add_source(self, source: McpSource) -> None:
        self._session.add(_source_row(self._tenant_id, source))
        await self._flush()

    async def update_source(self, source: McpSource) -> None:
        row = await self._source_row_for_update(source.id)
        if row is None:
            raise ExternalMcpRepositoryConflict
        _assign_source(row, source)
        await self._flush()

    async def clear_credential(self, source_id: UUID) -> None:
        await self._session.execute(
            delete(McpSourceCredentialRow).where(
                McpSourceCredentialRow.tenant_id == self._tenant_id,
                McpSourceCredentialRow.source_id == str(source_id),
            )
        )

    async def apply_sync(self, result: ExternalMcpSyncResult) -> None:
        source_row = await self._source_row_for_update(result.source.id)
        if source_row is None:
            raise ExternalMcpRepositoryConflict
        existing_rows = tuple(
            await self._session.scalars(
                select(ToolCapabilityRow)
                .where(
                    ToolCapabilityRow.tenant_id == self._tenant_id,
                    ToolCapabilityRow.source_id == str(result.source.id),
                )
                .with_for_update()
            )
        )
        existing_by_id = {row.id: row for row in existing_rows}
        result_ids = {str(item.id) for item in result.capabilities}
        if not set(existing_by_id).issubset(result_ids):
            raise ExternalMcpRepositoryConflict
        _assign_source(source_row, result.source)
        for capability in result.capabilities:
            row = existing_by_id.get(str(capability.id))
            if row is None:
                self._session.add(_capability_row(self._tenant_id, capability))
            else:
                _assign_capability(row, capability)
        await self._flush()

    async def delete_source(self, source_id: UUID) -> bool:
        row = await self._source_row_for_update(source_id)
        if row is None:
            return True
        capability_ids = select(ToolCapabilityRow.id).where(
            ToolCapabilityRow.tenant_id == self._tenant_id,
            ToolCapabilityRow.source_id == str(source_id),
        )
        referenced = await self._session.scalar(
            select(
                exists().where(
                    ToolCollectionSourceRow.tenant_id == self._tenant_id,
                    ToolCollectionSourceRow.source_id == str(source_id),
                )
                | exists().where(
                    EmployeeToolGrantRow.tenant_id == self._tenant_id,
                    EmployeeToolGrantRow.capability_id.in_(capability_ids),
                )
                | exists().where(
                    ConversationToolGrantRow.tenant_id == self._tenant_id,
                    ConversationToolGrantRow.capability_id.in_(capability_ids),
                )
            )
        )
        if referenced:
            return False
        await self._session.delete(row)
        await self._flush()
        return True

    async def _source_row_for_update(self, source_id: UUID) -> McpSourceRow | None:
        return cast(
            McpSourceRow | None,
            await self._session.scalar(
                select(McpSourceRow)
                .where(
                    McpSourceRow.tenant_id == self._tenant_id,
                    McpSourceRow.id == str(source_id),
                    McpSourceRow.source_type == McpSourceType.EXTERNAL.value,
                )
                .with_for_update()
            ),
        )

    async def _flush(self) -> None:
        try:
            await self._session.flush()
        except IntegrityError:
            raise ExternalMcpRepositoryConflict from None


class SqlAlchemyExternalMcpUnitOfWork:
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._repository: ExternalMcpRepository | None = None

    @property
    def external_mcp(self) -> ExternalMcpRepository:
        if self._repository is None:
            raise RuntimeError("外部 MCP 事务尚未开始")
        return self._repository

    async def __aenter__(self) -> SqlAlchemyExternalMcpUnitOfWork:
        if self._context is not None:
            raise RuntimeError("外部 MCP 事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._repository = SqlAlchemyExternalMcpRepository(session, self._tenant_id)
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
            raise RuntimeError("外部 MCP 事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("外部 MCP 事务尚未开始")
        await self._session.commit()


class SqlAlchemyExternalMcpUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyExternalMcpUnitOfWork:
        return SqlAlchemyExternalMcpUnitOfWork(
            self._database,
            self._tenant_id_provider(),
        )


def _source_row(tenant_id: str, source: McpSource) -> McpSourceRow:
    return McpSourceRow(
        id=str(source.id),
        tenant_id=tenant_id,
        name=source.name,
        description=source.description,
        source_type=source.source_type.value,
        endpoint_url=source.endpoint_url,
        status=source.status.value,
        created_at=to_database_datetime(source.created_at),
        updated_at=to_database_datetime(source.updated_at),
    )


def _assign_source(row: McpSourceRow, source: McpSource) -> None:
    row.name = source.name
    row.description = source.description
    row.endpoint_url = source.endpoint_url
    row.status = source.status.value
    row.updated_at = to_database_datetime(source.updated_at)


def _capability_row(tenant_id: str, capability: ToolCapability) -> ToolCapabilityRow:
    return ToolCapabilityRow(
        id=str(capability.id),
        tenant_id=tenant_id,
        source_id=str(capability.source_id),
        remote_name=capability.remote_name,
        display_name=capability.display_name,
        description=capability.description,
        input_schema=capability.input_schema,
        schema_fingerprint=capability.schema_fingerprint,
        status=capability.status.value,
        created_at=to_database_datetime(capability.created_at),
        updated_at=to_database_datetime(capability.updated_at),
    )


def _assign_capability(row: ToolCapabilityRow, capability: ToolCapability) -> None:
    row.remote_name = capability.remote_name
    row.display_name = capability.display_name
    row.description = capability.description
    row.input_schema = capability.input_schema
    row.schema_fingerprint = capability.schema_fingerprint
    row.status = capability.status.value
    row.updated_at = to_database_datetime(capability.updated_at)


def _source_to_domain(row: McpSourceRow) -> McpSource:
    return McpSource(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        source_type=McpSourceType(row.source_type),
        endpoint_url=row.endpoint_url,
        status=McpSourceStatus(row.status),
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )


def _capability_to_domain(row: ToolCapabilityRow) -> ToolCapability:
    return ToolCapability(
        id=UUID(row.id),
        source_id=UUID(row.source_id),
        remote_name=row.remote_name,
        display_name=row.display_name,
        description=row.description,
        input_schema=row.input_schema,
        schema_fingerprint=row.schema_fingerprint,
        status=ToolCapabilityStatus(row.status),
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )


__all__ = [
    "SqlAlchemyExternalMcpRepository",
    "SqlAlchemyExternalMcpUnitOfWork",
    "SqlAlchemyExternalMcpUnitOfWorkFactory",
]
