from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
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
    url: str

    @classmethod
    def from_env(cls) -> DatabaseSettings:
        return cls.from_mapping(os.environ)

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, str],
        *,
        project_root: Path | None = None,
    ) -> DatabaseSettings:
        configured = values.get("COMMON_AGENT_DATABASE_URL")
        if configured:
            return cls(url=configured)

        root = project_root or _find_project_root()
        database_path = root / ".local" / "common-agent.db"
        return cls(url=f"sqlite+aiosqlite:///{database_path}")


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


class ModelSettings(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    provider: Literal["bailian"] = "bailian"
    api_key: SecretStr
    base_url: str
    model: str

    @classmethod
    def from_env(cls) -> ModelSettings:
        values = _demo_values(None)
        for key in ("BAILIAN_API_KEY", "BAILIAN_BASE_URL", "BAILIAN_MODEL"):
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

        parsed = urlparse(base_url)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ConfigurationError("BAILIAN_BASE_URL must be a valid HTTPS URL")

        return cls(
            api_key=SecretStr(api_key),
            base_url=base_url.rstrip("/"),
            model=model,
        )


def _find_project_root() -> Path:
    candidates = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    for candidate in candidates:
        if (candidate / "CLAUDE.md").is_file():
            return candidate
    return Path.cwd()


def _demo_values(path: Path | None) -> dict[str, str]:
    demo_path = path or Path(__file__).resolve().parents[3] / ".env.demo"
    parsed = dotenv_values(demo_path, interpolate=False)
    return {key: value for key, value in parsed.items() if value is not None}


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "").strip()
    if not value:
        raise ConfigurationError(f"{key} is required")
    return value
