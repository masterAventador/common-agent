from __future__ import annotations

import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime, timedelta, timezone
from typing import cast

from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_connected_server_and_client_session

from common_agent.ports.mcp import (
    McpToolCallError,
    McpToolCallResponse,
    McpToolDescriptor,
)
from common_agent.tools.platform import (
    CURRENT_TIME_DESCRIPTION,
    CURRENT_TIME_DISPLAY_NAME,
    CURRENT_TIME_INPUT_SCHEMA,
    CURRENT_TIME_OUTPUT_SCHEMA,
    CURRENT_TIME_TOOL_NAME,
)

_OFFSET_PATTERN = re.compile(r"^(?P<sign>[+-])(?P<hours>\d{2}):(?P<minutes>\d{2})$")
_KNOWN_ERROR_CODES = frozenset(
    {
        "tool_capability_unavailable",
        "tool_execution_failed",
        "tool_invalid_arguments",
        "tool_protocol_error",
    }
)


class PlatformMcpRuntime:
    """Platform-owned MCP server and client connected through the actual MCP protocol."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._server: Server[object] = Server("common-agent-platform")
        self._register_handlers()

    async def list_tools(self) -> Sequence[McpToolDescriptor]:
        async with create_connected_server_and_client_session(self._server) as session:
            result = await session.list_tools()
        return tuple(
            McpToolDescriptor(
                name=tool.name,
                display_name=tool.title or tool.name,
                description=tool.description or "",
                input_schema=cast(dict[str, object], tool.inputSchema),
            )
            for tool in result.tools
        )

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        async with create_connected_server_and_client_session(self._server) as session:
            result = await session.call_tool(name, dict(arguments))
        if result.isError:
            code = _error_code(result.content)
            raise McpToolCallError(code)
        if not isinstance(result.structuredContent, dict):
            raise McpToolCallError("tool_protocol_error")
        return McpToolCallResponse(output=cast(dict[str, object], result.structuredContent))

    def _register_handlers(self) -> None:
        # MCP SDK 1.x decorators do not publish complete typing metadata.
        @self._server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name=CURRENT_TIME_TOOL_NAME,
                    title=CURRENT_TIME_DISPLAY_NAME,
                    description=CURRENT_TIME_DESCRIPTION,
                    inputSchema=CURRENT_TIME_INPUT_SCHEMA,
                    outputSchema=CURRENT_TIME_OUTPUT_SCHEMA,
                )
            ]

        @self._server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
            if name != CURRENT_TIME_TOOL_NAME:
                return _error_result("tool_capability_unavailable")
            try:
                output = self._current_time(arguments)
            except ValueError:
                return _error_result("tool_invalid_arguments")
            except Exception:
                return _error_result("tool_execution_failed")
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=str(output["iso8601"]),
                    )
                ],
                structuredContent=output,
                isError=False,
            )

    def _current_time(self, arguments: Mapping[str, object]) -> dict[str, object]:
        if set(arguments) - {"utc_offset"}:
            raise ValueError("unexpected current-time argument")
        raw_offset = arguments.get("utc_offset", "+08:00")
        if not isinstance(raw_offset, str):
            raise ValueError("invalid current-time offset")
        offset = _utc_offset(raw_offset)
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise RuntimeError("platform clock must be timezone-aware")
        utc_now = now.astimezone(UTC)
        return {
            "iso8601": utc_now.astimezone(offset).isoformat(timespec="seconds"),
            "unix_timestamp": int(utc_now.timestamp()),
            "utc_offset": raw_offset,
        }


def _utc_offset(value: str) -> timezone:
    match = _OFFSET_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError("invalid UTC offset")
    hours = int(match.group("hours"))
    minutes = int(match.group("minutes"))
    if hours > 14 or minutes > 59 or (hours == 14 and minutes != 0):
        raise ValueError("invalid UTC offset")
    total_minutes = hours * 60 + minutes
    if match.group("sign") == "-":
        total_minutes = -total_minutes
    return timezone(timedelta(minutes=total_minutes))


def _error_result(code: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=code)],
        isError=True,
    )


def _error_code(content: Sequence[types.ContentBlock]) -> str:
    if len(content) == 1 and isinstance(content[0], types.TextContent):
        candidate = content[0].text
        if candidate in _KNOWN_ERROR_CODES:
            return candidate
    return "tool_protocol_error"


__all__ = [
    "CURRENT_TIME_DESCRIPTION",
    "CURRENT_TIME_DISPLAY_NAME",
    "CURRENT_TIME_INPUT_SCHEMA",
    "CURRENT_TIME_OUTPUT_SCHEMA",
    "CURRENT_TIME_TOOL_NAME",
    "PlatformMcpRuntime",
]
