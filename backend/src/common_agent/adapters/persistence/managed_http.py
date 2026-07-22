from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import cast
from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ConversationToolGrantRow,
    EmployeeToolGrantRow,
    ManagedHttpCapabilityRow,
    McpSourceRow,
    ToolCapabilityRow,
    ToolCollectionSourceRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.ports.managed_http import (
    ManagedHttpRepository,
    ManagedHttpRepositoryConflict,
)
from common_agent.tenancy.context import current_tenant
from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpParameterBinding,
    ManagedHttpParameterLocation,
    ManagedHttpRuntimeSnapshot,
)
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolCapabilityStatus,
)


class SqlAlchemyManagedHttpRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = str(tenant_id)

    async def list_sources(self) -> tuple[ManagedHttpRuntimeSnapshot, ...]:
        source_rows = tuple(
            await self._session.scalars(
                select(McpSourceRow)
                .where(
                    McpSourceRow.tenant_id == self._tenant_id,
                    McpSourceRow.source_type == McpSourceType.MANAGED_HTTP.value,
                )
                .order_by(McpSourceRow.created_at, McpSourceRow.id)
            )
        )
        capability_rows = (
            await self._session.execute(
                select(ToolCapabilityRow, ManagedHttpCapabilityRow)
                .join(
                    ManagedHttpCapabilityRow,
                    (ManagedHttpCapabilityRow.tenant_id == ToolCapabilityRow.tenant_id)
                    & (ManagedHttpCapabilityRow.capability_id == ToolCapabilityRow.id),
                )
                .where(
                    ToolCapabilityRow.tenant_id == self._tenant_id,
                    ToolCapabilityRow.source_id.in_([row.id for row in source_rows]),
                )
                .order_by(ToolCapabilityRow.created_at, ToolCapabilityRow.id)
            )
        ).all()
        by_source: dict[str, list[ManagedHttpCapability]] = {}
        for capability_row, config_row in capability_rows:
            by_source.setdefault(capability_row.source_id, []).append(
                _capability_to_domain(capability_row, config_row)
            )
        return tuple(
            ManagedHttpRuntimeSnapshot(
                _source_to_domain(source_row),
                tuple(by_source.get(source_row.id, ())),
            )
            for source_row in source_rows
        )

    async def snapshot(self, source_id: UUID) -> ManagedHttpRuntimeSnapshot | None:
        source_row = await self._session.scalar(
            select(McpSourceRow).where(
                McpSourceRow.tenant_id == self._tenant_id,
                McpSourceRow.id == str(source_id),
                McpSourceRow.source_type == McpSourceType.MANAGED_HTTP.value,
            )
        )
        if source_row is None:
            return None
        rows = (
            await self._session.execute(
                select(ToolCapabilityRow, ManagedHttpCapabilityRow)
                .join(
                    ManagedHttpCapabilityRow,
                    (ManagedHttpCapabilityRow.tenant_id == ToolCapabilityRow.tenant_id)
                    & (ManagedHttpCapabilityRow.capability_id == ToolCapabilityRow.id),
                )
                .where(
                    ToolCapabilityRow.tenant_id == self._tenant_id,
                    ToolCapabilityRow.source_id == str(source_id),
                )
                .order_by(ToolCapabilityRow.created_at, ToolCapabilityRow.id)
            )
        ).all()
        return ManagedHttpRuntimeSnapshot(
            _source_to_domain(source_row),
            tuple(_capability_to_domain(capability, config) for capability, config in rows),
        )

    async def source_name_exists(self, name: str, excluding: UUID | None = None) -> bool:
        statement = select(McpSourceRow.id).where(
            McpSourceRow.tenant_id == self._tenant_id,
            McpSourceRow.name == name,
        )
        if excluding is not None:
            statement = statement.where(McpSourceRow.id != str(excluding))
        return await self._session.scalar(statement) is not None

    async def capability_name_exists(
        self,
        source_id: UUID,
        name: str,
        excluding: UUID | None = None,
    ) -> bool:
        statement = select(ToolCapabilityRow.id).where(
            ToolCapabilityRow.tenant_id == self._tenant_id,
            ToolCapabilityRow.source_id == str(source_id),
            ToolCapabilityRow.remote_name == name,
        )
        if excluding is not None:
            statement = statement.where(ToolCapabilityRow.id != str(excluding))
        return await self._session.scalar(statement) is not None

    async def add_source(self, source: McpSource) -> None:
        self._session.add(_source_row(self._tenant_id, source))
        try:
            await self._session.flush()
        except IntegrityError:
            raise ManagedHttpRepositoryConflict from None

    async def update_source(self, source: McpSource) -> None:
        row = await self._session.scalar(
            select(McpSourceRow)
            .where(
                McpSourceRow.tenant_id == self._tenant_id,
                McpSourceRow.id == str(source.id),
                McpSourceRow.source_type == McpSourceType.MANAGED_HTTP.value,
            )
            .with_for_update()
        )
        if row is None:
            raise RuntimeError("托管 MCP 来源在更新期间消失")
        row.name = source.name
        row.description = source.description
        row.endpoint_url = source.endpoint_url
        row.status = source.status.value
        row.updated_at = to_database_datetime(source.updated_at)
        try:
            await self._session.flush()
        except IntegrityError:
            raise ManagedHttpRepositoryConflict from None

    async def delete_source(self, source_id: UUID) -> bool:
        row = await self._session.scalar(
            select(McpSourceRow)
            .where(
                McpSourceRow.tenant_id == self._tenant_id,
                McpSourceRow.id == str(source_id),
                McpSourceRow.source_type == McpSourceType.MANAGED_HTTP.value,
            )
            .with_for_update()
        )
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
        try:
            await self._session.flush()
        except IntegrityError:
            raise ManagedHttpRepositoryConflict from None
        return True

    async def add_capability(self, capability: ManagedHttpCapability) -> None:
        self._session.add(_tool_row(self._tenant_id, capability.capability))
        try:
            await self._session.flush()
            self._session.add(_configuration_row(self._tenant_id, capability))
            await self._session.flush()
        except IntegrityError:
            raise ManagedHttpRepositoryConflict from None

    async def update_capability(self, capability: ManagedHttpCapability) -> None:
        capability_id = str(capability.capability.id)
        tool_row = await self._session.scalar(
            select(ToolCapabilityRow)
            .where(
                ToolCapabilityRow.tenant_id == self._tenant_id,
                ToolCapabilityRow.id == capability_id,
                ToolCapabilityRow.source_id == str(capability.capability.source_id),
            )
            .with_for_update()
        )
        config_row = await self._session.scalar(
            select(ManagedHttpCapabilityRow)
            .where(
                ManagedHttpCapabilityRow.tenant_id == self._tenant_id,
                ManagedHttpCapabilityRow.capability_id == capability_id,
            )
            .with_for_update()
        )
        if tool_row is None or config_row is None:
            raise RuntimeError("托管 MCP 能力在更新期间消失")
        tool = capability.capability
        tool_row.remote_name = tool.remote_name
        tool_row.display_name = tool.display_name
        tool_row.description = tool.description
        tool_row.input_schema = tool.input_schema
        tool_row.schema_fingerprint = tool.schema_fingerprint
        tool_row.status = tool.status.value
        tool_row.updated_at = to_database_datetime(tool.updated_at)
        _assign_configuration(config_row, capability)
        try:
            await self._session.flush()
        except IntegrityError:
            raise ManagedHttpRepositoryConflict from None

    async def delete_capability(self, source_id: UUID, capability_id: UUID) -> bool:
        row = await self._session.scalar(
            select(ToolCapabilityRow)
            .where(
                ToolCapabilityRow.tenant_id == self._tenant_id,
                ToolCapabilityRow.source_id == str(source_id),
                ToolCapabilityRow.id == str(capability_id),
            )
            .with_for_update()
        )
        if row is None:
            return True
        referenced = await self._session.scalar(
            select(
                exists().where(
                    EmployeeToolGrantRow.tenant_id == self._tenant_id,
                    EmployeeToolGrantRow.capability_id == str(capability_id),
                )
                | exists().where(
                    ConversationToolGrantRow.tenant_id == self._tenant_id,
                    ConversationToolGrantRow.capability_id == str(capability_id),
                )
            )
        )
        if referenced:
            return False
        await self._session.delete(row)
        try:
            await self._session.flush()
        except IntegrityError:
            raise ManagedHttpRepositoryConflict from None
        return True


