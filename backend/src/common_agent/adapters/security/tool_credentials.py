from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping
from typing import cast
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from common_agent.tools.credentials import (
    MCP_CREDENTIAL_FORMAT_VERSION,
    EncryptedMcpCredential,
    McpCredential,
    McpCredentialKind,
    ToolCredentialValidationError,
    mcp_credential_aad,
)

_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class CredentialCipherError(RuntimeError):
    """Raised without carrying credential plaintext or cryptographic internals."""


class AesGcmToolCredentialCipher:
    def __init__(self, *, keys: Mapping[str, bytes], active_key_id: str) -> None:
        normalized = dict(keys)
        if not normalized or active_key_id not in normalized:
            raise ValueError("MCP 凭据活动密钥不存在")
        for key_id, key in normalized.items():
            if not _KEY_ID.fullmatch(key_id):
                raise ValueError("MCP 凭据密钥 ID 不合法")
            if not isinstance(key, bytes) or len(key) != 32:
                raise ValueError("MCP 凭据密钥必须是 32 字节")
        self._keys = normalized
        self._active_key_id = active_key_id

    def encrypt(
        self,
        tenant_id: UUID,
        source_id: UUID,
        credential: McpCredential,
    ) -> EncryptedMcpCredential:
        nonce = os.urandom(12)
        plaintext = _serialize(credential)
        ciphertext = AESGCM(self._keys[self._active_key_id]).encrypt(
            nonce,
            plaintext,
            credential.aad(tenant_id, source_id),
        )
        return EncryptedMcpCredential(
            format_version=MCP_CREDENTIAL_FORMAT_VERSION,
            key_id=self._active_key_id,
            nonce=nonce,
            ciphertext=ciphertext,
        )

    def decrypt(
        self,
        tenant_id: UUID,
        source_id: UUID,
        encrypted: EncryptedMcpCredential,
    ) -> McpCredential:
        key = self._keys.get(encrypted.key_id)
        if key is None:
            raise CredentialCipherError("MCP 凭据无法解密")
        aad = mcp_credential_aad(tenant_id, source_id)
        try:
            plaintext = AESGCM(key).decrypt(encrypted.nonce, encrypted.ciphertext, aad)
            return _deserialize(plaintext)
        except (
            InvalidTag,
            UnicodeDecodeError,
            json.JSONDecodeError,
            ToolCredentialValidationError,
        ):
            raise CredentialCipherError("MCP 凭据无法解密") from None


def _serialize(credential: McpCredential) -> bytes:
    if credential.kind is McpCredentialKind.BEARER:
        payload: dict[str, object] = {
            "kind": credential.kind.value,
            "bearer_token": credential.bearer_token,
        }
    else:
        payload = {
            "kind": credential.kind.value,
            "headers": dict(credential.headers),
        }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _deserialize(plaintext: bytes) -> McpCredential:
    raw = json.loads(plaintext.decode("utf-8"))
    if not isinstance(raw, dict):
        raise ToolCredentialValidationError("MCP 凭据内容不合法")
    kind = raw.get("kind")
    if kind == McpCredentialKind.BEARER.value and set(raw) == {"kind", "bearer_token"}:
        return McpCredential.bearer(cast(str, raw["bearer_token"]))
    if kind == McpCredentialKind.CUSTOM_HEADERS.value and set(raw) == {"kind", "headers"}:
        headers = raw["headers"]
        if not isinstance(headers, dict):
            raise ToolCredentialValidationError("MCP 凭据 Header 不合法")
        return McpCredential.custom_headers(cast(dict[str, str], headers))
    raise ToolCredentialValidationError("MCP 凭据内容不合法")


__all__ = ["AesGcmToolCredentialCipher", "CredentialCipherError"]
