from __future__ import annotations

import base64

from common_agent.adapters.knowledge.ragflow_tenants import encrypt_ragflow_password


def test_ragflow_password_is_rsa_encrypted_for_transport_and_never_sent_as_plaintext() -> None:
    encrypted = encrypt_ragflow_password("tenant-specific-password")

    assert encrypted != "tenant-specific-password"
    assert b"tenant-specific-password" not in base64.b64decode(encrypted)
    assert len(base64.b64decode(encrypted)) == 256
