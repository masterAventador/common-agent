from pathlib import Path

import pytest

from common_agent.bootstrap.settings import (
    ApiSettings,
    AuthSettings,
    ConfigurationError,
    CorsSettings,
    DatabaseSettings,
    IntegrationModeSettings,
    RagFlowSettings,
    RuntimeEnvironmentSettings,
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


def test_production_runtime_requires_container_bind_and_secure_service_addresses() -> None:
    values = {
        "COMMON_AGENT_RUNTIME_ENV": "production",
        "COMMON_AGENT_API_HOST": "0.0.0.0",
        "COMMON_AGENT_API_PORT": "8000",
        "COMMON_AGENT_DATABASE_URL": (
            "mysql+aiomysql://common_agent:secret@platform-mysql:3306/common_agent"
        ),
        "COMMON_AGENT_CORS_ORIGINS": "https://agent.example.com",
        "COMMON_AGENT_AUTH_COOKIE_SECURE": "true",
        "RAGFLOW_BASE_URL": "https://ragflow.internal:9380",
        "RAGFLOW_CA_BUNDLE": "/run/common-agent/tls/ca-bundle.crt",
    }

    assert RuntimeEnvironmentSettings.from_mapping(values).environment == "production"
    assert ApiSettings.from_mapping(values).host == "0.0.0.0"
    assert DatabaseSettings.from_mapping(values).url == values["COMMON_AGENT_DATABASE_URL"]
    assert CorsSettings.from_mapping(values).origins == ("https://agent.example.com",)
    assert AuthSettings.from_mapping(values).cookie_secure is True
    assert RagFlowSettings.from_mapping(values).base_url == "https://ragflow.internal:9380"
    assert RagFlowSettings.from_mapping(values).ca_bundle_path == Path(
        "/run/common-agent/tls/ca-bundle.crt"
    )


@pytest.mark.parametrize(
    ("settings_type", "values", "message"),
    [
        (
            ApiSettings,
            {"COMMON_AGENT_RUNTIME_ENV": "production", "COMMON_AGENT_API_HOST": "127.0.0.1"},
            "COMMON_AGENT_API_HOST",
        ),
        (
            DatabaseSettings,
            {
                "COMMON_AGENT_RUNTIME_ENV": "production",
                "COMMON_AGENT_DATABASE_URL": (
                    "mysql+aiomysql://common_agent:secret@127.0.0.1:3306/common_agent"
                ),
            },
            "COMMON_AGENT_DATABASE_URL",
        ),
        (
            CorsSettings,
            {
                "COMMON_AGENT_RUNTIME_ENV": "production",
                "COMMON_AGENT_CORS_ORIGINS": "http://agent.example.com",
            },
            "COMMON_AGENT_CORS_ORIGINS",
        ),
        (
            AuthSettings,
            {
                "COMMON_AGENT_RUNTIME_ENV": "production",
                "COMMON_AGENT_AUTH_COOKIE_SECURE": "false",
            },
            "COMMON_AGENT_AUTH_COOKIE_SECURE",
        ),
        (
            RagFlowSettings,
            {
                "COMMON_AGENT_RUNTIME_ENV": "production",
                "RAGFLOW_BASE_URL": "http://ragflow.internal:9380",
            },
            "RAGFLOW_BASE_URL",
        ),
    ],
)
def test_production_runtime_rejects_local_or_insecure_addresses(
    settings_type: type[object],
    values: dict[str, str],
    message: str,
) -> None:
    with pytest.raises(ConfigurationError, match=message):
        settings_type.from_mapping(values)  # type: ignore[attr-defined]


def test_runtime_environment_defaults_local_and_rejects_unknown_values() -> None:
    assert RuntimeEnvironmentSettings.from_mapping({}).environment == "local"
    with pytest.raises(ConfigurationError, match="COMMON_AGENT_RUNTIME_ENV"):
        RuntimeEnvironmentSettings.from_mapping({"COMMON_AGENT_RUNTIME_ENV": "staging"})


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


def test_auth_settings_default_to_closed_registration_and_bounded_sessions() -> None:
    settings = AuthSettings.from_mapping({})

    assert settings.bootstrap_token.get_secret_value() == ""
    assert settings.session_idle_seconds == 1800
    assert settings.session_absolute_seconds == 43200
    assert settings.login_window_seconds == 900
    assert settings.login_max_attempts == 5
    assert settings.cookie_secure is False


def test_auth_settings_accept_secure_bootstrap_without_leaking_token() -> None:
    token = "bootstrap-token-that-is-at-least-32-characters"

    settings = AuthSettings.from_mapping(
        {
            "COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN": token,
            "COMMON_AGENT_AUTH_COOKIE_SECURE": "true",
            "COMMON_AGENT_AUTH_SESSION_IDLE_SECONDS": "1200",
            "COMMON_AGENT_AUTH_SESSION_ABSOLUTE_SECONDS": "7200",
        }
    )

    assert settings.bootstrap_token.get_secret_value() == token
    assert settings.cookie_secure is True
    assert settings.session_idle_seconds == 1200
    assert settings.session_absolute_seconds == 7200
    assert token not in repr(settings)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN", "too-short"),
        ("COMMON_AGENT_AUTH_COOKIE_SECURE", "sometimes"),
        ("COMMON_AGENT_AUTH_SESSION_IDLE_SECONDS", "59"),
        ("COMMON_AGENT_AUTH_SESSION_ABSOLUTE_SECONDS", "3599"),
        ("COMMON_AGENT_AUTH_LOGIN_WINDOW_SECONDS", "not-a-number"),
        ("COMMON_AGENT_AUTH_LOGIN_MAX_ATTEMPTS", "0"),
    ],
)
def test_auth_settings_reject_unsafe_values(name: str, value: str) -> None:
    with pytest.raises(ConfigurationError, match=name):
        AuthSettings.from_mapping({name: value})


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
    assert settings.expected_version == "v0.26.4"
    assert settings.timeout_seconds == 60
    assert settings.api_key.get_secret_value() == ""
    assert settings.embedding_model == (
        "text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible"
    )
    assert settings.rerank_model == ("qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible")


def test_ragflow_settings_accept_safe_override_without_leaking_key() -> None:
    settings = RagFlowSettings.from_mapping(
        {
            "RAGFLOW_BASE_URL": "http://localhost:29380/",
            "RAGFLOW_API_KEY": "do-not-leak",
            "RAGFLOW_EXPECTED_VERSION": "v0.26.4",
            "RAGFLOW_TIMEOUT_SECONDS": "120",
            "RAGFLOW_EMBEDDING_MODEL": (
                "text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible"
            ),
            "RAGFLOW_RERANK_MODEL": ("qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible"),
        }
    )

    assert settings.base_url == "http://localhost:29380"
    assert settings.timeout_seconds == 120
    assert "do-not-leak" not in repr(settings)


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("RAGFLOW_EMBEDDING_MODEL", "BAAI/bge-m3"),
        ("RAGFLOW_EMBEDDING_MODEL", "text-embedding-v4@OpenAI-API-Compatible"),
        ("RAGFLOW_RERANK_MODEL", "BAAI/bge-reranker-v2-m3"),
        ("RAGFLOW_RERANK_MODEL", "gte-rerank-v2@Tongyi-Qianwen"),
    ],
)
def test_ragflow_settings_reject_non_bailian_knowledge_models(name: str, value: str) -> None:
    with pytest.raises(ConfigurationError, match=name):
        RagFlowSettings.from_mapping({name: value})


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
