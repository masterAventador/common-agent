from __future__ import annotations

from uuid import uuid4

import pytest

from common_agent.adapters.security.tool_credentials import (
    AesGcmToolCredentialCipher,
    CredentialCipherError,
)
from common_agent.tools.credentials import McpCredential


def test_cipher_round_trip_uses_random_nonce_and_hides_plaintext() -> None:
    cipher = AesGcmToolCredentialCipher(
        keys={"active": b"a" * 32},
        active_key_id="active",
    )
    tenant_id = uuid4()
    source_id = uuid4()
    credential = McpCredential.bearer("plain-bearer-secret")

    first = cipher.encrypt(tenant_id, source_id, credential)
    second = cipher.encrypt(tenant_id, source_id, credential)

    assert first.nonce != second.nonce
    assert b"plain-bearer-secret" not in first.ciphertext
    assert "plain-bearer-secret" not in repr(first)
    assert cipher.decrypt(tenant_id, source_id, first) == credential


def test_cipher_rejects_tenant_or_source_row_swap() -> None:
    cipher = AesGcmToolCredentialCipher(
        keys={"active": b"a" * 32},
        active_key_id="active",
    )
    tenant_id = uuid4()
    source_id = uuid4()
    encrypted = cipher.encrypt(
        tenant_id,
        source_id,
        McpCredential.custom_headers({"X-Api-Key": "secret"}),
    )

    with pytest.raises(CredentialCipherError, match="无法解密"):
        cipher.decrypt(uuid4(), source_id, encrypted)
    with pytest.raises(CredentialCipherError, match="无法解密"):
        cipher.decrypt(tenant_id, uuid4(), encrypted)


def test_keyring_decrypts_old_key_but_new_writes_use_active_key() -> None:
    tenant_id = uuid4()
    source_id = uuid4()
    old_cipher = AesGcmToolCredentialCipher(
        keys={"old": b"o" * 32},
        active_key_id="old",
    )
    encrypted = old_cipher.encrypt(tenant_id, source_id, McpCredential.bearer("secret"))
    rotated = AesGcmToolCredentialCipher(
        keys={"new": b"n" * 32, "old": b"o" * 32},
        active_key_id="new",
    )

    assert rotated.decrypt(tenant_id, source_id, encrypted) == McpCredential.bearer("secret")
    assert rotated.encrypt(
        tenant_id,
        source_id,
        McpCredential.bearer("replacement"),
    ).key_id == "new"
