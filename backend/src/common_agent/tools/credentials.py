from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from uuid import UUID

CREDENTIAL_MASK = "********"
MCP_CREDENTIAL_MAX_SECRET_LENGTH = 8_192
MCP_CREDENTIAL_MAX_HEADER_COUNT = 16
MCP_CREDENTIAL_MAX_HEADER_NAME_LENGTH = 128
MCP_CREDENTIAL_MAX_TOTAL_BYTES = 32_768
MCP_CREDENTIAL_FORMAT_VERSION = 1

_HEADER_NAME = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+$")
_PROTECTED_HEADERS = frozenset(
    {
        "authorization",
        "connection",
        "content-length",
        "host",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
    }
)


class ToolCredentialValidationError(ValueError):
    """Raised when an MCP credential cannot be stored or sent safely."""


class McpCredentialKind(StrEnum):
    BEARER = "bearer"
    CUSTOM_HEADERS = "custom_headers"


class McpCredentialAction(StrEnum):
    KEEP = "keep"
    REPLACE = "replace"
    CLEAR = "clear"


@dataclass(frozen=True, slots=True)
class MaskedMcpCredential:
    kind: McpCredentialKind
    bearer_token: str | None = None
    headers: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "headers", MappingProxyType(dict(self.headers)))


@dataclass(frozen=True, slots=True)
class McpCredential:
    kind: McpCredentialKind
    bearer_token: str | None = field(default=None, repr=False)
    headers: Mapping[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.kind, McpCredentialKind):
            raise ToolCredentialValidationError("不支持的 MCP 凭据类型")
        if self.kind is McpCredentialKind.BEARER:
            token = _secret_value(self.bearer_token, "Bearer Token")
            if self.headers:
                raise ToolCredentialValidationError("Bearer 凭据不能同时包含自定义 Header")
            object.__setattr__(self, "bearer_token", token)
            object.__setattr__(self, "headers", MappingProxyType({}))
            return
        if self.bearer_token is not None:
            raise ToolCredentialValidationError("自定义 Header 凭据不能同时包含 Bearer Token")
        object.__setattr__(self, "headers", MappingProxyType(_headers(self.headers)))

    @classmethod
    def bearer(cls, token: str) -> McpCredential:
        return cls(kind=McpCredentialKind.BEARER, bearer_token=token)

    @classmethod
    def custom_headers(cls, headers: Mapping[str, str]) -> McpCredential:
        return cls(kind=McpCredentialKind.CUSTOM_HEADERS, headers=headers)

    def masked(self) -> MaskedMcpCredential:
        if self.kind is McpCredentialKind.BEARER:
            return MaskedMcpCredential(
                kind=self.kind,
                bearer_token=CREDENTIAL_MASK,
            )
        return MaskedMcpCredential(
            kind=self.kind,
            headers={name: CREDENTIAL_MASK for name in self.headers},
        )

    def aad(self, tenant_id: UUID, source_id: UUID) -> bytes:
        return mcp_credential_aad(tenant_id, source_id)


@dataclass(frozen=True, slots=True)
class EncryptedMcpCredential:
    format_version: int
    key_id: str
    nonce: bytes
    ciphertext: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if self.format_version != MCP_CREDENTIAL_FORMAT_VERSION:
            raise ToolCredentialValidationError("不支持的 MCP 凭据密文版本")
        if not self.key_id or len(self.key_id) > 64:
            raise ToolCredentialValidationError("MCP 凭据密钥 ID 不合法")
        if len(self.nonce) != 12:
            raise ToolCredentialValidationError("MCP 凭据随机数长度不合法")
        if len(self.ciphertext) < 16:
            raise ToolCredentialValidationError("MCP 凭据密文不合法")


