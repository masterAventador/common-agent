from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import AsyncIterator, Iterator, Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import replace
from ipaddress import ip_network
from typing import cast

import pytest
import uvicorn
from mcp import ClientSession, types
from mcp.server.fastmcp import FastMCP

from common_agent.adapters.mcp.external import (
    ExternalMcpRuntime,
    SafeExternalMcpHttpClientFactory,
)
from common_agent.bootstrap import ToolEgressSettings
from common_agent.ports.mcp import McpToolCallError
from common_agent.tools.models import McpSource, McpSourceStatus, McpSourceType


class _NoCredentials:
    async def resolve(self, source_id: object) -> None:
        del source_id
        return None


@contextmanager
def _real_mcp_server() -> Iterator[str]:
    mcp = FastMCP(
        "外部订单测试",
        stateless_http=True,
        json_response=True,
    )

    @mcp.tool(title="查询订单", description="按编号查询订单。", structured_output=True)
    def orders_get(order_id: str) -> dict[str, object]:
        return {"id": order_id, "status": "paid"}

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    server = uvicorn.Server(
        uvicorn.Config(
            mcp.streamable_http_app(),
            host="127.0.0.1",
            port=port,
            log_level="error",
        )
    )
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    if not server.started:
        raise RuntimeError("测试 MCP 服务启动失败")
    try:
        yield f"http://127.0.0.1:{port}/mcp"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


def test_external_runtime_uses_real_streamable_http_for_list_and_call() -> None:
    settings = ToolEgressSettings(
        allowed_hosts=("127.0.0.1",),
        allowed_cidrs=(ip_network("127.0.0.0/8"),),
        http_allowed_hosts=("127.0.0.1",),
        allow_loopback=True,
        connect_timeout_seconds=2,
        read_timeout_seconds=2,
        call_timeout_seconds=5,
        maximum_response_bytes=64 * 1024,
        maximum_concurrency=2,
    )
    runtime = ExternalMcpRuntime(
        _NoCredentials(),
        SafeExternalMcpHttpClientFactory(settings),
    )

    with _real_mcp_server() as endpoint:
        source = McpSource.create(
            name="外部订单 MCP",
            source_type=McpSourceType.EXTERNAL,
            endpoint_url=endpoint,
            status=McpSourceStatus.DRAFT,
        )

        async def exercise() -> None:
            tools = await runtime.list_tools(source)
            assert len(tools) == 1
            assert tools[0].name == "orders_get"
            assert tools[0].display_name == "查询订单"
            properties = tools[0].input_schema["properties"]
            assert isinstance(properties, dict)
            assert "order_id" in properties

            result = await runtime.call_tool(
                replace(source, status=McpSourceStatus.READY),
                "orders_get",
                {"order_id": "A-100"},
            )
            assert result.output == {"id": "A-100", "status": "paid"}

        asyncio.run(exercise())


class _CallDisconnectSession:
    def __init__(self) -> None:
        self.calls = 0

    async def call_tool(self, name: str, arguments: Mapping[str, object]) -> object:
        del name, arguments
        self.calls += 1
        raise RuntimeError("connection lost after the tool may have executed")


class _CallDisconnectRuntime(ExternalMcpRuntime):
    def __init__(self, session: _CallDisconnectSession) -> None:
        super().__init__(_NoCredentials(), cast(SafeExternalMcpHttpClientFactory, object()))
        self.session = session

    @asynccontextmanager
    async def _session(self, source: McpSource) -> AsyncIterator[ClientSession]:
        del source
        yield cast(ClientSession, self.session)


class _MalformedResultSession(_CallDisconnectSession):
    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> types.CallToolResult:
        del name, arguments
        self.calls += 1
        return types.CallToolResult(content=[], isError=False)


class _SessionUnavailableRuntime(ExternalMcpRuntime):
    def __init__(self) -> None:
        super().__init__(_NoCredentials(), cast(SafeExternalMcpHttpClientFactory, object()))

    @asynccontextmanager
    async def _session(self, source: McpSource) -> AsyncIterator[ClientSession]:
        del source
        raise RuntimeError("handshake unavailable")
        yield cast(ClientSession, object())


def test_external_runtime_marks_disconnect_after_call_dispatch_as_result_unknown() -> None:
    session = _CallDisconnectSession()
    runtime = _CallDisconnectRuntime(session)
    source = McpSource.create(
        name="外部写操作 MCP",
        source_type=McpSourceType.EXTERNAL,
        endpoint_url="https://mcp.partner.example/mcp",
        status=McpSourceStatus.READY,
    )

    with pytest.raises(McpToolCallError) as captured:
        asyncio.run(runtime.call_tool(source, "orders.create", {"order_id": "A-100"}))

    assert captured.value.code == "tool_result_unknown"
    assert captured.value.retryable is False
    assert session.calls == 1


def test_external_runtime_marks_malformed_success_after_dispatch_as_result_unknown() -> None:
    session = _MalformedResultSession()
    runtime = _CallDisconnectRuntime(session)
    source = McpSource.create(
        name="外部写操作 MCP",
        source_type=McpSourceType.EXTERNAL,
        endpoint_url="https://mcp.partner.example/mcp",
        status=McpSourceStatus.READY,
    )

    with pytest.raises(McpToolCallError) as captured:
        asyncio.run(runtime.call_tool(source, "orders.create", {"order_id": "A-100"}))

    assert captured.value.code == "tool_result_unknown"
    assert captured.value.retryable is False
    assert session.calls == 1


def test_external_runtime_keeps_pre_dispatch_handshake_failure_retryable() -> None:
    runtime = _SessionUnavailableRuntime()
    source = McpSource.create(
        name="外部 MCP",
        source_type=McpSourceType.EXTERNAL,
        endpoint_url="https://mcp.partner.example/mcp",
        status=McpSourceStatus.READY,
    )

    with pytest.raises(McpToolCallError) as captured:
        asyncio.run(runtime.call_tool(source, "orders.get", {}))

    assert captured.value.code == "tool_source_unavailable"
    assert captured.value.retryable is True
