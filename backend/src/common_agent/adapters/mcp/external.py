from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Protocol, cast
from uuid import UUID

import httpx
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from common_agent.adapters.security import (
    OutboundAccessPolicy,
    OutboundSecurityError,
    SafeOutboundHttpClient,
)
from common_agent.bootstrap import ToolEgressSettings
from common_agent.ports.mcp import (
    McpToolCallError,
    McpToolCallResponse,
    McpToolDescriptor,
)
from common_agent.tools.credentials import McpCredential
from common_agent.tools.external_mcp import EXTERNAL_MCP_MAX_TOOLS
from common_agent.tools.models import McpSource, McpSourceStatus, McpSourceType

from .outbound import credential_headers, egress_error_code

_MAX_LIST_PAGES = 100


class ExternalMcpCredentialResolver(Protocol):
    async def resolve(self, source_id: UUID) -> McpCredential | None: ...


class ExternalMcpHttpClient(Protocol):
    def stream_client(
        self,
        *,
        headers: Mapping[str, str] | None = None,
    ) -> AbstractAsyncContextManager[httpx.AsyncClient]: ...

    async def aclose(self) -> None: ...


class ExternalMcpHttpClientFactory(Protocol):
    def create(self, endpoint_url: str) -> ExternalMcpHttpClient: ...


class SafeExternalMcpHttpClientFactory:
    def __init__(self, settings: ToolEgressSettings) -> None:
        self._settings = settings
        self._policy = OutboundAccessPolicy(
            allowed_hosts=settings.allowed_hosts,
            allowed_cidrs=settings.allowed_cidrs,
            http_allowed_hosts=settings.http_allowed_hosts,
            allow_loopback=settings.allow_loopback,
        )
        self._semaphore = asyncio.Semaphore(settings.maximum_concurrency)

    def create(self, endpoint_url: str) -> SafeOutboundHttpClient:
        return SafeOutboundHttpClient(
            endpoint_url=endpoint_url,
            policy=self._policy,
            connect_timeout_seconds=self._settings.connect_timeout_seconds,
            read_timeout_seconds=self._settings.read_timeout_seconds,
            call_timeout_seconds=self._settings.call_timeout_seconds,
            maximum_response_bytes=self._settings.maximum_response_bytes,
            maximum_concurrency=self._settings.maximum_concurrency,
            concurrency_semaphore=self._semaphore,
        )


class ExternalMcpRuntime:
    """Official Streamable HTTP MCP client behind the platform egress policy."""

    def __init__(
        self,
        credentials: ExternalMcpCredentialResolver,
        clients: ExternalMcpHttpClientFactory,
    ) -> None:
        self._credentials = credentials
        self._clients = clients

    async def list_tools(self, source: McpSource) -> Sequence[McpToolDescriptor]:
        descriptors: list[McpToolDescriptor] = []
        cursors: set[str] = set()
        try:
            async with self._session(source) as session:
                cursor: str | None = None
                for _ in range(_MAX_LIST_PAGES):
                    result = await session.list_tools(cursor=cursor)
                    descriptors.extend(_descriptor(tool) for tool in result.tools)
                    if len(descriptors) > EXTERNAL_MCP_MAX_TOOLS:
                        raise McpToolCallError("tool_protocol_error")
                    cursor = result.nextCursor
                    if cursor is None:
                        break
                    if cursor in cursors:
                        raise McpToolCallError("tool_protocol_error")
                    cursors.add(cursor)
                else:
                    raise McpToolCallError("tool_protocol_error")
        except McpToolCallError:
            raise
        except OutboundSecurityError as error:
            raise McpToolCallError(
                egress_error_code(error),
                retryable=error.retryable,
            ) from None
        except Exception:
            raise McpToolCallError("tool_source_unavailable", retryable=True) from None
        if len({item.name for item in descriptors}) != len(descriptors):
            raise McpToolCallError("tool_protocol_error")
        return tuple(descriptors)

    async def call_tool(
        self,
        source: McpSource,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        if source.status is not McpSourceStatus.READY:
            raise McpToolCallError("tool_source_unavailable")
        try:
            async with self._session(source) as session:
                result = await session.call_tool(name, dict(arguments))
        except McpToolCallError:
            raise
        except OutboundSecurityError as error:
            raise McpToolCallError(
                egress_error_code(error),
                retryable=error.retryable,
            ) from None
        except Exception:
            raise McpToolCallError("tool_source_unavailable", retryable=True) from None
        if result.isError:
            raise McpToolCallError("tool_execution_failed")
        return McpToolCallResponse(output=_result_output(result))

    @asynccontextmanager
    async def _session(self, source: McpSource) -> AsyncIterator[ClientSession]:
        if source.source_type is not McpSourceType.EXTERNAL or source.endpoint_url is None:
            raise McpToolCallError("tool_source_unavailable")
        try:
            credential = await self._credentials.resolve(source.id)
        except Exception:
            raise McpToolCallError("tool_source_unavailable") from None
        headers = credential_headers({}, credential)
        client = self._clients.create(source.endpoint_url)
        try:
            async with (
                client.stream_client(headers=headers) as http_client,
                streamable_http_client(
                    source.endpoint_url,
                    http_client=http_client,
                ) as (read_stream, write_stream, _),
                ClientSession(read_stream, write_stream) as session,
            ):
                await session.initialize()
                yield session
        finally:
            await client.aclose()


def _descriptor(tool: types.Tool) -> McpToolDescriptor:
    try:
        return McpToolDescriptor(
            name=tool.name,
            display_name=tool.title or tool.name,
            description=tool.description or "",
            input_schema=cast(dict[str, object], tool.inputSchema),
        )
    except (TypeError, ValueError):
        raise McpToolCallError("tool_protocol_error") from None


def _result_output(result: types.CallToolResult) -> dict[str, object]:
    if isinstance(result.structuredContent, dict):
        return cast(dict[str, object], result.structuredContent)
    texts = [item.text for item in result.content if isinstance(item, types.TextContent)]
    if len(texts) == 1:
        try:
            parsed = json.loads(texts[0])
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return cast(dict[str, object], parsed)
    if texts and len(texts) == len(result.content):
        return {"content": "\n".join(texts)}
    raise McpToolCallError("tool_protocol_error")


__all__ = [
    "ExternalMcpCredentialResolver",
    "ExternalMcpHttpClient",
    "ExternalMcpHttpClientFactory",
    "ExternalMcpRuntime",
    "SafeExternalMcpHttpClientFactory",
]
