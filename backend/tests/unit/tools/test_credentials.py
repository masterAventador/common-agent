from __future__ import annotations

from uuid import uuid4

import pytest

from common_agent.tools.credentials import (
    CREDENTIAL_MASK,
    McpCredential,
    McpCredentialKind,
    ToolCredentialValidationError,
)


def test_bearer_credential_masks_secret_and_repr() -> None:
    secret = "bearer-value-that-must-never-leak"

    credential = McpCredential.bearer(secret)

    assert credential.kind is McpCredentialKind.BEARER
    assert credential.masked().bearer_token == CREDENTIAL_MASK
    assert secret not in repr(credential)
    assert secret not in repr(credential.masked())


def test_custom_headers_keep_names_but_mask_every_value() -> None:
    credential = McpCredential.custom_headers(
        {"X-Api-Key": "secret-api-key", "AuthToken": "secret-token"}
    )

    assert credential.masked().headers == {
        "AuthToken": CREDENTIAL_MASK,
        "X-Api-Key": CREDENTIAL_MASK,
    }
    assert "secret-api-key" not in repr(credential)
    assert "secret-token" not in repr(credential)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("Host", "example.com"),
        ("Authorization", "Bearer bypass"),
        ("Proxy-Authorization", "proxy-secret"),
        ("X-Bad\nHeader", "value"),
        ("X-Good", "value\r\ninjected: true"),
    ],
)
def test_custom_headers_reject_transport_override_and_injection(
    name: str,
    value: str,
) -> None:
    with pytest.raises(ToolCredentialValidationError):
        McpCredential.custom_headers({name: value})


def test_credential_aad_is_bound_to_tenant_and_source() -> None:
    tenant_id = uuid4()
    source_id = uuid4()

    credential = McpCredential.bearer("secret")

    assert credential.aad(tenant_id, source_id) != credential.aad(uuid4(), source_id)
    assert credential.aad(tenant_id, source_id) != credential.aad(tenant_id, uuid4())
