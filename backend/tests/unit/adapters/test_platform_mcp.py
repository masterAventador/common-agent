from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from common_agent.adapters.mcp.platform import (
    CURRENT_TIME_TOOL_NAME,
    PlatformMcpRuntime,
)
from common_agent.ports.mcp import McpToolCallError


def test_platform_mcp_lists_and_calls_current_time_over_the_protocol() -> None:
    runtime = PlatformMcpRuntime(
        clock=lambda: datetime(2026, 7, 22, 8, 9, 10, tzinfo=UTC)
    )

    async def exercise() -> None:
        tools = await runtime.list_tools()
        assert [tool.name for tool in tools] == [CURRENT_TIME_TOOL_NAME]
        assert tools[0].input_schema["additionalProperties"] is False

        result = await runtime.call_tool(
            CURRENT_TIME_TOOL_NAME,
            {"utc_offset": "+08:00"},
        )
        assert result.output == {
            "iso8601": "2026-07-22T16:09:10+08:00",
            "unix_timestamp": 1784707750,
            "utc_offset": "+08:00",
        }

    asyncio.run(exercise())


@pytest.mark.parametrize("offset", ["Asia/Shanghai", "+15:00", "+14:01", "+08:60"])
def test_platform_mcp_rejects_invalid_time_offsets_without_falling_back(offset: str) -> None:
    runtime = PlatformMcpRuntime(
        clock=lambda: datetime(2026, 7, 22, 8, 9, 10, tzinfo=UTC)
    )

    with pytest.raises(McpToolCallError, match="tool_invalid_arguments"):
        asyncio.run(runtime.call_tool(CURRENT_TIME_TOOL_NAME, {"utc_offset": offset}))


def test_platform_mcp_rejects_unknown_tools_and_arguments() -> None:
    runtime = PlatformMcpRuntime(
        clock=lambda: datetime(2026, 7, 22, 8, 9, 10, tzinfo=UTC)
    )

    with pytest.raises(McpToolCallError, match="tool_capability_unavailable"):
        asyncio.run(runtime.call_tool("unknown", {}))
    with pytest.raises(McpToolCallError, match="tool_invalid_arguments"):
        asyncio.run(runtime.call_tool(CURRENT_TIME_TOOL_NAME, {"extra": True}))
