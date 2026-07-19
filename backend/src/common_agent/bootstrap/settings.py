from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path


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


def _find_project_root() -> Path:
    candidates = [Path.cwd(), *Path.cwd().parents, *Path(__file__).resolve().parents]
    for candidate in candidates:
        if (candidate / "CLAUDE.md").is_file():
            return candidate
    return Path.cwd()
