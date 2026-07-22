from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Protocol, cast
from uuid import UUID

from jsonschema import Draft202012Validator
from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_connected_server_and_client_session

from common_agent.ports.mcp import (
    McpToolCallError,
    McpToolCallResponse,
    McpToolDescriptor,
)
from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpRuntimeSnapshot,
)
from common_agent.tools.models import McpSource, McpSourceStatus, ToolCapabilityStatus

_KNOWN_ERROR_CODES = frozenset(
    {
        "tool_capability_unavailable",
        "tool_execution_failed",
        "tool_invalid_arguments",
        "tool_protocol_error",
        "tool_result_unknown",
        "tool_response_too_large",
        "tool_source_unavailable",
        "tool_timeout",
    }
)


class ManagedHttpSnapshotDirectory(Protocol):
    async def snapshot(self, source_id: UUID) -> ManagedHttpRuntimeSnapshot: ...


class ManagedHttpExecutor(Protocol):
    async def execute(
        self,
        source: McpSource,
        capability: ManagedHttpCapability,
        arguments: dict[str, object],
    ) -> dict[str, object]: ...


class ManagedHttpMcpRuntime:
    """Tenant-scoped managed HTTP capabilities exposed through the official MCP SDK."""

    def __init__(
        self,
        directory: ManagedHttpSnapshotDirectory,
        executor: ManagedHttpExecutor,
    ) -> None:
        self._directory = directory
        self._executor = executor

    async def list_tools(self, source_id: UUID) -> Sequence[McpToolDescriptor]:
        snapshot = await self._ready_snapshot(source_id)
        server = self._server(snapshot)
        async with create_connected_server_and_client_session(server) as session:
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
        source_id: UUID,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        snapshot = await self._ready_snapshot(source_id)
        server = self._server(snapshot)
        async with create_connected_server_and_client_session(server) as session:
            result = await session.call_tool(name, dict(arguments))
        if result.isError:
            raise McpToolCallError(_error_code(result.content))
        if not isinstance(result.structuredContent, dict):
            raise McpToolCallError("tool_protocol_error")
        return McpToolCallResponse(output=cast(dict[str, object], result.structuredContent))

    async def _ready_snapshot(self, source_id: UUID) -> ManagedHttpRuntimeSnapshot:
        try:
            snapshot = await self._directory.snapshot(source_id)
        except McpToolCallError:
            raise
        except Exception:
            raise McpToolCallError("tool_source_unavailable") from None
        if snapshot.source.status is not McpSourceStatus.READY:
            raise McpToolCallError("tool_source_unavailable")
        return snapshot

    def _server(self, snapshot: ManagedHttpRuntimeSnapshot) -> Server[object]:
        server: Server[object] = Server(f"common-agent-managed-{snapshot.source.id}")
        active = {
            item.capability.remote_name: item
            for item in snapshot.capabilities
            if item.capability.status is ToolCapabilityStatus.ACTIVE
        }

        @server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name=item.capability.remote_name,
                    title=item.capability.display_name,
                    description=item.capability.description,
                    inputSchema=item.capability.input_schema,
                    outputSchema={"type": "object"},
                )
                for item in active.values()
            ]

        @server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
            capability = active.get(name)
            if capability is None:
                return _error_result("tool_capability_unavailable")
            if not _valid_arguments(capability, arguments):
                return _error_result("tool_invalid_arguments")
            try:
                output = await self._executor.execute(
                    snapshot.source,
                    capability,
                    arguments,
                )
            except McpToolCallError as error:
                return _error_result(
                    error.code if error.code in _KNOWN_ERROR_CODES else "tool_execution_failed"
                )
            except Exception:
                return _error_result("tool_execution_failed")
            if not isinstance(output, dict):
                return _error_result("tool_protocol_error")
            try:
                text = json.dumps(
                    output,
                    ensure_ascii=False,
                    allow_nan=False,
                    separators=(",", ":"),
                )
            except (TypeError, ValueError):
                return _error_result("tool_protocol_error")
            return types.CallToolResult(
                content=[types.TextContent(type="text", text=text)],
                structuredContent=output,
                isError=False,
            )

        return server


def _valid_arguments(
    capability: ManagedHttpCapability,
    arguments: dict[str, object],
) -> bool:
    try:
        return not any(
            Draft202012Validator(capability.capability.input_schema).iter_errors(arguments)
        )
    except Exception:
        return False


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
    "ManagedHttpExecutor",
    "ManagedHttpMcpRuntime",
    "ManagedHttpSnapshotDirectory",
]
