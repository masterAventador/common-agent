from __future__ import annotations

import base64
from ipaddress import ip_network

import pytest

from common_agent.bootstrap import (
    ConfigurationError,
    ToolCredentialSettings,
    ToolEgressSettings,
)


def _key(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii")


def test_local_tool_security_defaults_are_loopback_only() -> None:
    credentials = ToolCredentialSettings.from_mapping({})
    egress = ToolEgressSettings.from_mapping({})

    assert credentials.active_key_id == "local-dev-v1"
    assert credentials.keys[credentials.active_key_id]
    assert repr(credentials).find(credentials.keys[credentials.active_key_id].hex()) == -1
    assert egress.allowed_hosts == ("localhost",)
    assert egress.allowed_cidrs == (
        ip_network("127.0.0.0/8"),
        ip_network("::1/128"),
    )
    assert egress.http_allowed_hosts == ("localhost",)
    assert egress.allow_loopback is True


def test_production_requires_explicit_credential_keyring() -> None:
    with pytest.raises(ConfigurationError, match="COMMON_AGENT_TOOL_CREDENTIAL_KEYS"):
        ToolCredentialSettings.from_mapping({"COMMON_AGENT_RUNTIME_ENV": "production"})


def test_credential_keyring_accepts_old_decrypt_keys_and_active_key() -> None:
    settings = ToolCredentialSettings.from_mapping(
        {
            "COMMON_AGENT_RUNTIME_ENV": "production",
            "COMMON_AGENT_TOOL_CREDENTIAL_KEYS": (
                f"new:{_key(b'n' * 32)},old:{_key(b'o' * 32)}"
            ),
            "COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID": "new",
        }
    )

    assert settings.active_key_id == "new"
    assert settings.keys == {"new": b"n" * 32, "old": b"o" * 32}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("COMMON_AGENT_TOOL_CREDENTIAL_KEYS", "active:not-base64"),
        ("COMMON_AGENT_TOOL_CREDENTIAL_KEYS", f"active:{_key(b'short')}"),
        ("COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID", "missing"),
    ],
)
def test_credential_keyring_rejects_invalid_configuration(name: str, value: str) -> None:
    values = {
        "COMMON_AGENT_RUNTIME_ENV": "production",
        "COMMON_AGENT_TOOL_CREDENTIAL_KEYS": f"active:{_key(b'a' * 32)}",
        "COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID": "active",
    }
    values[name] = value

    with pytest.raises(ConfigurationError, match="COMMON_AGENT_TOOL_CREDENTIAL"):
        ToolCredentialSettings.from_mapping(values)


def test_egress_settings_parse_exact_hosts_cidrs_and_resource_limits() -> None:
    settings = ToolEgressSettings.from_mapping(
        {
            "COMMON_AGENT_RUNTIME_ENV": "production",
            "COMMON_AGENT_TOOL_EGRESS_ALLOWED_HOSTS": "mcp.example.com,business.internal",
            "COMMON_AGENT_TOOL_EGRESS_ALLOWED_CIDRS": "10.20.0.0/16",
            "COMMON_AGENT_TOOL_EGRESS_HTTP_ALLOWED_HOSTS": "business.internal",
            "COMMON_AGENT_TOOL_EGRESS_ALLOW_LOOPBACK": "false",
            "COMMON_AGENT_TOOL_EGRESS_CONNECT_TIMEOUT_SECONDS": "3",
            "COMMON_AGENT_TOOL_EGRESS_READ_TIMEOUT_SECONDS": "20",
            "COMMON_AGENT_TOOL_EGRESS_CALL_TIMEOUT_SECONDS": "30",
            "COMMON_AGENT_TOOL_EGRESS_MAX_RESPONSE_BYTES": "524288",
            "COMMON_AGENT_TOOL_EGRESS_MAX_CONCURRENCY": "8",
        }
    )

    assert settings.allowed_hosts == ("business.internal", "mcp.example.com")
    assert settings.allowed_cidrs == (ip_network("10.20.0.0/16"),)
    assert settings.http_allowed_hosts == ("business.internal",)
    assert settings.connect_timeout_seconds == 3
    assert settings.read_timeout_seconds == 20
    assert settings.call_timeout_seconds == 30
    assert settings.maximum_response_bytes == 524_288
    assert settings.maximum_concurrency == 8


def test_egress_settings_reject_wildcards_and_http_host_outside_allowlist() -> None:
    with pytest.raises(ConfigurationError, match="ALLOWED_HOSTS"):
        ToolEgressSettings.from_mapping(
            {"COMMON_AGENT_TOOL_EGRESS_ALLOWED_HOSTS": "*.example.com"}
        )
    with pytest.raises(ConfigurationError, match="HTTP_ALLOWED_HOSTS"):
        ToolEgressSettings.from_mapping(
            {"COMMON_AGENT_TOOL_EGRESS_HTTP_ALLOWED_HOSTS": "other.example.com"}
        )