@dataclass(frozen=True, slots=True)
class McpCredentialCommand:
    action: McpCredentialAction
    credential: McpCredential | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.action, McpCredentialAction):
            raise ToolCredentialValidationError("MCP 凭据更新动作不合法")
        if self.action is McpCredentialAction.REPLACE:
            if not isinstance(self.credential, McpCredential):
                raise ToolCredentialValidationError("替换 MCP 凭据时必须提供新值")
        elif self.credential is not None:
            raise ToolCredentialValidationError("保留或清空 MCP 凭据时不能提供新值")


@dataclass(frozen=True, slots=True)
class McpCredentialSummary:
    source_id: UUID
    configured: bool
    credential: MaskedMcpCredential | None
    updated_at: datetime | None

    def __post_init__(self) -> None:
        if self.configured != (self.credential is not None):
            raise ToolCredentialValidationError("MCP 凭据摘要状态不一致")
        if self.configured != (self.updated_at is not None):
            raise ToolCredentialValidationError("MCP 凭据摘要时间不一致")


def _secret_value(value: str | None, label: str) -> str:
    if value is None or not isinstance(value, str):
        raise ToolCredentialValidationError(f"{label} 不能为空")
    if not value or len(value) > MCP_CREDENTIAL_MAX_SECRET_LENGTH:
        raise ToolCredentialValidationError(
            f"{label} 长度必须在 1 到 {MCP_CREDENTIAL_MAX_SECRET_LENGTH} 之间"
        )
    if _has_control(value):
        raise ToolCredentialValidationError(f"{label} 不能包含控制字符")
    return value


def mcp_credential_aad(tenant_id: UUID, source_id: UUID) -> bytes:
    return (
        f"common-agent:mcp-credential:v{MCP_CREDENTIAL_FORMAT_VERSION}:"
        f"{tenant_id}:{source_id}"
    ).encode("ascii")


def _headers(values: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(values, Mapping) or not values:
        raise ToolCredentialValidationError("自定义 Header 不能为空")
    if len(values) > MCP_CREDENTIAL_MAX_HEADER_COUNT:
        raise ToolCredentialValidationError(
            f"自定义 Header 数量不能超过 {MCP_CREDENTIAL_MAX_HEADER_COUNT}"
        )
    normalized: dict[str, str] = {}
    normalized_names: set[str] = set()
    total_bytes = 0
    for raw_name, raw_value in values.items():
        if not isinstance(raw_name, str) or not raw_name:
            raise ToolCredentialValidationError("自定义 Header 名称不能为空")
        if len(raw_name) > MCP_CREDENTIAL_MAX_HEADER_NAME_LENGTH or not _HEADER_NAME.fullmatch(
            raw_name
        ):
            raise ToolCredentialValidationError("自定义 Header 名称不合法")
        lowercase_name = raw_name.lower()
        if lowercase_name in _PROTECTED_HEADERS or lowercase_name.startswith("proxy-"):
            raise ToolCredentialValidationError("自定义 Header 不能覆盖受保护的传输 Header")
        if lowercase_name in normalized_names:
            raise ToolCredentialValidationError("自定义 Header 名称不能大小写重复")
        value = _secret_value(raw_value, "自定义 Header 值")
        total_bytes += len(raw_name.encode("utf-8")) + len(value.encode("utf-8"))
        if total_bytes > MCP_CREDENTIAL_MAX_TOTAL_BYTES:
            raise ToolCredentialValidationError(
                f"自定义 Header 总大小不能超过 {MCP_CREDENTIAL_MAX_TOTAL_BYTES} 字节"
            )
        normalized_names.add(lowercase_name)
        normalized[raw_name] = value
    return dict(sorted(normalized.items(), key=lambda item: item[0].lower()))


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)


__all__ = [
    "CREDENTIAL_MASK",
    "MCP_CREDENTIAL_FORMAT_VERSION",
    "EncryptedMcpCredential",
    "MaskedMcpCredential",
    "McpCredential",
    "McpCredentialAction",
    "McpCredentialCommand",
    "McpCredentialKind",
    "McpCredentialSummary",
    "ToolCredentialValidationError",
    "mcp_credential_aad",
]
