from __future__ import annotations

import base64
import binascii
import hashlib
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from ipaddress import IPv4Network, IPv6Network, ip_network
from math import isfinite
from pathlib import Path
from types import MappingProxyType
from typing import Literal
from urllib.parse import urlparse

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, SecretStr


class ConfigurationError(ValueError):
    """Raised when local runtime configuration is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class RuntimeEnvironmentSettings:
    environment: Literal["local", "production"]

    @classmethod
    def from_env(cls) -> RuntimeEnvironmentSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> RuntimeEnvironmentSettings:
        environment = values.get("COMMON_AGENT_RUNTIME_ENV", "local").strip().lower()
        if environment == "local":
            return cls(environment="local")
        if environment == "production":
            return cls(environment="production")
        raise ConfigurationError("COMMON_AGENT_RUNTIME_ENV must be local or production")


@dataclass(frozen=True, slots=True)
class ApiSettings:
    host: str
    port: int

    @classmethod
    def from_env(cls) -> ApiSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> ApiSettings:
        runtime = RuntimeEnvironmentSettings.from_mapping(values)
        host = values.get("COMMON_AGENT_API_HOST", "127.0.0.1")
        if runtime.environment == "local":
            if host not in {"127.0.0.1", "::1", "localhost"}:
                raise ConfigurationError("COMMON_AGENT_API_HOST must be a loopback address")
        elif host not in {"0.0.0.0", "::"}:
            raise ConfigurationError(
                "COMMON_AGENT_API_HOST must be a container wildcard address in production"
            )

        raw_port = values.get("COMMON_AGENT_API_PORT", "18200")
        try:
            port = int(raw_port)
        except ValueError as error:
            raise ConfigurationError("COMMON_AGENT_API_PORT must be an integer") from error

        if not 1 <= port <= 65535:
            raise ConfigurationError("COMMON_AGENT_API_PORT must be between 1 and 65535")

        return cls(host=host, port=port)


@dataclass(frozen=True, slots=True)
class ProxySettings:
    forwarded_allow_ips: str

    @classmethod
    def from_env(cls) -> ProxySettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> ProxySettings:
        runtime = RuntimeEnvironmentSettings.from_mapping(values)
        configured = values.get(
            "COMMON_AGENT_TRUSTED_PROXY_IPS",
            "127.0.0.1" if runtime.environment == "local" else "",
        ).strip()
        if runtime.environment == "local":
            if configured not in {"127.0.0.1", "::1"}:
                raise ConfigurationError(
                    "COMMON_AGENT_TRUSTED_PROXY_IPS must contain one loopback proxy locally"
                )
        elif configured != "*":
            raise ConfigurationError(
                "COMMON_AGENT_TRUSTED_PROXY_IPS must be * behind the private production edge"
            )
        return cls(forwarded_allow_ips=configured)


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    url: str = field(repr=False)

    @classmethod
    def from_env(cls) -> DatabaseSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> DatabaseSettings:
        runtime = RuntimeEnvironmentSettings.from_mapping(values)
        configured = values.get(
            "COMMON_AGENT_DATABASE_URL",
            "mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/"
            "common_agent?charset=utf8mb4",
        ).strip()
        parsed = urlparse(configured)
        if parsed.scheme != "mysql+aiomysql":
            raise ConfigurationError("COMMON_AGENT_DATABASE_URL must use mysql+aiomysql")
        if runtime.environment == "local":
            if parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
                raise ConfigurationError("COMMON_AGENT_DATABASE_URL must use a loopback host")
        elif not parsed.hostname or parsed.hostname in {"127.0.0.1", "::1", "localhost"}:
            raise ConfigurationError(
                "COMMON_AGENT_DATABASE_URL must use a non-loopback service host in production"
            )
        try:
            port = parsed.port
        except ValueError as error:
            raise ConfigurationError("COMMON_AGENT_DATABASE_URL has an invalid port") from error
        if (
            port is None
            or not parsed.username
            or not parsed.password
            or not parsed.path.lstrip("/")
        ):
            raise ConfigurationError(
                "COMMON_AGENT_DATABASE_URL must include user, password, port and database"
            )
        return cls(url=configured)


@dataclass(frozen=True, slots=True)
class CorsSettings:
    origins: tuple[str, ...]

    @classmethod
    def from_env(cls) -> CorsSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> CorsSettings:
        runtime = RuntimeEnvironmentSettings.from_mapping(values)
        configured = values.get("COMMON_AGENT_CORS_ORIGINS", "http://127.0.0.1:18280")
        origins = tuple(
            origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()
        )
        if not origins:
            raise ConfigurationError("COMMON_AGENT_CORS_ORIGINS must not be empty")

        for origin in origins:
            parsed = urlparse(origin)
            if runtime.environment == "local":
                if (
                    parsed.scheme not in {"http", "https"}
                    or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                    or parsed.path not in {"", "/"}
                ):
                    raise ConfigurationError(
                        "COMMON_AGENT_CORS_ORIGINS must contain loopback origins"
                    )
            elif (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.hostname in {"127.0.0.1", "::1", "localhost"}
                or parsed.username is not None
                or parsed.password is not None
                or parsed.path not in {"", "/"}
                or parsed.params
                or parsed.query
                or parsed.fragment
            ):
                raise ConfigurationError(
                    "COMMON_AGENT_CORS_ORIGINS must contain secure production origins"
                )

        return cls(origins=origins)


@dataclass(frozen=True, slots=True)
class AuthSettings:
    bootstrap_token: SecretStr
    session_idle_seconds: int
    session_absolute_seconds: int
    login_window_seconds: int
    login_max_attempts: int
    cookie_secure: bool

    @property
    def session_cookie_name(self) -> str:
        if self.cookie_secure:
            return "__Host-common-agent-session"
        return "common_agent_session"

    @classmethod
    def from_env(cls) -> AuthSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> AuthSettings:
        raw_bootstrap_token = values.get("COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN", "").strip()
        if raw_bootstrap_token and not 32 <= len(raw_bootstrap_token) <= 256:
            raise ConfigurationError(
                "COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN must be between 32 and 256 characters"
            )

        session_idle_seconds = _bounded_auth_int(
            values,
            "COMMON_AGENT_AUTH_SESSION_IDLE_SECONDS",
            default=1800,
            minimum=300,
            maximum=3600,
        )
        session_absolute_seconds = _bounded_auth_int(
            values,
            "COMMON_AGENT_AUTH_SESSION_ABSOLUTE_SECONDS",
            default=43200,
            minimum=3600,
            maximum=86400,
        )
        if session_absolute_seconds < session_idle_seconds:
            raise ConfigurationError(
                "COMMON_AGENT_AUTH_SESSION_ABSOLUTE_SECONDS must not be shorter than idle time"
            )

        cookie_secure = _strict_bool(
            values,
            "COMMON_AGENT_AUTH_COOKIE_SECURE",
            default=False,
        )
        if (
            RuntimeEnvironmentSettings.from_mapping(values).environment == "production"
            and not cookie_secure
        ):
            raise ConfigurationError("COMMON_AGENT_AUTH_COOKIE_SECURE must be true in production")

        return cls(
            bootstrap_token=SecretStr(raw_bootstrap_token),
            session_idle_seconds=session_idle_seconds,
            session_absolute_seconds=session_absolute_seconds,
            login_window_seconds=_bounded_auth_int(
                values,
                "COMMON_AGENT_AUTH_LOGIN_WINDOW_SECONDS",
                default=900,
                minimum=60,
                maximum=3600,
            ),
            login_max_attempts=_bounded_auth_int(
                values,
                "COMMON_AGENT_AUTH_LOGIN_MAX_ATTEMPTS",
                default=5,
                minimum=3,
                maximum=20,
            ),
            cookie_secure=cookie_secure,
        )


@dataclass(frozen=True, slots=True)
class AuditSettings:
    retention_days: int
    maximum_events_per_scope: int

    @classmethod
    def from_env(cls) -> AuditSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> AuditSettings:
        return cls(
            retention_days=_bounded_auth_int(
                values,
                "COMMON_AGENT_AUDIT_RETENTION_DAYS",
                default=365,
                minimum=30,
                maximum=3650,
            ),
            maximum_events_per_scope=_bounded_auth_int(
                values,
                "COMMON_AGENT_AUDIT_MAX_EVENTS_PER_SCOPE",
                default=1_000_000,
                minimum=100,
                maximum=10_000_000,
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolCredentialSettings:
    keys: Mapping[str, bytes] = field(repr=False)
    active_key_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "keys", MappingProxyType(dict(self.keys)))

    @classmethod
    def from_env(cls) -> ToolCredentialSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> ToolCredentialSettings:
        runtime = RuntimeEnvironmentSettings.from_mapping(values)
        configured = values.get("COMMON_AGENT_TOOL_CREDENTIAL_KEYS", "").strip()
        if not configured:
            if runtime.environment == "production":
                raise ConfigurationError(
                    "COMMON_AGENT_TOOL_CREDENTIAL_KEYS is required in production"
                )
            key_id = "local-dev-v1"
            key = hashlib.sha256(b"common-agent local MCP credential development key v1").digest()
            return cls(keys={key_id: key}, active_key_id=key_id)

        parsed: dict[str, bytes] = {}
        try:
            for item in configured.split(","):
                key_id, separator, encoded = item.strip().partition(":")
                if not separator or not key_id or key_id in parsed:
                    raise ValueError
                decoded = base64.b64decode(encoded, altchars=b"-_", validate=True)
                if len(decoded) != 32:
                    raise ValueError
                parsed[key_id] = decoded
        except (ValueError, binascii.Error):
            raise ConfigurationError(
                "COMMON_AGENT_TOOL_CREDENTIAL_KEYS must contain unique id:base64-32-byte entries"
            ) from None
        active = values.get("COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID", "").strip()
        if not active:
            if len(parsed) != 1:
                raise ConfigurationError(
                    "COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID is required for a multi-key keyring"
                )
            active = next(iter(parsed))
        if active not in parsed:
            raise ConfigurationError(
                "COMMON_AGENT_TOOL_CREDENTIAL_ACTIVE_KEY_ID must identify a configured key"
            )
        return cls(keys=parsed, active_key_id=active)


@dataclass(frozen=True, slots=True)
class ToolEgressSettings:
    allowed_hosts: tuple[str, ...]
    allowed_cidrs: tuple[IPv4Network | IPv6Network, ...]
    http_allowed_hosts: tuple[str, ...]
    allow_loopback: bool
    connect_timeout_seconds: float
    read_timeout_seconds: float
    call_timeout_seconds: float
    maximum_response_bytes: int
    maximum_concurrency: int

    @classmethod
    def from_env(cls) -> ToolEgressSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> ToolEgressSettings:
        runtime = RuntimeEnvironmentSettings.from_mapping(values)
        local = runtime.environment == "local"
        allowed_hosts = _exact_hosts(
            values.get(
                "COMMON_AGENT_TOOL_EGRESS_ALLOWED_HOSTS",
                "localhost" if local else "",
            ),
            "COMMON_AGENT_TOOL_EGRESS_ALLOWED_HOSTS",
        )
        allowed_cidrs = _tool_egress_cidrs(
            values.get(
                "COMMON_AGENT_TOOL_EGRESS_ALLOWED_CIDRS",
                "127.0.0.0/8,::1/128" if local else "",
            )
        )
        http_allowed_hosts = _exact_hosts(
            values.get(
                "COMMON_AGENT_TOOL_EGRESS_HTTP_ALLOWED_HOSTS",
                "localhost" if local else "",
            ),
            "COMMON_AGENT_TOOL_EGRESS_HTTP_ALLOWED_HOSTS",
        )
        if not set(http_allowed_hosts).issubset(allowed_hosts):
            raise ConfigurationError(
                "COMMON_AGENT_TOOL_EGRESS_HTTP_ALLOWED_HOSTS must be a subset of "
                "COMMON_AGENT_TOOL_EGRESS_ALLOWED_HOSTS"
            )
        connect_timeout = _bounded_float(
            values,
            "COMMON_AGENT_TOOL_EGRESS_CONNECT_TIMEOUT_SECONDS",
            default=5.0,
            maximum=30.0,
        )
        read_timeout = _bounded_float(
            values,
            "COMMON_AGENT_TOOL_EGRESS_READ_TIMEOUT_SECONDS",
            default=30.0,
            maximum=300.0,
        )
        call_timeout = _bounded_float(
            values,
            "COMMON_AGENT_TOOL_EGRESS_CALL_TIMEOUT_SECONDS",
            default=60.0,
            maximum=600.0,
        )
        if call_timeout < connect_timeout or call_timeout < read_timeout:
            raise ConfigurationError(
                "COMMON_AGENT_TOOL_EGRESS_CALL_TIMEOUT_SECONDS must not be shorter than "
                "connect or read timeout"
            )
        return cls(
            allowed_hosts=allowed_hosts,
            allowed_cidrs=allowed_cidrs,
            http_allowed_hosts=http_allowed_hosts,
            allow_loopback=_strict_bool(
                values,
                "COMMON_AGENT_TOOL_EGRESS_ALLOW_LOOPBACK",
                default=local,
            ),
            connect_timeout_seconds=connect_timeout,
            read_timeout_seconds=read_timeout,
            call_timeout_seconds=call_timeout,
            maximum_response_bytes=_bounded_auth_int(
                values,
                "COMMON_AGENT_TOOL_EGRESS_MAX_RESPONSE_BYTES",
                default=1_048_576,
                minimum=1_024,
                maximum=16_777_216,
            ),
            maximum_concurrency=_bounded_auth_int(
                values,
                "COMMON_AGENT_TOOL_EGRESS_MAX_CONCURRENCY",
                default=16,
                minimum=1,
                maximum=256,
            ),
        )


@dataclass(frozen=True, slots=True)
class WorkerSettings:
    poll_interval_seconds: float
    lease_seconds: int
    heartbeat_seconds: int
    maximum_attempts: int
    claim_batch_size: int
    event_retention_days: int
    maximum_events_per_stream: int

    @classmethod
    def from_env(cls) -> WorkerSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> WorkerSettings:
        lease_seconds = _bounded_auth_int(
            values,
            "COMMON_AGENT_WORKER_LEASE_SECONDS",
            default=60,
            minimum=3,
            maximum=3600,
        )
        heartbeat_seconds = _bounded_auth_int(
            values,
            "COMMON_AGENT_WORKER_HEARTBEAT_SECONDS",
            default=10,
            minimum=1,
            maximum=1200,
        )
        if heartbeat_seconds * 2 >= lease_seconds:
            raise ConfigurationError(
                "COMMON_AGENT_WORKER_HEARTBEAT_SECONDS must be less than half of "
                "COMMON_AGENT_WORKER_LEASE_SECONDS"
            )

        return cls(
            poll_interval_seconds=_bounded_float(
                values,
                "COMMON_AGENT_WORKER_POLL_INTERVAL_SECONDS",
                default=0.25,
                maximum=10.0,
            ),
            lease_seconds=lease_seconds,
            heartbeat_seconds=heartbeat_seconds,
            maximum_attempts=_bounded_auth_int(
                values,
                "COMMON_AGENT_WORKER_MAXIMUM_ATTEMPTS",
                default=3,
                minimum=1,
                maximum=10,
            ),
            claim_batch_size=_bounded_auth_int(
                values,
                "COMMON_AGENT_WORKER_CLAIM_BATCH_SIZE",
                default=8,
                minimum=2,
                maximum=100,
            ),
            event_retention_days=_bounded_auth_int(
                values,
                "COMMON_AGENT_EVENT_RETENTION_DAYS",
                default=30,
                minimum=1,
                maximum=3650,
            ),
            maximum_events_per_stream=_bounded_auth_int(
                values,
                "COMMON_AGENT_EVENT_MAX_PER_STREAM",
                default=100_000,
                minimum=100,
                maximum=1_000_000,
            ),
        )


@dataclass(frozen=True, slots=True)
class IntegrationModeSettings:
    mode: Literal["real", "demo"]

    @classmethod
    def from_env(cls) -> IntegrationModeSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> IntegrationModeSettings:
        mode = values.get("COMMON_AGENT_INTEGRATION_MODE", "real").strip().lower()
        if mode == "real":
            return cls(mode="real")
        if mode == "demo":
            return cls(mode="demo")
        raise ConfigurationError("COMMON_AGENT_INTEGRATION_MODE must be real or demo")


@dataclass(frozen=True, slots=True)
class RagFlowSettings:
    base_url: str
    api_key: SecretStr
    ca_bundle_path: Path | None
    expected_version: str
    embedding_model: str
    rerank_model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> RagFlowSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> RagFlowSettings:
        runtime = RuntimeEnvironmentSettings.from_mapping(values)
        base_url = values.get("RAGFLOW_BASE_URL", "http://127.0.0.1:19380").strip().rstrip("/")
        parsed = urlparse(base_url)
        try:
            port = parsed.port
        except ValueError as error:
            raise ConfigurationError("RAGFLOW_BASE_URL must be a loopback HTTP(S) URL") from error
        invalid_common = (
            port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or bool(parsed.query)
            or bool(parsed.fragment)
        )
        if runtime.environment == "local":
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                or invalid_common
            ):
                raise ConfigurationError("RAGFLOW_BASE_URL must be a loopback HTTP(S) URL")
        elif (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.hostname in {"127.0.0.1", "::1", "localhost"}
            or invalid_common
        ):
            raise ConfigurationError("RAGFLOW_BASE_URL must be a secure production service URL")

        raw_ca_bundle = values.get("RAGFLOW_CA_BUNDLE", "").strip()
        ca_bundle_path = Path(raw_ca_bundle) if raw_ca_bundle else None
        if ca_bundle_path is not None and not ca_bundle_path.is_absolute():
            raise ConfigurationError("RAGFLOW_CA_BUNDLE must be an absolute path")
        if runtime.environment == "production" and ca_bundle_path is None:
            raise ConfigurationError("RAGFLOW_CA_BUNDLE is required in production")

        expected_version = values.get("RAGFLOW_EXPECTED_VERSION", "v0.26.4").strip()
        if not expected_version:
            raise ConfigurationError("RAGFLOW_EXPECTED_VERSION is required")

        embedding_model = values.get(
            "RAGFLOW_EMBEDDING_MODEL",
            "text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible",
        ).strip()
        if embedding_model != "text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible":
            raise ConfigurationError(
                "RAGFLOW_EMBEDDING_MODEL must be "
                "text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible"
            )

        rerank_model = values.get(
            "RAGFLOW_RERANK_MODEL",
            "qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible",
        ).strip()
        if rerank_model != "qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible":
            raise ConfigurationError(
                "RAGFLOW_RERANK_MODEL must be "
                "qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible"
            )

        raw_timeout = values.get("RAGFLOW_TIMEOUT_SECONDS", "60")
        try:
            timeout_seconds = float(raw_timeout)
        except ValueError as error:
            raise ConfigurationError("RAGFLOW_TIMEOUT_SECONDS must be a number") from error
        if not isfinite(timeout_seconds) or not 0 < timeout_seconds <= 300:
            raise ConfigurationError("RAGFLOW_TIMEOUT_SECONDS must be between 0 and 300")

        return cls(
            base_url=base_url,
            api_key=SecretStr(values.get("RAGFLOW_API_KEY", "").strip()),
            ca_bundle_path=ca_bundle_path,
            expected_version=expected_version,
            embedding_model=embedding_model,
            rerank_model=rerank_model,
            timeout_seconds=timeout_seconds,
        )


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["bailian"] = "bailian"
    api_key: SecretStr
    base_url: str
    model: str
    timeout_seconds: float = 60.0
    stream_chunk_timeout_seconds: float = 60.0
    max_retries: int = 2

    @classmethod
    def from_env(cls) -> ModelSettings:
        values = _demo_values(None)
        for key in (
            "BAILIAN_API_KEY",
            "BAILIAN_BASE_URL",
            "BAILIAN_MODEL",
            "BAILIAN_TIMEOUT_SECONDS",
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS",
            "BAILIAN_MAX_RETRIES",
        ):
            configured = os.environ.get(key)
            if configured:
                values[key] = configured
        return cls.from_mapping(values)

    @classmethod
    def from_demo_file(cls, path: Path | None = None) -> ModelSettings:
        return cls.from_mapping(_demo_values(path))

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> ModelSettings:
        api_key = _required(values, "BAILIAN_API_KEY")
        base_url = _required(values, "BAILIAN_BASE_URL")
        model = _required(values, "BAILIAN_MODEL")
        timeout_seconds = _bounded_float(
            values,
            "BAILIAN_TIMEOUT_SECONDS",
            default=60.0,
            maximum=300.0,
        )
        stream_chunk_timeout_seconds = _bounded_float(
            values,
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS",
            default=60.0,
            maximum=300.0,
        )
        max_retries = _bounded_int(
            values,
            "BAILIAN_MAX_RETRIES",
            default=2,
            maximum=3,
        )

        parsed = urlparse(base_url)
        try:
            port = parsed.port
        except ValueError as error:
            raise ConfigurationError(
                "BAILIAN_BASE_URL must be an official HTTPS endpoint"
            ) from error
        host = parsed.hostname or ""
        if (
            parsed.scheme != "https"
            or not _is_bailian_host(host)
            or port not in {None, 443}
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path.rstrip("/") != "/compatible-mode/v1"
            or parsed.params
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError("BAILIAN_BASE_URL must be an official HTTPS endpoint")

        return cls(
            api_key=SecretStr(api_key),
            base_url=base_url.rstrip("/"),
            model=model,
            timeout_seconds=timeout_seconds,
            stream_chunk_timeout_seconds=stream_chunk_timeout_seconds,
            max_retries=max_retries,
        )


def _demo_values(path: Path | None) -> dict[str, str]:
    demo_path = path or Path(__file__).resolve().parents[3] / ".env.demo"
    parsed = dotenv_values(demo_path, interpolate=False)
    return {key: value for key, value in parsed.items() if value is not None}


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is required")
    return value


def _bounded_float(
    values: Mapping[str, str],
    key: str,
    *,
    default: float,
    maximum: float,
) -> float:
    raw_value = values.get(key, str(default))
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{key} must be a number") from error
    if not isfinite(value) or not 0 < value <= maximum:
        raise ConfigurationError(f"{key} must be between 0 and {maximum:g}")
    return value


def _bounded_int(
    values: Mapping[str, str],
    key: str,
    *,
    default: int,
    maximum: int,
) -> int:
    raw_value = values.get(key, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{key} must be an integer") from error
    if not 0 <= value <= maximum:
        raise ConfigurationError(f"{key} must be between 0 and {maximum}")
    return value


def _bounded_auth_int(
    values: Mapping[str, str],
    key: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    raw_value = values.get(key, str(default))
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ConfigurationError(f"{key} must be an integer") from error
    if not minimum <= value <= maximum:
        raise ConfigurationError(f"{key} must be between {minimum} and {maximum}")
    return value


def _strict_bool(values: Mapping[str, str], key: str, *, default: bool) -> bool:
    raw_value = values.get(key, str(default)).strip().lower()
    if raw_value == "true":
        return True
    if raw_value == "false":
        return False
    raise ConfigurationError(f"{key} must be true or false")


def _exact_hosts(configured: str, key: str) -> tuple[str, ...]:
    hosts: set[str] = set()
    for raw in configured.split(","):
        host = raw.strip().lower().removeprefix("[").removesuffix("]").rstrip(".")
        if not host:
            continue
        if any(character.isspace() for character in host) or any(
            marker in host for marker in ("*", "/", "://")
        ):
            raise ConfigurationError(f"{key} must contain exact host names or IP addresses")
        hosts.add(host)
    return tuple(sorted(hosts))


def _tool_egress_cidrs(configured: str) -> tuple[IPv4Network | IPv6Network, ...]:
    networks: set[IPv4Network | IPv6Network] = set()
    try:
        for raw in configured.split(","):
            if raw.strip():
                networks.add(ip_network(raw.strip(), strict=True))
    except ValueError:
        raise ConfigurationError(
            "COMMON_AGENT_TOOL_EGRESS_ALLOWED_CIDRS must contain canonical IPv4/IPv6 CIDRs"
        ) from None
    return tuple(sorted(networks, key=lambda value: (value.version, int(value.network_address))))


def _is_bailian_host(host: str) -> bool:
    if host in {"dashscope.aliyuncs.com", "dashscope-intl.aliyuncs.com"}:
        return True
    return any(
        host.endswith(suffix) and host != suffix.removeprefix(".")
        for suffix in (
            ".cn-beijing.maas.aliyuncs.com",
            ".ap-southeast-1.maas.aliyuncs.com",
        )
    )
