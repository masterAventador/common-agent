from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.agent.platform_tools import PlatformMcpToolRegistry
from common_agent.adapters.mcp.platform import PlatformMcpRuntime
from common_agent.audit import (
    AuditAction,
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditOutcome,
    AuditPage,
    AuditQuery,
    AuditResourceType,
    AuditService,
)
from common_agent.ports.mcp import McpToolCallError, McpToolCallResponse, McpToolDescriptor
from common_agent.tenancy import TenantAccess, TenantRole, bind_tenant
from common_agent.tools import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolGrantTarget,
    ToolGrantTargetType,
    ToolRuntimeCapability,
    platform_tool_catalog_seed,
)
from common_agent.tools.service import ToolCapabilityUnavailable

_TENANT_ID = UUID("10000000-0000-4000-8000-000000000001")
_USER_ID = UUID("20000000-0000-4000-8000-000000000001")
_NOW = datetime(2026, 7, 22, 8, 9, 10, tzinfo=UTC)


class _RuntimeDirectory:
    def __init__(self, target: ToolGrantTarget) -> None:
        seed = platform_tool_catalog_seed(_TENANT_ID)
        self.target = target
        self.capability = ToolRuntimeCapability(seed.source, seed.current_time)
        self.enabled = True
        self.calls: list[tuple[ToolGrantTarget, tuple[UUID, ...]]] = []

    async def authorized_runtime_capabilities(
        self,
        target: ToolGrantTarget,
        capability_ids: tuple[UUID, ...],
    ) -> tuple[ToolRuntimeCapability, ...]:
        self.calls.append((target, capability_ids))
        if (
            not self.enabled
            or target != self.target
            or capability_ids != (self.capability.capability.id,)
        ):
            raise ToolCapabilityUnavailable
        return (self.capability,)


class _AuditStore:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        del retention_until, max_events_per_scope
        self.entries.append(entry)
        return cast(AuditEvent, object())

    async def page(self, query: AuditQuery) -> AuditPage:
        del query
        return AuditPage()

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity:
        del tenant_id
        return cast(AuditIntegrity, object())


class _FailSucceededAuditStore(_AuditStore):
    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        if entry.outcome is AuditOutcome.SUCCEEDED:
            raise RuntimeError("audit unavailable")
        return await super().append(
            entry,
            retention_until=retention_until,
            max_events_per_scope=max_events_per_scope,
        )


@pytest.mark.parametrize(
    "target_type",
    [ToolGrantTargetType.EMPLOYEE, ToolGrantTargetType.CONVERSATION],
)
def test_platform_tool_uses_real_mcp_and_rechecks_exact_grant(
    target_type: ToolGrantTargetType,
) -> None:
    target = ToolGrantTarget(target_type, uuid4())
    directory = _RuntimeDirectory(target)
    audit = _AuditStore()
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        audit=AuditService(audit),
    )

    async def exercise() -> str:
        tools = await registry.resolve(
            (directory.capability.capability.id,),
            target=target,
        )
        assert len(tools) == 1
        return cast(str, await tools[0].ainvoke({"utc_offset": "+08:00"}))

    with bind_tenant(TenantAccess(_TENANT_ID, _USER_ID, TenantRole.EDITOR)):
        result = asyncio.run(exercise())

    assert result == (
        '{"iso8601":"2026-07-22T16:09:10+08:00",'
        '"unix_timestamp":1784707750,"utc_offset":"+08:00"}'
    )
    assert directory.calls == [
        (target, (directory.capability.capability.id,)),
        (target, (directory.capability.capability.id,)),
    ]
    assert [entry.action for entry in audit.entries] == [
        AuditAction.TOOL_CALLED,
        AuditAction.TOOL_CALLED,
    ]
    assert [entry.outcome for entry in audit.entries] == [
        AuditOutcome.STARTED,
        AuditOutcome.SUCCEEDED,
    ]
    assert all(entry.resource_type is AuditResourceType.TOOL_CAPABILITY for entry in audit.entries)
    assert all(
        entry.resource_id == str(directory.capability.capability.id) for entry in audit.entries
    )


