from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common_agent.ports.mcp import McpToolDescriptor
from common_agent.tools.external_mcp import (
    ExternalMcpSourceCommand,
    ExternalMcpValidationError,
    reconcile_external_capabilities,
)
from common_agent.tools.models import McpSourceStatus, ToolCapability, ToolCapabilityStatus

_NOW = datetime(2026, 7, 22, 9, 0, tzinfo=UTC)
_LATER = datetime(2026, 7, 22, 9, 5, tzinfo=UTC)


def _descriptor(name: str, field_type: str = "string") -> McpToolDescriptor:
    return McpToolDescriptor(
        name=name,
        display_name=f"显示 {name}",
        description=f"说明 {name}",
        input_schema={
            "type": "object",
            "properties": {"value": {"type": field_type}},
            "additionalProperties": False,
        },
    )


def test_external_source_command_creates_draft_without_claiming_network_success() -> None:
    command = ExternalMcpSourceCommand(
        name="外部订单 MCP",
        description="合作方提供的 Streamable HTTP 服务",
        endpoint_url="https://mcp.partner.example/v1/mcp",
    )

    source = command.create(now=_NOW)

    assert source.status is McpSourceStatus.DRAFT
    assert source.endpoint_url == "https://mcp.partner.example/v1/mcp"


def test_explicit_sync_preserves_ids_and_quarantines_schema_drift_for_one_cycle() -> None:
    source = ExternalMcpSourceCommand(
        name="外部订单 MCP",
        endpoint_url="https://mcp.partner.example/mcp",
    ).create(now=_NOW)
    unchanged = ToolCapability.create(
        source_id=source.id,
        remote_name="orders.get",
        display_name="旧查询名称",
        description="旧说明",
        input_schema=_descriptor("orders.get").input_schema,
        capability_id=uuid4(),
        now=_NOW,
    )
    drifted = ToolCapability.create(
        source_id=source.id,
        remote_name="orders.update",
        display_name="更新订单",
        input_schema=_descriptor("orders.update").input_schema,
        capability_id=uuid4(),
        now=_NOW,
    )
    removed = ToolCapability.create(
        source_id=source.id,
        remote_name="orders.remove",
        display_name="删除订单",
        input_schema=_descriptor("orders.remove").input_schema,
        capability_id=uuid4(),
        now=_NOW,
    )

    first = reconcile_external_capabilities(
        source,
        (unchanged, drifted, removed),
        (
            _descriptor("orders.get"),
            _descriptor("orders.update", "integer"),
            _descriptor("orders.create"),
        ),
        now=_LATER,
    )

    by_name = {item.remote_name: item for item in first.capabilities}
    assert by_name["orders.get"].id == unchanged.id
    assert by_name["orders.get"].display_name == "显示 orders.get"
    assert by_name["orders.get"].status is ToolCapabilityStatus.ACTIVE
    assert by_name["orders.update"].id == drifted.id
    assert by_name["orders.update"].status is ToolCapabilityStatus.UNAVAILABLE
    assert by_name["orders.remove"].id == removed.id
    assert by_name["orders.remove"].status is ToolCapabilityStatus.UNAVAILABLE
    assert by_name["orders.create"].status is ToolCapabilityStatus.ACTIVE
    assert first.added == 1
    assert first.schema_changed == 1
    assert first.removed == 1
    assert first.source.status is McpSourceStatus.READY

    confirmed = reconcile_external_capabilities(
        first.source,
        first.capabilities,
        (
            _descriptor("orders.get"),
            _descriptor("orders.update", "integer"),
            _descriptor("orders.create"),
        ),
        now=datetime(2026, 7, 22, 9, 10, tzinfo=UTC),
    )
    confirmed_by_name = {item.remote_name: item for item in confirmed.capabilities}

    assert confirmed_by_name["orders.update"].id == drifted.id
    assert confirmed_by_name["orders.update"].status is ToolCapabilityStatus.ACTIVE
    assert confirmed.reactivated == 1
    assert confirmed_by_name["orders.remove"].status is ToolCapabilityStatus.UNAVAILABLE


def test_sync_rejects_duplicate_remote_names_without_silent_suffixes() -> None:
    source = ExternalMcpSourceCommand(
        name="外部 MCP",
        endpoint_url="https://mcp.partner.example/mcp",
    ).create(now=_NOW)

    with pytest.raises(ExternalMcpValidationError, match="重复"):
        reconcile_external_capabilities(
            source,
            (),
            (_descriptor("same"), _descriptor("same")),
            now=_LATER,
        )


@pytest.mark.parametrize(
    "input_schema",
    (
        {"type": "array", "items": {"type": "string"}},
        {"type": "object", "properties": {"value": {"type": "not-a-type"}}},
    ),
)
def test_sync_rejects_non_object_or_invalid_remote_input_schema(
    input_schema: dict[str, object],
) -> None:
    source = ExternalMcpSourceCommand(
        name="外部 MCP",
        endpoint_url="https://mcp.partner.example/mcp",
    ).create(now=_NOW)
    descriptor = McpToolDescriptor(
        name="unsafe",
        display_name="非法工具",
        description="服务端返回了平台无法安全校验的参数定义",
        input_schema=input_schema,
    )

    with pytest.raises(ExternalMcpValidationError, match="输入 Schema"):
        reconcile_external_capabilities(source, (), (descriptor,), now=_LATER)
