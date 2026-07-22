from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.mcp.managed_http import ManagedHttpMcpRuntime
from common_agent.ports.mcp import McpToolCallError
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


def _managed_capability(
    source_id: UUID,
    *,
    name: str = "orders.get",
    status: ToolCapabilityStatus = ToolCapabilityStatus.ACTIVE,
) -> ManagedHttpCapability:
    capability = ToolCapability.create(
        source_id=source_id,
        remote_name=name,
        display_name="查询订单",
        description="按订单编号查询订单。",
        status=status,
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单编号"},
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
    )
    return ManagedHttpCapability(
        capability=capability,
        method="GET",
        path_template="/orders/{order_id}",
        parameter_bindings=(
            ManagedHttpParameterBinding(
                argument_name="order_id",
                location=ManagedHttpParameterLocation.PATH,
                target_name="order_id",
            ),
        ),
        timeout_seconds=10,
    )


class _Directory:
    def __init__(self, snapshot: ManagedHttpRuntimeSnapshot) -> None:
        self.snapshot_value = snapshot

    async def snapshot(self, source_id: UUID) -> ManagedHttpRuntimeSnapshot:
        assert source_id == self.snapshot_value.source.id
        return self.snapshot_value


class _Executor:
    def __init__(self) -> None:
        self.calls: list[tuple[UUID, dict[str, object]]] = []

    async def execute(
        self,
        source: McpSource,
        capability: ManagedHttpCapability,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        self.calls.append((capability.capability.id, arguments))
        return {"id": arguments["order_id"], "source": source.name}


def test_managed_http_mcp_discovers_and_calls_only_active_capabilities_over_protocol() -> None:
    source = McpSource.create(
        name="订单系统",
        description="订单查询能力",
        source_type=McpSourceType.MANAGED_HTTP,
        endpoint_url="https://business.example/api",
        status=McpSourceStatus.READY,
    )
    active = _managed_capability(source.id)
    disabled = _managed_capability(
        source.id,
        name="orders.delete",
        status=ToolCapabilityStatus.DISABLED,
    )
    executor = _Executor()
    runtime = ManagedHttpMcpRuntime(
        _Directory(
            ManagedHttpRuntimeSnapshot(
                source=source,
                capabilities=(active, disabled),
            )
        ),
        executor,
    )

    async def exercise() -> None:
        descriptors = await runtime.list_tools(source.id)
        assert [descriptor.name for descriptor in descriptors] == ["orders.get"]
        assert descriptors[0].input_schema == active.capability.input_schema

        result = await runtime.call_tool(
            source.id,
            "orders.get",
            {"order_id": "A-100"},
        )
        assert result.output == {"id": "A-100", "source": "订单系统"}

    asyncio.run(exercise())
    assert executor.calls == [(active.capability.id, {"order_id": "A-100"})]


def test_managed_http_mcp_rejects_unknown_disabled_and_invalid_calls() -> None:
    source = McpSource.create(
        name="订单系统",
        source_type=McpSourceType.MANAGED_HTTP,
        endpoint_url="https://business.example/api",
        status=McpSourceStatus.READY,
    )
    active = _managed_capability(source.id)
    disabled = _managed_capability(
        source.id,
        name="orders.delete",
        status=ToolCapabilityStatus.DISABLED,
    )
    runtime = ManagedHttpMcpRuntime(
        _Directory(ManagedHttpRuntimeSnapshot(source, (active, disabled))),
        _Executor(),
    )

    with pytest.raises(McpToolCallError, match="tool_capability_unavailable"):
        asyncio.run(runtime.call_tool(source.id, "orders.delete", {"order_id": "A-100"}))
    with pytest.raises(McpToolCallError, match="tool_capability_unavailable"):
        asyncio.run(runtime.call_tool(source.id, "unknown", {}))
    with pytest.raises(McpToolCallError, match="tool_invalid_arguments"):
        asyncio.run(runtime.call_tool(source.id, "orders.get", {"extra": str(uuid4())}))


def test_managed_http_mcp_fails_closed_when_source_is_not_ready() -> None:
    source = McpSource.create(
        name="订单系统",
        source_type=McpSourceType.MANAGED_HTTP,
        endpoint_url="https://business.example/api",
        status=McpSourceStatus.DISABLED,
    )
    runtime = ManagedHttpMcpRuntime(
        _Directory(
            ManagedHttpRuntimeSnapshot(source, (_managed_capability(source.id),))
        ),
        _Executor(),
    )

    with pytest.raises(McpToolCallError, match="tool_source_unavailable"):
        asyncio.run(runtime.list_tools(source.id))

