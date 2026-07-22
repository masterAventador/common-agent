from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import AbstractAsyncContextManager
from datetime import UTC, datetime
from types import TracebackType
from uuid import UUID

import pytest

from common_agent.ports.external_mcp import ExternalMcpRepository
from common_agent.ports.mcp import McpToolCallError, McpToolCallResponse, McpToolDescriptor
from common_agent.tools.external_mcp import (
    ExternalMcpSnapshot,
    ExternalMcpSourceCommand,
    ExternalMcpSyncResult,
)
from common_agent.tools.external_mcp_service import (
    ExternalMcpService,
    ExternalMcpSyncFailed,
)
from common_agent.tools.models import McpSource, McpSourceStatus

_NOW = datetime(2026, 7, 22, 10, 0, tzinfo=UTC)


class _Repository(ExternalMcpRepository):
    def __init__(self) -> None:
        self.snapshots: dict[UUID, ExternalMcpSnapshot] = {}
        self.cleared_credentials: list[UUID] = []

    async def list_sources(self) -> tuple[ExternalMcpSnapshot, ...]:
        return tuple(self.snapshots.values())

    async def snapshot(
        self,
        source_id: UUID,
        *,
        for_update: bool = False,
    ) -> ExternalMcpSnapshot | None:
        del for_update
        return self.snapshots.get(source_id)

    async def source_name_exists(self, name: str, excluding: UUID | None = None) -> bool:
        return any(
            item.source.name == name and item.source.id != excluding
            for item in self.snapshots.values()
        )

    async def add_source(self, source: McpSource) -> None:
        self.snapshots[source.id] = ExternalMcpSnapshot(source, ())

    async def update_source(self, source: McpSource) -> None:
        current = self.snapshots[source.id]
        self.snapshots[source.id] = ExternalMcpSnapshot(source, current.capabilities)

    async def clear_credential(self, source_id: UUID) -> None:
        self.cleared_credentials.append(source_id)

    async def apply_sync(self, result: ExternalMcpSyncResult) -> None:
        self.snapshots[result.source.id] = ExternalMcpSnapshot(
            result.source,
            result.capabilities,
        )

    async def delete_source(self, source_id: UUID) -> bool:
        self.snapshots.pop(source_id, None)
        return True


class _UnitOfWork(AbstractAsyncContextManager["_UnitOfWork"]):
    def __init__(self, repository: _Repository) -> None:
        self.external_mcp: ExternalMcpRepository = repository
        self.committed = False

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


class _Client:
    def __init__(self) -> None:
        self.list_calls = 0
        self.failure: McpToolCallError | None = None

    async def list_tools(self, source: McpSource) -> tuple[McpToolDescriptor, ...]:
        self.list_calls += 1
        if self.failure is not None:
            raise self.failure
        assert source.endpoint_url == "https://mcp.partner.example/mcp"
        return (
            McpToolDescriptor(
                name="orders.get",
                display_name="查询订单",
                description="按编号查询订单。",
                input_schema={"type": "object", "properties": {}},
            ),
        )

    async def call_tool(
        self,
        source: McpSource,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        del source, name, arguments
        return McpToolCallResponse(output={})


def test_create_is_offline_and_explicit_sync_is_the_only_discovery_boundary() -> None:
    repository = _Repository()
    units: list[_UnitOfWork] = []

    def factory() -> _UnitOfWork:
        unit = _UnitOfWork(repository)
        units.append(unit)
        return unit

    client = _Client()
    service = ExternalMcpService(factory, client, clock=lambda: _NOW)

    async def exercise() -> None:
        created = await service.create_source(
            ExternalMcpSourceCommand(
                name="合作方订单 MCP",
                endpoint_url="https://mcp.partner.example/mcp",
            )
        )
        assert created.source.status is McpSourceStatus.DRAFT
        assert created.capabilities == ()
        assert client.list_calls == 0

        synced = await service.sync_source(created.source.id)
        assert synced.source.status is McpSourceStatus.READY
        assert [item.remote_name for item in synced.capabilities] == ["orders.get"]
        assert synced.added == 1
        assert client.list_calls == 1

    asyncio.run(exercise())

    assert len(units) == 3
    assert units[0].committed is True
    assert units[1].committed is False
    assert units[2].committed is True


def test_failed_sync_marks_only_source_unavailable_and_keeps_last_catalog() -> None:
    repository = _Repository()
    client = _Client()
    service = ExternalMcpService(lambda: _UnitOfWork(repository), client, clock=lambda: _NOW)

    async def exercise() -> None:
        created = await service.create_source(
            ExternalMcpSourceCommand(
                name="合作方订单 MCP",
                endpoint_url="https://mcp.partner.example/mcp",
            )
        )
        synced = await service.sync_source(created.source.id)
        capability_id = synced.capabilities[0].id
        client.failure = McpToolCallError("tool_timeout", retryable=True)

        with pytest.raises(ExternalMcpSyncFailed) as captured:
            await service.sync_source(created.source.id)

        current = await service.snapshot(created.source.id)
        assert captured.value.code == "tool_timeout"
        assert captured.value.retryable is True
        assert current.source.status is McpSourceStatus.UNAVAILABLE
        assert current.capabilities[0].id == capability_id

    asyncio.run(exercise())


def test_endpoint_change_clears_bound_credential_but_metadata_edit_keeps_it() -> None:
    repository = _Repository()
    service = ExternalMcpService(
        lambda: _UnitOfWork(repository),
        _Client(),
        clock=lambda: _NOW,
    )

    async def exercise() -> None:
        created = await service.create_source(
            ExternalMcpSourceCommand(
                name="合作方订单 MCP",
                endpoint_url="https://mcp.partner.example/mcp",
            )
        )
        await service.update_source(
            created.source.id,
            ExternalMcpSourceCommand(
                name="合作方订单 MCP 新名称",
                endpoint_url="https://mcp.partner.example/mcp",
            ),
        )
        assert repository.cleared_credentials == []

        updated = await service.update_source(
            created.source.id,
            ExternalMcpSourceCommand(
                name="合作方订单 MCP 新名称",
                endpoint_url="https://mcp-v2.partner.example/mcp",
            ),
        )
        assert updated.source.status is McpSourceStatus.DRAFT
        assert repository.cleared_credentials == [created.source.id]

    asyncio.run(exercise())
