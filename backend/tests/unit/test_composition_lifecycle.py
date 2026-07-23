from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

import common_agent.api.app as api_app
import common_agent.worker_app as worker_app
from common_agent.bootstrap import (
    AuditSettings,
    AuthSettings,
    DatabaseSettings,
    IntegrationModeSettings,
    ModelSettings,
    RagFlowIdentitySettings,
    RagFlowSettings,
    ToolCredentialSettings,
    ToolEgressSettings,
    WorkerSettings,
)


class _DatabaseProbe:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def start(self) -> None:
        self.calls.append("start")

    async def stop(self) -> None:
        self.calls.append("stop")


class _ClosableProbe:
    provider_name = "probe"

    def __init__(self) -> None:
        self.closed = False

    async def aclose(self) -> None:
        self.closed = True


class _TenancyStoreProbe:
    async def list_tenant_ids(self) -> tuple[object, ...]:
        return ()


class _PlatformToolSeederProbe:
    async def seed_all(self, tenant_ids: object) -> None:
        del tenant_ids

    async def seed(self, tenant_id: object) -> None:
        del tenant_id


class _RagFlowIdentityProbe:
    async def ensure_all(self, tenant_ids: object) -> None:
        del tenant_ids

    async def ensure(self, tenant_id: object) -> None:
        del tenant_id

    async def api_key_for(self, tenant_id: object) -> str:
        del tenant_id
        return "test-key"


def _stub_platform_tool_bootstrap(monkeypatch: pytest.MonkeyPatch, module: object) -> None:
    monkeypatch.setattr(module, "SqlAlchemyTenancyStore", lambda _: _TenancyStoreProbe())
    monkeypatch.setattr(
        module,
        "SqlAlchemyPlatformToolSeeder",
        lambda _: _PlatformToolSeederProbe(),
    )
    monkeypatch.setattr(
        module,
        "RagFlowTenantIdentityService",
        lambda *_, **__: _RagFlowIdentityProbe(),
    )


def _raise_bootstrap_failure() -> None:
    raise RuntimeError("bootstrap failed")


def _raise_component_bootstrap_failure(*args: object, **kwargs: object) -> None:
    del args, kwargs
    raise RuntimeError("component bootstrap failed")


def _ragflow_settings() -> SimpleNamespace:
    return SimpleNamespace(
        base_url="http://127.0.0.1:19380",
        api_key=SimpleNamespace(get_secret_value=lambda: "test-key"),
        expected_version="v0.26.4",
        embedding_model="embedding",
        rerank_model="rerank",
        timeout_seconds=1.0,
        ca_bundle_path=None,
    )


def _model_settings() -> SimpleNamespace:
    return SimpleNamespace(
        api_key=SimpleNamespace(get_secret_value=lambda: "bailian-key"),
        base_url="https://example.test/compatible-mode/v1",
    )


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


def test_api_closes_real_model_when_later_component_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _DatabaseProbe()
    knowledge = _ClosableProbe()
    model = _ClosableProbe()
    app = FastAPI()
    app.state.database = database
    app.state.audit_settings = AuditSettings(
        retention_days=365,
        maximum_events_per_scope=1_000_000,
    )
    app.state.auth_settings = AuthSettings.from_mapping({})
    app.state.integration_mode = SimpleNamespace(mode="real")
    app.state.worker_settings = object()
    app.state.tool_credential_settings = ToolCredentialSettings.from_mapping({})
    app.state.tool_egress_settings = ToolEgressSettings.from_mapping({})
    app.state.ragflow_settings = _ragflow_settings()
    app.state.ragflow_identity_settings = RagFlowIdentitySettings.from_mapping({})
    monkeypatch.setattr(api_app, "RagFlowKnowledgeService", lambda **_: knowledge)
    _stub_platform_tool_bootstrap(monkeypatch, api_app)
    monkeypatch.setattr(ModelSettings, "from_env", _model_settings)
    monkeypatch.setattr(api_app, "BailianChatModelAdapter", lambda _: model)
    monkeypatch.setattr(api_app, "KnowledgeBaseService", _raise_component_bootstrap_failure)

    async def run() -> None:
        async with api_app.lifespan(app):
            pytest.fail("应用装配失败后不应进入 serving 阶段")

    with pytest.raises(RuntimeError, match="component bootstrap failed"):
        asyncio.run(run())

    assert knowledge.closed is True
    assert model.closed is True
    assert database.calls == ["start", "stop"]


def test_worker_stops_started_database_when_settings_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _DatabaseProbe()
    monkeypatch.setattr(worker_app, "Database", lambda _: database)
    monkeypatch.setattr(
        DatabaseSettings,
        "from_env",
        lambda: SimpleNamespace(url="mysql+aiomysql://unused"),
    )
    monkeypatch.setattr(WorkerSettings, "from_env", _raise_bootstrap_failure)

    with pytest.raises(RuntimeError, match="bootstrap failed"):
        asyncio.run(worker_app.run_worker(asyncio.Event()))

    assert database.calls == ["start", "stop"]


def test_worker_closes_real_model_when_later_component_bootstrap_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database = _DatabaseProbe()
    knowledge = _ClosableProbe()
    model = _ClosableProbe()
    monkeypatch.setattr(worker_app, "Database", lambda _: database)
    monkeypatch.setattr(
        DatabaseSettings,
        "from_env",
        lambda: SimpleNamespace(url="mysql+aiomysql://unused"),
    )
    monkeypatch.setattr(WorkerSettings, "from_env", lambda: object())
    monkeypatch.setattr(
        IntegrationModeSettings,
        "from_env",
        lambda: SimpleNamespace(mode="real"),
    )
    monkeypatch.setattr(AuditSettings, "from_env", lambda: object())
    monkeypatch.setattr(RagFlowSettings, "from_env", _ragflow_settings)
    monkeypatch.setattr(worker_app, "RagFlowKnowledgeService", lambda **_: knowledge)
    _stub_platform_tool_bootstrap(monkeypatch, worker_app)
    monkeypatch.setattr(ModelSettings, "from_env", _model_settings)
    monkeypatch.setattr(worker_app, "BailianChatModelAdapter", lambda _: model)
    monkeypatch.setattr(worker_app, "KnowledgeBaseService", _raise_component_bootstrap_failure)

    with pytest.raises(RuntimeError, match="component bootstrap failed"):
        asyncio.run(worker_app.run_worker(asyncio.Event()))

    assert knowledge.closed is True
    assert model.closed is True
    assert database.calls == ["start", "stop"]
