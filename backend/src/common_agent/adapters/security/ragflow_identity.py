from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from collections.abc import Mapping
from uuid import UUID

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from common_agent.knowledge.ragflow_identity import (
    RAGFLOW_IDENTITY_FORMAT_VERSION,
    EncryptedRagFlowApiKey,
)

_KEY_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class RagFlowIdentityCipherError(RuntimeError):
    """Raised without carrying RAGFlow credentials or cryptographic internals."""


class AesGcmRagFlowIdentityCipher:
    def __init__(self, *, keys: Mapping[str, bytes], active_key_id: str) -> None:
        normalized = dict(keys)
        if not normalized or active_key_id not in normalized:
            raise ValueError("RAGFlow 身份活动密钥不存在")
        for key_id, key in normalized.items():
            if not _KEY_ID.fullmatch(key_id):
                raise ValueError("RAGFlow 身份密钥 ID 不合法")
            if not isinstance(key, bytes) or len(key) != 32:
                raise ValueError("RAGFlow 身份密钥必须是 32 字节")
        self._keys = normalized
        self._active_key_id = active_key_id

    @property
    def active_key_id(self) -> str:
        return self._active_key_id

    def derive_account_password(self, tenant_id: UUID, *, key_id: str) -> str:
        key = self._keys.get(key_id)
        if key is None:
            raise RagFlowIdentityCipherError("RAGFlow 身份密码无法派生")
        digest = hmac.new(
            key,
            f"common-agent:ragflow-account-password:v1:{tenant_id}".encode(),
            hashlib.sha256,
        ).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def encrypt_token(
        self,
        platform_tenant_id: UUID,
        account_email: str,
        ragflow_tenant_id: str,
        token: str,
    ) -> EncryptedRagFlowApiKey:
        normalized = token.strip()
        if not normalized:
            raise RagFlowIdentityCipherError("RAGFlow API Token 不能为空")
        nonce = os.urandom(12)
        ciphertext = AESGCM(self._keys[self._active_key_id]).encrypt(
            nonce,
            normalized.encode(),
            _aad(platform_tenant_id, account_email, ragflow_tenant_id),
        )
        return EncryptedRagFlowApiKey(
            format_version=RAGFLOW_IDENTITY_FORMAT_VERSION,
            key_id=self._active_key_id,
            nonce=nonce,
            ciphertext=ciphertext,
        )

    def decrypt_token(
        self,
        platform_tenant_id: UUID,
        account_email: str,
        ragflow_tenant_id: str,
        encrypted: EncryptedRagFlowApiKey,
    ) -> str:
        key = self._keys.get(encrypted.key_id)
        if (
            key is None
            or encrypted.format_version != RAGFLOW_IDENTITY_FORMAT_VERSION
            or len(encrypted.nonce) != 12
        ):
            raise RagFlowIdentityCipherError("RAGFlow API Token 无法解密")
        try:
            return AESGCM(key).decrypt(
                encrypted.nonce,
                encrypted.ciphertext,
                _aad(platform_tenant_id, account_email, ragflow_tenant_id),
            ).decode()
        except (InvalidTag, UnicodeDecodeError):
            raise RagFlowIdentityCipherError("RAGFlow API Token 无法解密") from None


def _aad(platform_tenant_id: UUID, account_email: str, ragflow_tenant_id: str) -> bytes:
    return (
        f"common-agent:ragflow-identity:v{RAGFLOW_IDENTITY_FORMAT_VERSION}:"
        f"{platform_tenant_id}:{account_email.casefold()}:{ragflow_tenant_id}"
    ).encode()


__all__ = ["AesGcmRagFlowIdentityCipher", "RagFlowIdentityCipherError"]
