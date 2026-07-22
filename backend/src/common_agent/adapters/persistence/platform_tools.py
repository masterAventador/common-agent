from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.mysql import insert

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import McpSourceRow, ToolCapabilityRow
from common_agent.adapters.persistence.timestamps import to_database_datetime
from common_agent.tools.models import McpSource, ToolCapability
from common_agent.tools.platform import platform_tool_catalog_seed


class SqlAlchemyPlatformToolSeeder:
    """Idempotently materialize platform-owned MCP definitions for every tenant."""

    def __init__(self, database: Database) -> None:
        self._database = database

    async def seed_all(self, tenant_ids: Iterable[UUID]) -> None:
        for tenant_id in tuple(tenant_ids):
            await self.seed(tenant_id)

    async def seed(self, tenant_id: UUID) -> None:
        catalog = platform_tool_catalog_seed(tenant_id)
        source = catalog.source
        capability = catalog.current_time
        now = to_database_datetime(datetime.now(UTC))
        async with self._database.session() as session:
            source_insert = insert(McpSourceRow).values(
                id=str(source.id),
                tenant_id=str(tenant_id),
                name=source.name,
                description=source.description,
                source_type=source.source_type.value,
                endpoint_url=source.endpoint_url,
                status=source.status.value,
                created_at=now,
                updated_at=now,
            )
            await session.execute(
                source_insert.on_duplicate_key_update(id=McpSourceRow.id)
            )
            capability_insert = insert(ToolCapabilityRow).values(
                id=str(capability.id),
                tenant_id=str(tenant_id),
                source_id=str(source.id),
                remote_name=capability.remote_name,
                display_name=capability.display_name,
                description=capability.description,
                input_schema=capability.input_schema,
                schema_fingerprint=capability.schema_fingerprint,
                status=capability.status.value,
                created_at=now,
                updated_at=now,
            )
            await session.execute(
                capability_insert.on_duplicate_key_update(id=ToolCapabilityRow.id)
            )
            source_row = await session.scalar(
                select(McpSourceRow).where(McpSourceRow.id == str(source.id)).with_for_update()
            )
            capability_row = await session.scalar(
                select(ToolCapabilityRow)
                .where(ToolCapabilityRow.id == str(capability.id))
                .with_for_update()
            )
            if source_row is None or capability_row is None:
                raise RuntimeError("平台 MCP 目录初始化失败")
            if source_row.tenant_id != str(tenant_id) or capability_row.tenant_id != str(tenant_id):
                raise RuntimeError("平台 MCP 稳定 ID 与其他租户冲突")
            source_changed = _update_source(source_row, source)
            capability_changed = _update_capability(capability_row, capability)
            if source_changed:
                source_row.updated_at = now
            if capability_changed:
                capability_row.updated_at = now
            await session.commit()


def _update_source(row: McpSourceRow, expected: McpSource) -> bool:
    catalog = expected
    changes = {
        "name": catalog.name,
        "description": catalog.description,
        "source_type": catalog.source_type.value,
        "endpoint_url": catalog.endpoint_url,
        "status": catalog.status.value,
    }
    changed = False
    for field_name, value in changes.items():
        if getattr(row, field_name) != value:
            setattr(row, field_name, value)
            changed = True
    return changed


def _update_capability(row: ToolCapabilityRow, expected: ToolCapability) -> bool:
    capability = expected
    changes = {
        "source_id": str(capability.source_id),
        "remote_name": capability.remote_name,
        "display_name": capability.display_name,
        "description": capability.description,
        "input_schema": capability.input_schema,
        "schema_fingerprint": capability.schema_fingerprint,
        "status": capability.status.value,
    }
    changed = False
    for field_name, value in changes.items():
        if getattr(row, field_name) != value:
            setattr(row, field_name, value)
            changed = True
    return changed


__all__ = ["SqlAlchemyPlatformToolSeeder"]