def test_platform_tool_denies_a_grant_removed_after_resolution() -> None:
    target = ToolGrantTarget(ToolGrantTargetType.EMPLOYEE, uuid4())
    directory = _RuntimeDirectory(target)
    audit = _AuditStore()
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        audit=AuditService(audit),
    )

    async def exercise() -> str:
        tools = await registry.resolve(
            (directory.capability.capability.id,),
            target=target,
        )
        directory.enabled = False
        return cast(str, await tools[0].ainvoke({"utc_offset": "+08:00"}))

    with bind_tenant(TenantAccess(_TENANT_ID, _USER_ID, TenantRole.EDITOR)):
        result = asyncio.run(exercise())

    assert result == "工具调用失败,错误码:tool_unauthorized"
    assert [entry.outcome for entry in audit.entries] == [
        AuditOutcome.STARTED,
        AuditOutcome.DENIED,
    ]
    assert audit.entries[-1].error_code == "tool_unauthorized"


class _ManagedDirectory:
    def __init__(self, target: ToolGrantTarget) -> None:
        source = McpSource.create(
            name="订单系统",
            source_type=McpSourceType.MANAGED_HTTP,
            endpoint_url="https://business.example/api",
            status=McpSourceStatus.READY,
        )
        capability = ToolCapability.create(
            source_id=source.id,
            remote_name="orders.get",
            display_name="查询订单",
            description="按编号查询订单。",
            input_schema={
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单编号"},
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
        )
        self.target = target
        self.capability = ToolRuntimeCapability(source, capability)
        self.enabled = True
        self.calls = 0

    async def authorized_runtime_capabilities(
        self,
        target: ToolGrantTarget,
        capability_ids: tuple[UUID, ...],
    ) -> tuple[ToolRuntimeCapability, ...]:
        self.calls += 1
        if (
            not self.enabled
            or target != self.target
            or capability_ids != (self.capability.capability.id,)
        ):
            raise ToolCapabilityUnavailable
        return (self.capability,)


class _ManagedMcp:
    def __init__(self, capability: ToolRuntimeCapability) -> None:
        self.capability = capability
        self.calls: list[tuple[UUID, str, dict[str, object]]] = []

    async def list_tools(self, source_id: UUID) -> tuple[McpToolDescriptor, ...]:
        assert source_id == self.capability.source.id
        tool = self.capability.capability
        return (
            McpToolDescriptor(
                name=tool.remote_name,
                display_name=tool.display_name,
                description=tool.description,
                input_schema=tool.input_schema,
            ),
        )

    async def call_tool(
        self,
        source_id: UUID,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        self.calls.append((source_id, name, dict(arguments)))
        return McpToolCallResponse(output={"id": arguments["order_id"]})


class _UnknownResultManagedMcp(_ManagedMcp):
    async def call_tool(
        self,
        source_id: UUID,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        self.calls.append((source_id, name, dict(arguments)))
        raise McpToolCallError("tool_result_unknown", retryable=False)


def test_managed_http_tool_is_namespaced_and_rechecks_exact_grant() -> None:
    target = ToolGrantTarget(ToolGrantTargetType.CONVERSATION, uuid4())
    directory = _ManagedDirectory(target)
    managed_mcp = _ManagedMcp(directory.capability)
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        managed_mcp=managed_mcp,
    )

    async def exercise() -> str:
        tools = await registry.resolve(
            (directory.capability.capability.id,),
            target=target,
        )
        assert tools[0].name.startswith("orders.get__")
        return cast(str, await tools[0].ainvoke({"order_id": "A-100"}))

    result = asyncio.run(exercise())

    assert result == '{"id":"A-100"}'
    assert directory.calls == 2
    assert managed_mcp.calls == [
        (
            directory.capability.source.id,
            "orders.get",
            {"order_id": "A-100"},
        )
    ]


def test_result_unknown_latches_tool_and_prevents_same_turn_replay() -> None:
    target = ToolGrantTarget(ToolGrantTargetType.CONVERSATION, uuid4())
    directory = _ManagedDirectory(target)
    managed_mcp = _UnknownResultManagedMcp(directory.capability)
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        managed_mcp=managed_mcp,
    )

    async def exercise() -> tuple[str, str]:
        tools = await registry.resolve(
            (directory.capability.capability.id,),
            target=target,
        )
        first = cast(str, await tools[0].ainvoke({"order_id": "A-100"}))
        second = cast(str, await tools[0].ainvoke({"order_id": "A-100"}))
        return first, second

    assert asyncio.run(exercise()) == (
        "工具调用失败,错误码:tool_result_unknown",
        "工具调用失败,错误码:tool_result_unknown",
    )
    assert len(managed_mcp.calls) == 1


def test_duplicate_provider_tool_call_id_is_coalesced_before_mcp_dispatch() -> None:
    target = ToolGrantTarget(ToolGrantTargetType.CONVERSATION, uuid4())
    directory = _ManagedDirectory(target)
    managed_mcp = _ManagedMcp(directory.capability)
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        managed_mcp=managed_mcp,
    )

    async def exercise() -> None:
        tool = (
            await registry.resolve(
                (directory.capability.capability.id,),
                target=target,
            )
        )[0]
        call = {
            "type": "tool_call",
            "id": "provider-duplicate-id",
            "name": tool.name,
            "args": {"order_id": "A-100"},
        }
        first, second = await asyncio.gather(
            tool.ainvoke(dict(call)),
            tool.ainvoke(dict(call)),
        )
        assert first == second

    asyncio.run(exercise())

    assert len(managed_mcp.calls) == 1


