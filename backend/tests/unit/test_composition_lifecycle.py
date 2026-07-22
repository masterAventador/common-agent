from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import common_agent.api.app as api_app
import common_agent.worker_app as worker_app
from common_agent.bootstrap import AuditSettings


class _DatabaseProbe:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def start(self) -> None:
        self.calls.append("start")

    async def stop(self) -> None:
        self.calls.append("stop")


def _raise_bootstrap_failure() -> None:
    raise RuntimeError("bootstrap failed")


def test_api_stops_started_database_when_component_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _DatabaseProbe()
    app = FastAPI()
    app.state.database = database
    app.state.audit_settings = AuditSettings(
        retention_days=365,
        maximum_events_per_scope=1_000_000,
    )
    app.state.auth_settings = object()
    monkeypatch.setattr(api_app, "Argon2PasswordHasher", _raise_bootstrap_failure)

    async def run() -> None:
        async with api_app.lifespan(app):
            pytest.fail("应用装配失败后不应进入 serving 阶段")

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        asyncio.run(run())

    assert database.calls == ["start", "stop"]


def test_worker_stops_started_database_when_settings_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _DatabaseProbe()
    monkeypatch.setattr(worker_app, "Database", lambda _: database)
    monkeypatch.setattr(
        worker_app.DatabaseSettings,
        "from_env",
        lambda: SimpleNamespace(url="mysql+aiomysql://unused"),
    )
    monkeypatch.setattr(worker_app.WorkerSettings, "from_env", _raise_bootstrap_failure)

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        asyncio.run(worker_app.run_worker(asyncio.Event()))

    assert database.calls == ["start", "stop"]
