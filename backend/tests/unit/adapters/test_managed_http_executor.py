from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.mcp.managed_http_executor import ManagedHttpRequestExecutor
from common_agent.adapters.security import OutboundHttpResponse, OutboundSecurityError
from common_agent.ports.mcp import McpToolCallError
from common_agent.tools.credentials import McpCredential
from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpParameterBinding,
    ManagedHttpParameterLocation,
)
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
)


def _fixture() -> tuple[McpSource, ManagedHttpCapability]:
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
    return source, ManagedHttpCapability(
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
        timeout_seconds=12,
        response_json_pointer="/data/order",
    )


class _Credentials:
    def __init__(self, value: McpCredential | None) -> None:
        self.value = value

    async def resolve(self, source_id: UUID) -> McpCredential | None:
        assert isinstance(source_id, UUID)
        return self.value


class _Client:
    def __init__(
        self,
        response: OutboundHttpResponse | Exception,
        *,
        close_error: Exception | None = None,
    ) -> None:
        self.response = response
        self.close_error = close_error
        self.calls: list[tuple[str, str, dict[str, str], bytes | None]] = []
        self.closed = False

    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        content: bytes | None,
    ) -> OutboundHttpResponse:
        self.calls.append((method, url, dict(headers), content))
        if isinstance(self.response, Exception):
            raise self.response
        return self.response

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


class _Factory:
    def __init__(self, client: _Client) -> None:
        self.client = client
        self.calls: list[tuple[str, int]] = []

    def create(self, endpoint_url: str, timeout_seconds: int) -> _Client:
        self.calls.append((endpoint_url, timeout_seconds))
        return self.client


def test_executor_injects_server_side_bearer_and_extracts_json_pointer() -> None:
    source, capability = _fixture()
    response_body = json.dumps(
        {"data": {"order": {"id": "A-100", "state": "paid"}}}
    ).encode()
    client = _Client(OutboundHttpResponse(200, (), response_body))
    factory = _Factory(client)
    executor = ManagedHttpRequestExecutor(
        _Credentials(McpCredential.bearer("server-secret-token")),
        factory,
    )

    result = asyncio.run(executor.execute(source, capability, {"order_id": "A-100"}))

    assert result == {"id": "A-100", "state": "paid"}
    assert factory.calls == [("https://business.example/api", 12)]
    assert client.calls == [
        (
            "GET",
            "https://business.example/api/orders/A-100",
            {"Authorization": "Bearer server-secret-token"},
            None,
        )
    ]
    assert client.closed is True
    assert "server-secret-token" not in repr(executor)


@pytest.mark.parametrize(
    ("response", "error_code"),
    [
        (
            OutboundHttpResponse(503, (), b'{"error":"secret-upstream-error"}'),
            "tool_execution_failed",
        ),
        (OutboundHttpResponse(200, (), b"not-json"), "tool_result_unknown"),
        (
            OutboundSecurityError(
                "tool_egress_timeout",
                "timed out with secret-upstream-error",
                retryable=True,
            ),
            "tool_timeout",
        ),
        (
            OutboundSecurityError(
                "tool_egress_response_too_large",
                "large secret-upstream-error",
            ),
            "tool_response_too_large",
        ),
        (RuntimeError("disconnected after dispatch with secret"), "tool_result_unknown"),
    ],
)
def test_executor_maps_failures_to_stable_codes_without_upstream_content(
    response: OutboundHttpResponse | Exception,
    error_code: str,
) -> None:
    source, capability = _fixture()
    client = _Client(response)
    executor = ManagedHttpRequestExecutor(_Credentials(None), _Factory(client))

    with pytest.raises(McpToolCallError) as captured:
        asyncio.run(executor.execute(source, capability, {"order_id": str(uuid4())}))

    assert captured.value.code == error_code
    if error_code == "tool_result_unknown":
        assert captured.value.retryable is False
    assert "secret-upstream-error" not in str(captured.value)
    assert client.closed is True


def test_executor_injects_custom_credential_headers_server_side() -> None:
    source, capability = _fixture()
    client = _Client(OutboundHttpResponse(200, (), b'{"data":{"order":{}}}'))
    executor = ManagedHttpRequestExecutor(
        _Credentials(McpCredential.custom_headers({"Cookie": "session-secret"})),
        _Factory(client),
    )

    configured_capability = ManagedHttpCapability(
        capability=capability.capability,
        method="GET",
        path_template="/orders/{order_id}",
        parameter_bindings=capability.parameter_bindings,
        timeout_seconds=12,
        response_json_pointer=capability.response_json_pointer,
    )

    result = asyncio.run(
        executor.execute(source, configured_capability, {"order_id": "A-100"})
    )
    assert result == {}
    assert client.calls[0][2] == {"Cookie": "session-secret"}


def test_executor_does_not_treat_cleanup_failure_as_safe_to_replay() -> None:
    source, capability = _fixture()
    client = _Client(
        OutboundHttpResponse(200, (), b'{"data":{"order":{"id":"A-100"}}}'),
        close_error=RuntimeError("connection cleanup failed with secret"),
    )
    executor = ManagedHttpRequestExecutor(_Credentials(None), _Factory(client))

    with pytest.raises(McpToolCallError) as captured:
        asyncio.run(executor.execute(source, capability, {"order_id": "A-100"}))

    assert captured.value.code == "tool_result_unknown"
    assert captured.value.retryable is False
    assert "secret" not in str(captured.value)
    assert client.closed is True
