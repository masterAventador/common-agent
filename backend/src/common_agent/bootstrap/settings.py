from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from math import isfinite
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, SecretStr


class ConfigurationError(ValueError):
    """Raised when local runtime configuration is unsafe or invalid."""


@dataclass(frozen=True, slots=True)
class ApiSettings:
    host: str
    port: int

    @classmethod
    def from_env(cls) -> ApiSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> ApiSettings:
        host = values.get("COMMON_AGENT_API_HOST", "127.0.0.1")
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ConfigurationError("COMMON_AGENT_API_HOST must be a loopback address")

        raw_port = values.get("COMMON_AGENT_API_PORT", "18200")
        try:
            port = int(raw_port)
        except ValueError as error:
            raise ConfigurationError("COMMON_AGENT_API_PORT must be an integer") from error

        if not 1 <= port <= 65535:
            raise ConfigurationError("COMMON_AGENT_API_PORT must be between 1 and 65535")

        return cls(host=host, port=port)


@dataclass(frozen=True, slots=True)
class DatabaseSettings:
    url: str = field(repr=False)

    @classmethod
    def from_env(cls) -> DatabaseSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> DatabaseSettings:
        configured = values.get(
            "COMMON_AGENT_DATABASE_URL",
            "mysql+aiomysql://common_agent:common_agent_dev@127.0.0.1:19506/"
            "common_agent?charset=utf8mb4",
        ).strip()
        parsed = urlparse(configured)
        if parsed.scheme != "mysql+aiomysql":
            raise ConfigurationError("COMMON_AGENT_DATABASE_URL must use mysql+aiomysql")
        if parsed.hostname not in {"127.0.0.1", "::1", "localhost"}:
            raise ConfigurationError("COMMON_AGENT_DATABASE_URL must use a loopback host")
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
        configured = values.get("COMMON_AGENT_CORS_ORIGINS", "http://127.0.0.1:18280")
        origins = tuple(
            origin.strip().rstrip("/") for origin in configured.split(",") if origin.strip()
        )
        if not origins:
            raise ConfigurationError("COMMON_AGENT_CORS_ORIGINS must not be empty")

        for origin in origins:
            parsed = urlparse(origin)
            if (
                parsed.scheme not in {"http", "https"}
                or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
                or parsed.path not in {"", "/"}
            ):
                raise ConfigurationError("COMMON_AGENT_CORS_ORIGINS must contain loopback origins")

        return cls(origins=origins)


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
    expected_version: str
    embedding_model: str
    rerank_model: str
    timeout_seconds: float

    @classmethod
    def from_env(cls) -> RagFlowSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(cls, values: Mapping[str, str]) -> RagFlowSettings:
        base_url = values.get("RAGFLOW_BASE_URL", "http://127.0.0.1:19380").strip().rstrip("/")
        parsed = urlparse(base_url)
        try:
            port = parsed.port
        except ValueError as error:
            raise ConfigurationError("RAGFLOW_BASE_URL must be a loopback HTTP(S) URL") from error
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.hostname not in {"127.0.0.1", "::1", "localhost"}
            or port is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ConfigurationError("RAGFLOW_BASE_URL must be a loopback HTTP(S) URL")

        expected_version = values.get("RAGFLOW_EXPECTED_VERSION", "v0.25.6").strip()
        if not expected_version:
            raise ConfigurationError("RAGFLOW_EXPECTED_VERSION is required")

        embedding_model = values.get(
            "RAGFLOW_EMBEDDING_MODEL", "text-embedding-v4@Tongyi-Qianwen"
        ).strip()
        if embedding_model != "text-embedding-v4@Tongyi-Qianwen":
            raise ConfigurationError(
                "RAGFLOW_EMBEDDING_MODEL must be text-embedding-v4@Tongyi-Qianwen"
            )

        rerank_model = values.get("RAGFLOW_RERANK_MODEL", "qwen3-rerank@Tongyi-Qianwen").strip()
        if rerank_model != "qwen3-rerank@Tongyi-Qianwen":
            raise ConfigurationError("RAGFLOW_RERANK_MODEL must be qwen3-rerank@Tongyi-Qianwen")

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
