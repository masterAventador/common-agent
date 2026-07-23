from __future__ import annotations

import base64

import pytest

from common_agent.bootstrap import ConfigurationError, RagFlowIdentitySettings


def _key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def test_local_ragflow_identity_keyring_has_an_isolated_development_key() -> None:
    settings = RagFlowIdentitySettings.from_mapping({})

    assert settings.active_key_id == "local-ragflow-v1"
    assert settings.keys[settings.active_key_id]


def test_production_requires_explicit_ragflow_identity_keyring() -> None:
    with pytest.raises(ConfigurationError, match="COMMON_AGENT_RAGFLOW_IDENTITY_KEYS"):
        RagFlowIdentitySettings.from_mapping({"COMMON_AGENT_RUNTIME_ENV": "production"})


def test_ragflow_identity_keyring_supports_rotation() -> None:
    settings = RagFlowIdentitySettings.from_mapping(
        {
            "COMMON_AGENT_RUNTIME_ENV": "production",
            "COMMON_AGENT_RAGFLOW_IDENTITY_KEYS": (
                f"new:{_key(b'n' * 32)},old:{_key(b'o' * 32)}"
            ),
            "COMMON_AGENT_RAGFLOW_IDENTITY_ACTIVE_KEY_ID": "new",
        }
    )

    assert settings.active_key_id == "new"
    assert settings.keys == {"new": b"n" * 32, "old": b"o" * 32}
