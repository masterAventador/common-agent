from __future__ import annotations

from uuid import uuid4

import pytest

from common_agent.adapters.security.ragflow_identity import (
    AesGcmRagFlowIdentityCipher,
    RagFlowIdentityCipherError,
)


def test_ragflow_token_cipher_binds_ciphertext_to_both_tenants_and_account() -> None:
    cipher = AesGcmRagFlowIdentityCipher(
        keys={"active": b"a" * 32},
        active_key_id="active",
    )
    platform_tenant_id = uuid4()
    account_email = "common-agent-tenant@local.test"
    ragflow_tenant_id = "ragflow-tenant-a"

    encrypted = cipher.encrypt_token(
        platform_tenant_id,
        account_email,
        ragflow_tenant_id,
        "ragflow-secret-token",
    )

    assert b"ragflow-secret-token" not in encrypted.ciphertext
    assert cipher.decrypt_token(
        platform_tenant_id,
        account_email,
        ragflow_tenant_id,
        encrypted,
    ) == "ragflow-secret-token"
    with pytest.raises(RagFlowIdentityCipherError):
        cipher.decrypt_token(
            uuid4(),
            account_email,
            ragflow_tenant_id,
            encrypted,
        )
    with pytest.raises(RagFlowIdentityCipherError):
        cipher.decrypt_token(
            platform_tenant_id,
            "other@local.test",
            ragflow_tenant_id,
            encrypted,
        )


def test_ragflow_account_password_is_deterministic_per_tenant_and_never_stored() -> None:
    cipher = AesGcmRagFlowIdentityCipher(
        keys={"active": b"a" * 32},
        active_key_id="active",
    )
    first_tenant = uuid4()
    second_tenant = uuid4()

    first = cipher.derive_account_password(first_tenant, key_id="active")

    assert first == cipher.derive_account_password(first_tenant, key_id="active")
    assert first != cipher.derive_account_password(second_tenant, key_id="active")
    assert len(first) >= 32
