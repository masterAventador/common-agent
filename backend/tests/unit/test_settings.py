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


def test_database_settings_default_to_project_local_mysql() -> None:
    settings = DatabaseSettings.from_mapping({})

    assert settings.url == (
        "mysql+asyncmy://common_agent:common_agent_dev@127.0.0.1:19506/common_agent?charset=utf8mb4"
    )


def test_database_settings_allow_formal_adapter_override() -> None:
    url = "mysql+asyncmy://common_agent:secret@127.0.0.1:19507/common_agent"

    settings = DatabaseSettings.from_mapping({"COMMON_AGENT_DATABASE_URL": url})

    assert settings.url == url


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:////tmp/common-agent.db",
        "postgresql+asyncpg://common_agent:secret@127.0.0.1:19432/common_agent",
    ],
)
def test_database_settings_reject_non_mysql_formal_adapters(url: str) -> None:
    with pytest.raises(ConfigurationError, match=r"mysql\+asyncmy"):
        DatabaseSettings.from_mapping({"COMMON_AGENT_DATABASE_URL": url})


def test_database_settings_reject_remote_mysql_host() -> None:
    with pytest.raises(ConfigurationError, match="loopback"):
        DatabaseSettings.from_mapping(
            {
                "COMMON_AGENT_DATABASE_URL": (
                    "mysql+asyncmy://common_agent:secret@db.example.com:3306/common_agent"
                )
            }
        )


@pytest.mark.parametrize(
    "url",
    [
        "mysql+asyncmy://:secret@127.0.0.1:19506/common_agent",
        "mysql+asyncmy://common_agent@127.0.0.1:19506/common_agent",
        "mysql+asyncmy://common_agent:@127.0.0.1:19506/common_agent",
        "mysql+asyncmy://common_agent:secret@127.0.0.1/common_agent",
        "mysql+asyncmy://common_agent:secret@127.0.0.1:19506/",
    ],
)
def test_database_settings_require_all_connection_fields(url: str) -> None:
    with pytest.raises(ConfigurationError, match="user, password, port and database"):
        DatabaseSettings.from_mapping({"COMMON_AGENT_DATABASE_URL": url})


def test_database_settings_does_not_leak_password_in_repr() -> None:
    settings = DatabaseSettings.from_mapping(
        {
            "COMMON_AGENT_DATABASE_URL": (
                "mysql+asyncmy://common_agent:do-not-leak@127.0.0.1:19506/common_agent"
            )
        }
    )

    assert "do-not-leak" not in repr(settings)


def test_cors_settings_default_to_project_frontend_origin() -> None:
    settings = CorsSettings.from_mapping({})

    assert settings.origins == ("http://127.0.0.1:18280",)


def test_cors_settings_reject_public_or_remote_origin() -> None:
    with pytest.raises(ConfigurationError, match="loopback"):
        CorsSettings.from_mapping({"COMMON_AGENT_CORS_ORIGINS": "https://example.com"})
