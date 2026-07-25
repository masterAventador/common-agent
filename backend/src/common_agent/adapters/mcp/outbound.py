from __future__ import annotations

from collections.abc import Mapping

from common_agent.adapters.security import OutboundSecurityError
from common_agent.ports.mcp import McpToolCallError
from common_agent.tools.credentials import McpCredential, McpCredentialKind
from common_agent.tools.models import ToolCallErrorCode


def credential_headers(
    request_headers: Mapping[str, str],
    credential: McpCredential | None,
) -> dict[str, str]:
    headers = dict(request_headers)
    if credential is None:
        return headers
    if credential.kind is McpCredentialKind.BEARER:
        if credential.bearer_token is None:
            raise McpToolCallError(ToolCallErrorCode.SOURCE_UNAVAILABLE.value)
        _replace_header(headers, "Authorization", f"Bearer {credential.bearer_token}")
        return headers
    for name, value in credential.headers.items():
        _replace_header(headers, name, value)
    return headers


def egress_error_code(error: OutboundSecurityError) -> str:
    if error.code == "tool_egress_timeout":
        return ToolCallErrorCode.TIMEOUT.value
    if error.code == "tool_egress_response_too_large":
        return ToolCallErrorCode.RESPONSE_TOO_LARGE.value
    return ToolCallErrorCode.SOURCE_UNAVAILABLE.value


def _replace_header(headers: dict[str, str], name: str, value: str) -> None:
    existing = next((key for key in headers if key.lower() == name.lower()), None)
    if existing is not None:
        del headers[existing]
    headers[name] = value


__all__ = ["credential_headers", "egress_error_code"]