class SqlAlchemyManagedHttpUnitOfWork:
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._repository: ManagedHttpRepository | None = None

    @property
    def managed_http(self) -> ManagedHttpRepository:
        if self._repository is None:
            raise RuntimeError("托管 MCP 事务尚未开始")
        return self._repository

    async def __aenter__(self) -> SqlAlchemyManagedHttpUnitOfWork:
        if self._context is not None:
            raise RuntimeError("托管 MCP 事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._repository = SqlAlchemyManagedHttpRepository(session, self._tenant_id)
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
            raise RuntimeError("托管 MCP 事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("托管 MCP 事务尚未开始")
        await self._session.commit()


class SqlAlchemyManagedHttpUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyManagedHttpUnitOfWork:
        return SqlAlchemyManagedHttpUnitOfWork(
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


def _tool_row(tenant_id: str, tool: ToolCapability) -> ToolCapabilityRow:
    return ToolCapabilityRow(
        id=str(tool.id),
        tenant_id=tenant_id,
        source_id=str(tool.source_id),
        remote_name=tool.remote_name,
        display_name=tool.display_name,
        description=tool.description,
        input_schema=tool.input_schema,
        schema_fingerprint=tool.schema_fingerprint,
        status=tool.status.value,
        created_at=to_database_datetime(tool.created_at),
        updated_at=to_database_datetime(tool.updated_at),
    )


def _configuration_row(
    tenant_id: str,
    capability: ManagedHttpCapability,
) -> ManagedHttpCapabilityRow:
    row = ManagedHttpCapabilityRow(
        tenant_id=tenant_id,
        capability_id=str(capability.capability.id),
        http_method=capability.method,
        path_template=capability.path_template,
        parameter_bindings=[],
        timeout_seconds=capability.timeout_seconds,
        response_json_pointer=capability.response_json_pointer,
    )
    _assign_configuration(row, capability)
    return row


def _assign_configuration(
    row: ManagedHttpCapabilityRow,
    capability: ManagedHttpCapability,
) -> None:
    row.http_method = capability.method
    row.path_template = capability.path_template
    row.parameter_bindings = [
        {
            "argument_name": binding.argument_name,
            "location": binding.location.value,
            "target_name": binding.target_name,
        }
        for binding in capability.parameter_bindings
    ]
    row.timeout_seconds = capability.timeout_seconds
    row.response_json_pointer = capability.response_json_pointer


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


def _capability_to_domain(
    row: ToolCapabilityRow,
    config: ManagedHttpCapabilityRow,
) -> ManagedHttpCapability:
    tool = ToolCapability(
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
    return ManagedHttpCapability(
        capability=tool,
        method=config.http_method,
        path_template=config.path_template,
        parameter_bindings=tuple(
            ManagedHttpParameterBinding(
                argument_name=value["argument_name"],
                location=ManagedHttpParameterLocation(value["location"]),
                target_name=value["target_name"],
            )
            for value in config.parameter_bindings
        ),
        timeout_seconds=config.timeout_seconds,
        response_json_pointer=config.response_json_pointer,
    )


__all__ = [
    "SqlAlchemyManagedHttpRepository",
    "SqlAlchemyManagedHttpUnitOfWork",
    "SqlAlchemyManagedHttpUnitOfWorkFactory",
]
