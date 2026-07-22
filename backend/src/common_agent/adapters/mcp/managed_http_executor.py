from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping
from typing import Protocol, cast
from uuid import UUID

from common_agent.adapters.security import (
    OutboundAccessPolicy,
    OutboundHttpResponse,
    OutboundSecurityError,
    SafeOutboundHttpClient,
)
from common_agent.bootstrap import ToolEgressSettings
from common_agent.ports.mcp import McpToolCallError
from common_agent.tools.credentials import McpCredential, McpCredentialKind
from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpValidationError,
    build_managed_http_request,
)
from common_agent.tools.models import McpSource


class ManagedHttpCredentialResolver(Protocol):
    async def resolve(self, source_id: UUID) -> McpCredential | None: ...


class ManagedHttpClient(Protocol):
    async def request(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        content: bytes | None,
    ) -> OutboundHttpResponse: ...

    async def aclose(self) -> None: ...


class ManagedHttpClientFactory(Protocol):
    def create(self, endpoint_url: str, timeout_seconds: int) -> ManagedHttpClient: ...


class SafeManagedHttpClientFactory:
    def __init__(self, settings: ToolEgressSettings) -> None:
        self._settings = settings
        self._policy = OutboundAccessPolicy(
            allowed_hosts=settings.allowed_hosts,
            allowed_cidrs=settings.allowed_cidrs,
            http_allowed_hosts=settings.http_allowed_hosts,
            allow_loopback=settings.allow_loopback,
        )
        self._semaphore = asyncio.Semaphore(settings.maximum_concurrency)

    def create(self, endpoint_url: str, timeout_seconds: int) -> SafeOutboundHttpClient:
        call_timeout = min(float(timeout_seconds), self._settings.call_timeout_seconds)
        return SafeOutboundHttpClient(
            endpoint_url=endpoint_url,
            policy=self._policy,
            connect_timeout_seconds=min(
                self._settings.connect_timeout_seconds,
                call_timeout,
            ),
            read_timeout_seconds=min(
                self._settings.read_timeout_seconds,
                call_timeout,
            ),
            call_timeout_seconds=call_timeout,
            maximum_response_bytes=self._settings.maximum_response_bytes,
            maximum_concurrency=self._settings.maximum_concurrency,
            concurrency_semaphore=self._semaphore,
        )


class ManagedHttpRequestExecutor:
    def __init__(
        self,
        credentials: ManagedHttpCredentialResolver,
        clients: ManagedHttpClientFactory,
    ) -> None:
        self._credentials = credentials
        self._clients = clients

    async def execute(
        self,
        source: McpSource,
        capability: ManagedHttpCapability,
        arguments: dict[str, object],
    ) -> dict[str, object]:
        endpoint_url = source.endpoint_url
        if endpoint_url is None:
            raise McpToolCallError("tool_source_unavailable")
        try:
            outbound = build_managed_http_request(endpoint_url, capability, arguments)
        except ManagedHttpValidationError:
            raise McpToolCallError("tool_invalid_arguments") from None
        try:
            credential = await self._credentials.resolve(source.id)
        except Exception:
            raise McpToolCallError("tool_source_unavailable") from None
        headers = _credential_headers(outbound.headers, credential)
        client = self._clients.create(endpoint_url, capability.timeout_seconds)
        try:
            response = await client.request(
                outbound.method,
                outbound.url,
                headers=headers,
                content=outbound.body,
            )
        except OutboundSecurityError as error:
            raise McpToolCallError(_egress_error_code(error), retryable=error.retryable) from None
        except Exception:
            raise McpToolCallError("tool_source_unavailable", retryable=True) from None
        finally:
            await client.aclose()
        if not 200 <= response.status_code < 300:
            raise McpToolCallError("tool_execution_failed")
        try:
            payload = json.loads(response.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise McpToolCallError("tool_protocol_error") from None
        try:
            selected = _json_pointer(payload, capability.response_json_pointer)
        except (KeyError, IndexError, TypeError, ValueError):
            raise McpToolCallError("tool_protocol_error") from None
        if isinstance(selected, dict):
            return cast(dict[str, object], selected)
        return {"result": selected}


def _credential_headers(
    request_headers: Mapping[str, str],
    credential: McpCredential | None,
) -> dict[str, str]:
    headers = dict(request_headers)
    if credential is None:
        return headers
    if credential.kind is McpCredentialKind.BEARER:
        if credential.bearer_token is None:
            raise McpToolCallError("tool_source_unavailable")
        _replace_header(headers, "Authorization", f"Bearer {credential.bearer_token}")
        return headers
    for name, value in credential.headers.items():
        _replace_header(headers, name, value)
    return headers


def _replace_header(headers: dict[str, str], name: str, value: str) -> None:
    existing = next((key for key in headers if key.lower() == name.lower()), None)
    if existing is not None:
        del headers[existing]
    headers[name] = value


def _egress_error_code(error: OutboundSecurityError) -> str:
    if error.code == "tool_egress_timeout":
        return "tool_timeout"
    if error.code == "tool_egress_response_too_large":
        return "tool_response_too_large"
    return "tool_source_unavailable"


def _json_pointer(payload: object, pointer: str | None) -> object:
    if pointer is None:
        return payload
    current = payload
    for raw_token in pointer.split("/")[1:]:
        token = raw_token.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict):
            current = current[token]
        elif isinstance(current, list):
            if token == "-" or (token.startswith("0") and token != "0"):
                raise ValueError("invalid JSON Pointer array index")
            current = current[int(token)]
        else:
            raise TypeError("JSON Pointer cannot descend into scalar")
    return current


__all__ = [
    "ManagedHttpClient",
    "ManagedHttpClientFactory",
    "ManagedHttpCredentialResolver",
    "ManagedHttpRequestExecutor",
    "SafeManagedHttpClientFactory",
]