def test_audit_failure_after_remote_result_latches_result_unknown() -> None:
    target = ToolGrantTarget(ToolGrantTargetType.CONVERSATION, uuid4())
    directory = _ManagedDirectory(target)
    managed_mcp = _ManagedMcp(directory.capability)
    audit = _FailSucceededAuditStore()
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        managed_mcp=managed_mcp,
        audit=AuditService(audit),
    )

    async def exercise() -> tuple[str, str]:
        tool = (
            await registry.resolve(
                (directory.capability.capability.id,),
                target=target,
            )
        )[0]
        first = cast(str, await tool.ainvoke({"order_id": "A-100"}))
        second = cast(str, await tool.ainvoke({"order_id": "A-100"}))
        return first, second

    with bind_tenant(TenantAccess(_TENANT_ID, _USER_ID, TenantRole.EDITOR)):
        assert asyncio.run(exercise()) == (
            "工具调用失败,错误码:tool_result_unknown",
            "工具调用失败,错误码:tool_result_unknown",
        )

    assert len(managed_mcp.calls) == 1
    assert [entry.outcome for entry in audit.entries] == [
        AuditOutcome.STARTED,
        AuditOutcome.FAILED,
        AuditOutcome.STARTED,
        AuditOutcome.FAILED,
    ]


class _ExternalDirectory(_ManagedDirectory):
    def __init__(self, target: ToolGrantTarget) -> None:
        super().__init__(target)
        source = McpSource.create(
            name="合作方订单",
            source_type=McpSourceType.EXTERNAL,
            endpoint_url="https://mcp.partner.example/mcp",
            status=McpSourceStatus.READY,
        )
        capability = ToolCapability.create(
            source_id=source.id,
            remote_name="orders.get",
            display_name="查询合作方订单",
            description="按编号查询合作方订单。",
            input_schema=self.capability.capability.input_schema,
        )
        self.capability = ToolRuntimeCapability(source, capability)


class _ExternalMcp:
    def __init__(self, capability: ToolRuntimeCapability) -> None:
        self.capability = capability
        self.calls: list[tuple[McpSource, str, dict[str, object]]] = []

    async def list_tools(self, source: McpSource) -> tuple[McpToolDescriptor, ...]:
        assert source == self.capability.source
        capability = self.capability.capability
        return (
            McpToolDescriptor(
                name=capability.remote_name,
                display_name=capability.display_name,
                description=capability.description,
                input_schema=capability.input_schema,
            ),
        )

    async def call_tool(
        self,
        source: McpSource,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        self.calls.append((source, name, dict(arguments)))
        return McpToolCallResponse(output={"id": arguments["order_id"]})


def test_external_mcp_tool_rechecks_exact_grant_and_uses_current_source_snapshot() -> None:
    target = ToolGrantTarget(ToolGrantTargetType.EMPLOYEE, uuid4())
    directory = _ExternalDirectory(target)
    external_mcp = _ExternalMcp(directory.capability)
    registry = PlatformMcpToolRegistry(
        directory,
        PlatformMcpRuntime(clock=lambda: _NOW),
        external_mcp=external_mcp,
    )

    async def exercise() -> str:
        tools = await registry.resolve(
            (directory.capability.capability.id,),
            target=target,
        )
        assert tools[0].name.startswith("orders.get__")
        return cast(str, await tools[0].ainvoke({"order_id": "P-100"}))

    assert asyncio.run(exercise()) == '{"id":"P-100"}'
    assert external_mcp.calls == [
        (
            directory.capability.source,
            "orders.get",
            {"order_id": "P-100"},
        )
    ]
