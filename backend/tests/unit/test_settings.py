import pytest

from common_agent.bootstrap.settings import (
    ApiSettings,
    ConfigurationError,
    CorsSettings,
    DatabaseSettings,
    IntegrationModeSettings,
    RagFlowSettings,
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
        "mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/common_agent?charset=utf8mb4"
    )


def test_database_settings_allow_formal_adapter_override() -> None:
    url = "mysql+aiomysql://common_agent:secret@127.0.0.1:19507/common_agent"

    settings = DatabaseSettings.from_mapping({"COMMON_AGENT_DATABASE_URL": url})

    assert settings.url == url


@pytest.mark.parametrize(
    "url",
    [
        "sqlite+aiosqlite:////tmp/common-agent.db",
        "postgresql+asyncpg://common_agent:secret@127.0.0.1:19432/common_agent",
        "mysql+asyncmy://common_agent:secret@127.0.0.1:19506/common_agent",
    ],
)
def test_database_settings_reject_non_mysql_formal_adapters(url: str) -> None:
    with pytest.raises(ConfigurationError, match=r"mysql\+aiomysql"):
        DatabaseSettings.from_mapping({"COMMON_AGENT_DATABASE_URL": url})


def test_database_settings_reject_remote_mysql_host() -> None:
    with pytest.raises(ConfigurationError, match="loopback"):
        DatabaseSettings.from_mapping(
            {
                "COMMON_AGENT_DATABASE_URL": (
                    "mysql+aiomysql://common_agent:secret@db.example.com:3306/common_agent"
                )
            }
        )


@pytest.mark.parametrize(
    "url",
    [
        "mysql+aiomysql://:secret@127.0.0.1:19506/common_agent",
        "mysql+aiomysql://common_agent@127.0.0.1:19506/common_agent",
        "mysql+aiomysql://common_agent:@127.0.0.1:19506/common_agent",
        "mysql+aiomysql://common_agent:secret@127.0.0.1/common_agent",
        "mysql+aiomysql://common_agent:secret@127.0.0.1:19506/",
    ],
)
def test_database_settings_require_all_connection_fields(url: str) -> None:
    with pytest.raises(ConfigurationError, match="user, password, port and database"):
        DatabaseSettings.from_mapping({"COMMON_AGENT_DATABASE_URL": url})


def test_database_settings_does_not_leak_password_in_repr() -> None:
    settings = DatabaseSettings.from_mapping(
        {
            "COMMON_AGENT_DATABASE_URL": (
                "mysql+aiomysql://common_agent:do-not-leak@127.0.0.1:19506/common_agent"
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


def test_integration_mode_defaults_to_real_and_accepts_explicit_demo() -> None:
    assert IntegrationModeSettings.from_mapping({}).mode == "real"
    assert (
        IntegrationModeSettings.from_mapping({"COMMON_AGENT_INTEGRATION_MODE": "demo"}).mode
        == "demo"
    )


def test_integration_mode_rejects_unknown_values() -> None:
    with pytest.raises(ConfigurationError, match="COMMON_AGENT_INTEGRATION_MODE"):
        IntegrationModeSettings.from_mapping({"COMMON_AGENT_INTEGRATION_MODE": "mock"})


def test_ragflow_settings_use_fixed_loopback_defaults() -> None:
    settings = RagFlowSettings.from_mapping({})

    assert settings.base_url == "http://127.0.0.1:19380"
    assert settings.expected_version == "v0.25.6"
    assert settings.timeout_seconds == 60
    assert settings.api_key.get_secret_value() == ""


def test_ragflow_settings_accept_safe_override_without_leaking_key() -> None:
    settings = RagFlowSettings.from_mapping(
        {
            "RAGFLOW_BASE_URL": "http://localhost:29380/",
            "RAGFLOW_API_KEY": "do-not-leak",
            "RAGFLOW_EXPECTED_VERSION": "v0.25.6",
            "RAGFLOW_TIMEOUT_SECONDS": "120",
        }
    )

    assert settings.base_url == "http://localhost:29380"
    assert settings.timeout_seconds == 120
    assert "do-not-leak" not in repr(settings)


@pytest.mark.parametrize(
    "base_url",
    [
        "https://ragflow.example.com",
        "ftp://127.0.0.1:19380",
        "http://127.0.0.1",
        "http://127.0.0.1:invalid",
        "http://127.0.0.1:19380/private/path",
        "http://127.0.0.1:19380?token=secret",
        "http://user:password@127.0.0.1:19380",
    ],
)
def test_ragflow_settings_reject_unsafe_base_url(base_url: str) -> None:
    with pytest.raises(ConfigurationError, match="loopback"):
        RagFlowSettings.from_mapping({"RAGFLOW_BASE_URL": base_url})


@pytest.mark.parametrize("timeout", ["invalid", "0", "301", "nan", "inf"])
def test_ragflow_settings_reject_invalid_timeout(timeout: str) -> None:
    with pytest.raises(ConfigurationError, match="RAGFLOW_TIMEOUT_SECONDS"):
        RagFlowSettings.from_mapping({"RAGFLOW_TIMEOUT_SECONDS": timeout})
