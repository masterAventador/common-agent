from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from ipaddress import ip_network

import uvicorn
from mcp.server.fastmcp import FastMCP

from common_agent.adapters.mcp.external import (
    ExternalMcpRuntime,
    SafeExternalMcpHttpClientFactory,
)
from common_agent.bootstrap import ToolEgressSettings
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
