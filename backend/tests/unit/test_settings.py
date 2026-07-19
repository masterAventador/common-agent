from pathlib import Path

import pytest

from common_agent.bootstrap.settings import (
    ApiSettings,
    ConfigurationError,
    CorsSettings,
    DatabaseSettings,
)


def test_api_settings_use_project_loopback_defaults() -> None:
    settings = ApiSettings.from_mapping({})

    assert settings.host == "127.0.0.1"
    assert settings.port == 18200


def test_api_settings_accept_project_specific_override() -> None:
    settings = ApiSettings.from_mapping(
        {
            "COMMON_AGENT_API_HOST": "localhost",
            "COMMON_AGENT_API_PORT": "18201",
        }
    )

    assert settings.host == "localhost"
    assert settings.port == 18201


@pytest.mark.parametrize("port", ["not-a-port", "0", "65536"])
def test_api_settings_reject_invalid_port(port: str) -> None:
    with pytest.raises(ConfigurationError, match="COMMON_AGENT_API_PORT"):
        ApiSettings.from_mapping({"COMMON_AGENT_API_PORT": port})


def test_api_settings_reject_public_bind_address() -> None:
    with pytest.raises(ConfigurationError, match="loopback"):
        ApiSettings.from_mapping({"COMMON_AGENT_API_HOST": "0.0.0.0"})


def test_database_settings_default_to_project_local_sqlite(tmp_path: Path) -> None:
    settings = DatabaseSettings.from_mapping({}, project_root=tmp_path)

    assert settings.url == f"sqlite+aiosqlite:///{tmp_path / '.local' / 'common-agent.db'}"


def test_database_settings_allow_formal_adapter_override(tmp_path: Path) -> None:
    url = "postgresql+asyncpg://common-agent:secret@127.0.0.1:19432/common_agent"

    settings = DatabaseSettings.from_mapping(
        {"COMMON_AGENT_DATABASE_URL": url}, project_root=tmp_path
    )

    assert settings.url == url


def test_cors_settings_default_to_project_frontend_origin() -> None:
    settings = CorsSettings.from_mapping({})

    assert settings.origins == ("http://127.0.0.1:18280",)


def test_cors_settings_reject_public_or_remote_origin() -> None:
    with pytest.raises(ConfigurationError, match="loopback"):
        CorsSettings.from_mapping({"COMMON_AGENT_CORS_ORIGINS": "https://example.com"})
