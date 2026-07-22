from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from typing import cast
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ConversationRow,
    ConversationToolCollectionSelectionRow,
    ConversationToolGrantRow,
    EmployeeRow,
    EmployeeToolCollectionSelectionRow,
    EmployeeToolGrantRow,
    McpSourceRow,
    ToolCapabilityRow,
    ToolCollectionRow,
    ToolCollectionSourceRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.ports.tools import (
    ToolGrantResolution,
    ToolRepository,
    ToolRuntimeResolution,
)
from common_agent.tenancy.context import current_tenant
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolCapabilityStatus,
    ToolCatalog,
    ToolCollection,
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTarget,
    ToolGrantTargetType,
    ToolRuntimeCapability,
)


class SqlAlchemyToolRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = str(tenant_id)

    async def catalog(self) -> ToolCatalog:
        sources = tuple(
            await self._session.scalars(
                select(McpSourceRow)
                .where(McpSourceRow.tenant_id == self._tenant_id)
                .order_by(McpSourceRow.created_at, McpSourceRow.id)
            )
        )
        capabilities = tuple(
            await self._session.scalars(
                select(ToolCapabilityRow)
                .where(ToolCapabilityRow.tenant_id == self._tenant_id)
                .order_by(ToolCapabilityRow.created_at, ToolCapabilityRow.id)
            )
        )
        collections = tuple(
            await self._session.scalars(
                select(ToolCollectionRow)
                .where(ToolCollectionRow.tenant_id == self._tenant_id)
                .order_by(ToolCollectionRow.created_at, ToolCollectionRow.id)
            )
        )
        association_rows = tuple(
            (
                str(collection_id),
                str(source_id),
            )
            for collection_id, source_id in (
                await self._session.execute(
                    select(
                        ToolCollectionSourceRow.collection_id,
                        ToolCollectionSourceRow.source_id,
                    )
                    .where(ToolCollectionSourceRow.tenant_id == self._tenant_id)
                    .order_by(
                        ToolCollectionSourceRow.collection_id,
                        ToolCollectionSourceRow.source_id,
                    )
                )
            ).all()
        )
        source_ids_by_collection: dict[str, list[UUID]] = {}
        for collection_id, source_id in association_rows:
            source_ids_by_collection.setdefault(collection_id, []).append(UUID(source_id))
        return ToolCatalog(
            sources=tuple(_source_to_domain(row) for row in sources),
            capabilities=tuple(_capability_to_domain(row) for row in capabilities),
            collections=tuple(
                _collection_to_domain(
                    row,
                    tuple(source_ids_by_collection.get(row.id, ())),
                )
                for row in collections
            ),
        )

    async def target_exists(self, target_type: ToolGrantTargetType, target_id: UUID) -> bool:
        if target_type is ToolGrantTargetType.EMPLOYEE:
            statement = select(EmployeeRow.id).where(
                EmployeeRow.tenant_id == self._tenant_id,
                EmployeeRow.id == str(target_id),
            )
        else:
            statement = select(ConversationRow.id).where(
                ConversationRow.tenant_id == self._tenant_id,
                ConversationRow.id == str(target_id),
                ConversationRow.source == "generic",
            )
        found = await self._session.scalar(statement)
        return found is not None

    async def grants(
        self,
        target_type: ToolGrantTargetType,
        target_id: UUID,
    ) -> ToolGrantSnapshot:
        target_value = str(target_id)
        if target_type is ToolGrantTargetType.EMPLOYEE:
            raw_collection_ids = await self._session.scalars(
                select(EmployeeToolCollectionSelectionRow.collection_id)
                .where(
                    EmployeeToolCollectionSelectionRow.tenant_id == self._tenant_id,
                    EmployeeToolCollectionSelectionRow.employee_id == target_value,
                )
                .order_by(EmployeeToolCollectionSelectionRow.collection_id)
            )
            raw_capability_ids = await self._session.scalars(
                select(EmployeeToolGrantRow.capability_id)
                .where(
                    EmployeeToolGrantRow.tenant_id == self._tenant_id,
                    EmployeeToolGrantRow.employee_id == target_value,
                )
                .order_by(EmployeeToolGrantRow.capability_id)
            )
        else:
            raw_collection_ids = await self._session.scalars(
                select(ConversationToolCollectionSelectionRow.collection_id)
                .where(
                    ConversationToolCollectionSelectionRow.tenant_id == self._tenant_id,
                    ConversationToolCollectionSelectionRow.conversation_id == target_value,
                )
                .order_by(ConversationToolCollectionSelectionRow.collection_id)
            )
            raw_capability_ids = await self._session.scalars(
                select(ConversationToolGrantRow.capability_id)
                .where(
                    ConversationToolGrantRow.tenant_id == self._tenant_id,
                    ConversationToolGrantRow.conversation_id == target_value,
                )
                .order_by(ConversationToolGrantRow.capability_id)
            )
        return ToolGrantSnapshot(
            target_type=target_type,
            target_id=target_id,
            collection_ids=tuple(UUID(value) for value in raw_collection_ids),
            capability_ids=tuple(UUID(value) for value in raw_capability_ids),
        )

    async def resolve(self, selection: ToolGrantSelection) -> ToolGrantResolution:
        requested_collections = {str(value) for value in selection.collection_ids}
        found_collections = set(
            await self._session.scalars(
                select(ToolCollectionRow.id).where(
                    ToolCollectionRow.tenant_id == self._tenant_id,
                    ToolCollectionRow.id.in_(requested_collections),
                )
            )
        )
        missing_collections = tuple(
            value for value in selection.collection_ids if str(value) not in found_collections
        )

        selected_sources: set[str] = set()
        if found_collections:
            selected_sources.update(
                await self._session.scalars(
                    select(ToolCollectionSourceRow.source_id).where(
                        ToolCollectionSourceRow.tenant_id == self._tenant_id,
                        ToolCollectionSourceRow.collection_id.in_(found_collections),
                    )
                )
            )

        requested_capabilities = {str(value) for value in selection.capability_ids}
        selectable_ids: set[str] = set()
        if requested_capabilities or selected_sources:
            statement = (
                select(ToolCapabilityRow.id)
                .join(
                    McpSourceRow,
                    (McpSourceRow.tenant_id == ToolCapabilityRow.tenant_id)
                    & (McpSourceRow.id == ToolCapabilityRow.source_id),
                )
                .where(
                    ToolCapabilityRow.tenant_id == self._tenant_id,
                    ToolCapabilityRow.status == ToolCapabilityStatus.ACTIVE.value,
                    McpSourceRow.status == McpSourceStatus.READY.value,
                )
            )
            if requested_capabilities and selected_sources:
                statement = statement.where(
                    (ToolCapabilityRow.id.in_(requested_capabilities))
                    | (ToolCapabilityRow.source_id.in_(selected_sources))
                )
            elif requested_capabilities:
                statement = statement.where(ToolCapabilityRow.id.in_(requested_capabilities))
            else:
                statement = statement.where(ToolCapabilityRow.source_id.in_(selected_sources))
            selectable_ids.update(await self._session.scalars(statement))

        unavailable = tuple(
            value for value in selection.capability_ids if str(value) not in selectable_ids
        )
        return ToolGrantResolution(
            capability_ids=tuple(UUID(value) for value in sorted(selectable_ids)),
            missing_collection_ids=missing_collections,
            unavailable_capability_ids=unavailable,
        )

    async def replace_grants(self, snapshot: ToolGrantSnapshot) -> None:
        target_value = str(snapshot.target_id)
        created_at = to_database_datetime(datetime.now(UTC))
        if snapshot.target_type is ToolGrantTargetType.EMPLOYEE:
            await self._session.execute(
                delete(EmployeeToolCollectionSelectionRow).where(
                    EmployeeToolCollectionSelectionRow.tenant_id == self._tenant_id,
                    EmployeeToolCollectionSelectionRow.employee_id == target_value,
                )
            )
            await self._session.execute(
                delete(EmployeeToolGrantRow).where(
                    EmployeeToolGrantRow.tenant_id == self._tenant_id,
                    EmployeeToolGrantRow.employee_id == target_value,
                )
            )
            self._session.add_all(
                EmployeeToolCollectionSelectionRow(
                    tenant_id=self._tenant_id,
                    employee_id=target_value,
                    collection_id=str(collection_id),
                    created_at=created_at,
                )
                for collection_id in snapshot.collection_ids
            )
            self._session.add_all(
                EmployeeToolGrantRow(
                    tenant_id=self._tenant_id,
                    employee_id=target_value,
                    capability_id=str(capability_id),
                    created_at=created_at,
                )
                for capability_id in snapshot.capability_ids
            )
        else:
            await self._session.execute(
                delete(ConversationToolCollectionSelectionRow).where(
                    ConversationToolCollectionSelectionRow.tenant_id == self._tenant_id,
                    ConversationToolCollectionSelectionRow.conversation_id == target_value,
                )
            )
            await self._session.execute(
                delete(ConversationToolGrantRow).where(
                    ConversationToolGrantRow.tenant_id == self._tenant_id,
                    ConversationToolGrantRow.conversation_id == target_value,
                )
            )
            self._session.add_all(
                ConversationToolCollectionSelectionRow(
                    tenant_id=self._tenant_id,
                    conversation_id=target_value,
                    collection_id=str(collection_id),
                    created_at=created_at,
                )
                for collection_id in snapshot.collection_ids
            )
            self._session.add_all(
                ConversationToolGrantRow(
                    tenant_id=self._tenant_id,
                    conversation_id=target_value,
                    capability_id=str(capability_id),
                    created_at=created_at,
                )
                for capability_id in snapshot.capability_ids
            )
        await self._session.flush()

    async def runtime_capabilities(
        self,
        target: ToolGrantTarget,
        capability_ids: tuple[UUID, ...],
    ) -> ToolRuntimeResolution:
        if not capability_ids:
            return ToolRuntimeResolution(capabilities=())
        requested = tuple(str(value) for value in capability_ids)
        query = select(ToolCapabilityRow, McpSourceRow).join(
            McpSourceRow,
            (McpSourceRow.tenant_id == ToolCapabilityRow.tenant_id)
            & (McpSourceRow.id == ToolCapabilityRow.source_id),
        )
        if target.target_type is ToolGrantTargetType.EMPLOYEE:
            query = query.join(
                EmployeeToolGrantRow,
                (EmployeeToolGrantRow.tenant_id == ToolCapabilityRow.tenant_id)
                & (EmployeeToolGrantRow.capability_id == ToolCapabilityRow.id),
            ).where(EmployeeToolGrantRow.employee_id == str(target.target_id))
        else:
            query = query.join(
                ConversationToolGrantRow,
                (ConversationToolGrantRow.tenant_id == ToolCapabilityRow.tenant_id)
                & (ConversationToolGrantRow.capability_id == ToolCapabilityRow.id),
            ).where(ConversationToolGrantRow.conversation_id == str(target.target_id))
        rows = (
            await self._session.execute(
                query.where(
                    ToolCapabilityRow.tenant_id == self._tenant_id,
                    ToolCapabilityRow.id.in_(requested),
                    ToolCapabilityRow.status == ToolCapabilityStatus.ACTIVE.value,
                    McpSourceRow.status == McpSourceStatus.READY.value,
                )
            )
        ).all()
        by_id = {
            capability_row.id: ToolRuntimeCapability(
                source=_source_to_domain(source_row),
                capability=_capability_to_domain(capability_row),
            )
            for capability_row, source_row in rows
        }
        return ToolRuntimeResolution(
            capabilities=tuple(by_id[value] for value in requested if value in by_id),
            missing_capability_ids=tuple(
                capability_id
                for capability_id in capability_ids
                if str(capability_id) not in by_id
            ),
        )


class SqlAlchemyToolUnitOfWork:
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._repository: ToolRepository | None = None

    @property
    def tools(self) -> ToolRepository:
        if self._repository is None:
            raise RuntimeError("工具目录事务尚未开始")
        return self._repository

    async def __aenter__(self) -> SqlAlchemyToolUnitOfWork:
        if self._context is not None:
            raise RuntimeError("工具目录事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._repository = SqlAlchemyToolRepository(session, self._tenant_id)
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
            raise RuntimeError("工具目录事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("工具目录事务尚未开始")
        await self._session.commit()


class SqlAlchemyToolUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyToolUnitOfWork:
        return SqlAlchemyToolUnitOfWork(self._database, self._tenant_id_provider())


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


def _collection_to_domain(
    row: ToolCollectionRow,
    source_ids: tuple[UUID, ...],
) -> ToolCollection:
    return ToolCollection(
        id=UUID(row.id),
        name=row.name,
        description=row.description,
        source_ids=source_ids,
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )


__all__ = [
    "SqlAlchemyToolRepository",
    "SqlAlchemyToolUnitOfWork",
    "SqlAlchemyToolUnitOfWorkFactory",
]
