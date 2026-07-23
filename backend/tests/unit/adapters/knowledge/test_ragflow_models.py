from __future__ import annotations

import json
import stat
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import common_agent.adapters.knowledge.ragflow_models as ragflow_models
from common_agent.adapters.knowledge.ragflow_models import (
    BAILIAN_EMBEDDING_ID,
    BAILIAN_EMBEDDING_INSTANCE,
    BAILIAN_FACTORY,
    BAILIAN_RERANK_ID,
    BAILIAN_RERANK_INSTANCE,
    RagFlowBailianIndexMigrator,
    RagFlowBailianMigrationPlan,
    RagFlowBailianMigrationResult,
    RagFlowModelConfigurationError,
    RagFlowModelConfigurator,
    RagFlowModelStatus,
    main,
)
from common_agent.bootstrap.settings import ConfigurationError, ModelSettings, RagFlowSettings


def test_configurator_registers_bailian_models_and_sets_tenant_defaults() -> None:
    requests: list[httpx.Request] = []
    providers: list[dict[str, object]] = []
    instances: list[dict[str, object]] = []
    defaults: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/users":
            return httpx.Response(200, json={"code": 0, "data": True})
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(
                200,
                headers={"Authorization": "ragflow-session"},
                json={"code": 0, "data": True},
            )
        assert request.headers["Authorization"] == "ragflow-session"
        if request.url.path == "/api/v1/providers" and request.method == "GET":
            return httpx.Response(200, json={"code": 0, "data": list(providers)})
        if request.url.path == "/api/v1/providers" and request.method == "PUT":
            providers.append({"name": BAILIAN_FACTORY})
            return httpx.Response(200, json={"code": 0, "message": "success"})
        if (
            request.url.path == f"/api/v1/providers/{BAILIAN_FACTORY}/instances"
            and request.method == "GET"
        ):
            return httpx.Response(200, json={"code": 0, "data": list(instances)})
        if (
            request.url.path == f"/api/v1/providers/{BAILIAN_FACTORY}/instances"
            and request.method == "POST"
        ):
            payload = json.loads(request.content)
            instances.append({"instance_name": payload["instance_name"], "status": "active"})
            return httpx.Response(200, json={"code": 0, "message": "success"})
        if request.url.path == "/api/v1/models":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [
                        {
                            "name": "text-embedding-v4",
                            "model_type": ["embedding"],
                            "provider_name": BAILIAN_FACTORY,
                            "instance_name": BAILIAN_EMBEDDING_INSTANCE,
                        },
                        {
                            "name": "qwen3-rerank",
                            "model_type": ["rerank"],
                            "provider_name": BAILIAN_FACTORY,
                            "instance_name": BAILIAN_RERANK_INSTANCE,
                        },
                    ],
                },
            )
        if request.url.path == "/api/v1/models/default" and request.method == "GET":
            return httpx.Response(200, json={"code": 0, "data": {"models": list(defaults)}})
        if request.url.path == "/api/v1/models/default" and request.method == "PATCH":
            defaults.append(json.loads(request.content))
            return httpx.Response(200, json={"code": 0, "message": "success"})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
    ) as client:
        status = RagFlowModelConfigurator(client=client).apply(
            api_key="fixture-bailian-secret",
            provider_base_url=(
                "https://ws-fixture.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"
            ),
        )

    provider_payloads = [
        json.loads(request.content)
        for request in requests
        if request.url.path == "/api/v1/providers" and request.method == "PUT"
    ]
    assert provider_payloads == [{"provider_name": BAILIAN_FACTORY}]
    instance_payloads = [
        json.loads(request.content)
        for request in requests
        if request.url.path == f"/api/v1/providers/{BAILIAN_FACTORY}/instances"
        and request.method == "POST"
    ]
    assert instance_payloads == [
        {
            "instance_name": BAILIAN_EMBEDDING_INSTANCE,
            "api_key": "fixture-bailian-secret",
            "base_url": ("https://ws-fixture.cn-beijing.maas.aliyuncs.com/compatible-mode/v1"),
            "region": "",
            "model_info": [
                {
                    "model_name": "text-embedding-v4",
                    "model_type": ["embedding"],
                    "max_tokens": 8192,
                }
            ],
        },
        {
            "instance_name": BAILIAN_RERANK_INSTANCE,
            "api_key": "fixture-bailian-secret",
            "base_url": (
                "https://ws-fixture.cn-beijing.maas.aliyuncs.com/compatible-api/v1/reranks"
            ),
            "region": "",
            "model_info": [
                {
                    "model_name": "qwen3-rerank",
                    "model_type": ["rerank"],
                    "max_tokens": 4000,
                }
            ],
        },
    ]
    assert defaults == [
        {
            "model_provider": BAILIAN_FACTORY,
            "model_instance": BAILIAN_EMBEDDING_INSTANCE,
            "model_name": "text-embedding-v4",
            "model_type": "embedding",
        },
        {
            "model_provider": BAILIAN_FACTORY,
            "model_instance": BAILIAN_RERANK_INSTANCE,
            "model_name": "qwen3-rerank",
            "model_type": "rerank",
        },
    ]
    assert BAILIAN_EMBEDDING_ID == (
        "text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible"
    )
    assert BAILIAN_RERANK_ID == ("qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible")
    assert status.embedding_ready is True
    assert status.rerank_ready is True
    assert status.defaults_ready is True
    assert "fixture-bailian-secret" not in repr(status)


def test_configurator_accepts_idempotent_existing_local_account() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/users":
            return httpx.Response(
                200,
                json={"code": 102, "message": "User already registered!"},
            )
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(
                200,
                headers={"Authorization": "ragflow-session"},
                json={"code": 0, "data": True},
            )
        if request.url.path == "/api/v1/models":
            return httpx.Response(200, json={"code": 0, "data": []})
        if request.url.path == "/api/v1/models/default":
            return httpx.Response(200, json={"code": 0, "data": {"models": []}})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
    ) as client:
        status = RagFlowModelConfigurator(client=client).status()

    assert status.embedding_ready is False
    assert status.rerank_ready is False
    assert status.defaults_ready is False


def test_configurator_sanitizes_upstream_model_errors() -> None:
    secret = "fixture-bailian-secret"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/users":
            return httpx.Response(200, json={"code": 0, "data": True})
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(
                200,
                headers={"Authorization": "ragflow-session"},
                json={"code": 0, "data": True},
            )
        if request.url.path == "/api/v1/providers" and request.method == "GET":
            return httpx.Response(200, json={"code": 0, "data": []})
        if request.url.path == "/api/v1/providers" and request.method == "PUT":
            return httpx.Response(200, json={"code": 0, "message": "success"})
        if (
            request.url.path == "/api/v1/providers/OpenAI-API-Compatible/instances"
            and request.method == "GET"
        ):
            return httpx.Response(200, json={"code": 0, "data": []})
        if (
            request.url.path == "/api/v1/providers/OpenAI-API-Compatible/instances"
            and request.method == "POST"
        ):
            return httpx.Response(
                200,
                json={"code": 100, "message": f"provider rejected {secret}"},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    with (
        httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
        ) as client,
        pytest.raises(RagFlowModelConfigurationError) as captured,
    ):
        RagFlowModelConfigurator(client=client).apply(
            api_key=secret,
            provider_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )

    assert captured.value.code == "ragflow_model_configuration_failed"
    assert captured.value.stage == "create_embedding_instance"
    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)


def test_configurator_reuses_valid_api_token_without_web_login(tmp_path: Path) -> None:
    token_file = tmp_path / "runtime" / "ragflow-api-token"
    token_file.parent.mkdir()
    token_file.write_text("ragflow-existing-token\n", encoding="utf-8")
    token_file.chmod(0o600)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/datasets"
        assert request.headers["Authorization"] == "Bearer ragflow-existing-token"
        return httpx.Response(200, json={"code": 0, "data": []})

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
    ) as client:
        configurator = RagFlowModelConfigurator(client=client)
        configurator.ensure_api_token(token_file=token_file)
        configurator.check_api_token(token_file=token_file)

    assert token_file.read_text(encoding="utf-8") == "ragflow-existing-token\n"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_configurator_replaces_stale_file_with_api_token_from_public_endpoint(
    tmp_path: Path,
) -> None:
    token_file = tmp_path / "runtime" / "ragflow-api-token"
    token_file.parent.mkdir()
    token_file.write_text("ragflow-stale-token\n", encoding="utf-8")
    token_file.chmod(0o644)
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/datasets":
            authorization = request.headers["Authorization"]
            code = 0 if authorization == "Bearer ragflow-current-token" else 401
            return httpx.Response(200, json={"code": code, "data": []})
        if request.url.path == "/api/v1/users":
            return httpx.Response(200, json={"code": 0, "data": True})
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(
                200,
                headers={"Authorization": "ragflow-session"},
                json={"code": 0, "data": True},
            )
        if request.url.path == "/api/v1/system/tokens":
            assert request.headers["Authorization"] == "ragflow-session"
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [{"token": "ragflow-current-token"}],
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
    ) as client:
        RagFlowModelConfigurator(client=client).ensure_api_token(token_file=token_file)

    assert token_file.read_text(encoding="utf-8") == "ragflow-current-token\n"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600
    assert all("ragflow-current-token" not in str(request.url) for request in requests)


def test_configurator_creates_api_token_when_account_has_none(tmp_path: Path) -> None:
    token_file = tmp_path / "runtime" / "ragflow-api-token"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/users":
            return httpx.Response(200, json={"code": 0, "data": True})
        if request.url.path == "/api/v1/auth/login":
            return httpx.Response(
                200,
                headers={"Authorization": "ragflow-session"},
                json={"code": 0, "data": True},
            )
        if request.url.path == "/api/v1/system/tokens" and request.method == "GET":
            return httpx.Response(200, json={"code": 0, "data": []})
        if request.url.path == "/api/v1/system/tokens" and request.method == "POST":
            return httpx.Response(
                200,
                json={"code": 0, "data": {"token": "ragflow-new-token"}},
            )
        if request.url.path == "/api/v1/datasets":
            assert request.headers["Authorization"] == "Bearer ragflow-new-token"
            return httpx.Response(200, json={"code": 0, "data": []})
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
    ) as client:
        RagFlowModelConfigurator(client=client).ensure_api_token(token_file=token_file)

    assert token_file.read_text(encoding="utf-8") == "ragflow-new-token\n"
    assert stat.S_IMODE(token_file.stat().st_mode) == 0o600


def test_bailian_migrator_reindexes_existing_documents_through_public_api() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["Authorization"] == "Bearer ragflow-api-key"
        if request.url.path == "/api/v1/datasets" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [
                        {
                            "id": "kb-1",
                            "embedding_model": "BAAI/bge-m3@HuggingFace",
                        }
                    ],
                },
            )
        if request.url.path == "/api/v1/datasets/kb-1/documents" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "total": 2,
                        "docs": [
                            {"id": "doc-1", "run": "DONE"},
                            {"id": "doc-2", "run": "DONE"},
                        ],
                    },
                },
            )
        if request.url.path == "/api/v1/datasets/kb-1" and request.method == "PUT":
            assert json.loads(request.content) == {"embedding_model": BAILIAN_EMBEDDING_ID}
            return httpx.Response(200, json={"code": 0, "data": {"id": "kb-1"}})
        if request.url.path == "/api/v1/datasets/kb-1/documents/parse" and request.method == "POST":
            assert json.loads(request.content) == {"document_ids": ["doc-1", "doc-2"]}
            return httpx.Response(
                200,
                json={"code": 0, "data": {"success_count": 2}},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url.path}")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
    ) as client:
        migrator = RagFlowBailianIndexMigrator(
            client=client,
            authorization="Bearer ragflow-api-key",
            poll_interval_seconds=0,
        )
        plan = migrator.plan()
        result = migrator.migrate()

    assert plan.dataset_count == 1
    assert plan.document_count == 2
    assert plan.datasets_requiring_model_update == 1
    assert result.dataset_count == 1
    assert result.document_count == 2
    assert result.datasets_updated == 1
    assert sum(request.method == "PUT" for request in requests) == 1
    assert sum(request.url.path.endswith("/documents/parse") for request in requests) == 1


def test_bailian_migrator_preflight_rejects_busy_documents_before_mutation() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/v1/datasets":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [{"id": "kb-1", "embedding_model": BAILIAN_EMBEDDING_ID}],
                },
            )
        if request.url.path == "/api/v1/datasets/kb-1/documents":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "total": 1,
                        "docs": [{"id": "doc-1", "run": "RUNNING"}],
                    },
                },
            )
        raise AssertionError("preflight failure must not mutate RAGFlow")

    with (
        httpx.Client(
            transport=httpx.MockTransport(handler), base_url="http://127.0.0.1:19380"
        ) as client,
        pytest.raises(RagFlowModelConfigurationError) as captured,
    ):
        RagFlowBailianIndexMigrator(
            client=client,
            authorization="Bearer ragflow-api-key",
            poll_interval_seconds=0,
        ).migrate()

    assert captured.value.stage == "migration_documents_busy"
    assert all(request.method == "GET" for request in requests)


def test_cli_emits_workspace_native_api_url_without_key(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BAILIAN_API_KEY", "fixture-bailian-secret")
    monkeypatch.setenv(
        "BAILIAN_BASE_URL",
        "https://ws-fixture.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setenv("BAILIAN_MODEL", "qwen-plus")

    assert main(["native-base-url"]) == 0
    captured = capsys.readouterr()

    assert captured.out.strip() == ("https://ws-fixture.cn-beijing.maas.aliyuncs.com/api/v1")
    assert captured.err == ""
    assert "fixture-bailian-secret" not in captured.out


def test_cli_diagnoses_bailian_scope_and_limits_without_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("BAILIAN_API_KEY", "fixture-bailian-secret")
    monkeypatch.setenv(
        "BAILIAN_BASE_URL",
        "https://ws-fixture.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
    )
    monkeypatch.setenv("BAILIAN_MODEL", "qwen-plus")
    monkeypatch.setenv("BAILIAN_TIMEOUT_SECONDS", "45")
    monkeypatch.setenv("BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS", "15")
    monkeypatch.setenv("BAILIAN_MAX_RETRIES", "1")

    assert main(["diagnose"]) == 0
    captured = capsys.readouterr()

    assert "provider=bailian" in captured.out
    assert "BAILIAN_API_KEY=present" in captured.out
    assert "endpoint=business-space" in captured.out
    assert "region=cn-beijing" in captured.out
    assert "chat=qwen-plus" in captured.out
    assert (
        "embedding=text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible" in captured.out
    )
    assert "rerank=qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible" in captured.out
    assert "timeout=45s" in captured.out
    assert "stream_timeout=15s" in captured.out
    assert "retries=1" in captured.out
    assert "fixture-bailian-secret" not in captured.out
    assert "ws-fixture" not in captured.out


def test_migration_cli_requires_explicit_cost_confirmation(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("RAGFLOW_CONFIRM_BAILIAN_REINDEX", raising=False)

    assert main(["migrate"]) == 1
    captured = capsys.readouterr()

    assert captured.out == ""
    assert captured.err.strip() == ("ragflow_model_configuration_failed:migration_confirmation")


def test_status_cli_ignores_system_proxy_for_loopback_ragflow(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client_options: dict[str, object] = {}

    class ClientProbe:
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)

        def __enter__(self) -> ClientProbe:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", ClientProbe)
    monkeypatch.setattr(
        RagFlowModelConfigurator,
        "status",
        lambda _self: ragflow_models.RagFlowModelStatus(True, True, True),
    )
    monkeypatch.setenv("RAGFLOW_BASE_URL", "http://127.0.0.1:19380")
    monkeypatch.setenv("RAGFLOW_EXPECTED_VERSION", "v0.26.4")

    assert main(["status"]) == 0
    assert capsys.readouterr().err == ""
    assert client_options["trust_env"] is False


@pytest.mark.parametrize(
    ("authorization", "poll_interval", "timeout"),
    [("", 0, 1), ("token", -1, 1), ("token", 0, 0)],
)
def test_migrator_rejects_invalid_runtime_limits(
    authorization: str,
    poll_interval: float,
    timeout: float,
) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client,
        pytest.raises(RagFlowModelConfigurationError) as captured,
    ):
        RagFlowBailianIndexMigrator(
            client=client,
            authorization=authorization,
            poll_interval_seconds=poll_interval,
            timeout_seconds=timeout,
        )

    assert captured.value.stage == "migration_input"


@pytest.mark.parametrize(
    "datasets",
    [None, [None], [{"id": ""}], [{"id": "kb", "embedding_model": 1}]],
)
def test_migrator_rejects_malformed_dataset_inventory(
    monkeypatch: pytest.MonkeyPatch,
    datasets: object,
) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        migrator = RagFlowBailianIndexMigrator(client=client, authorization="Bearer token")
        monkeypatch.setattr(migrator, "_request", lambda *_args, **_kwargs: datasets)
        with pytest.raises(RagFlowModelConfigurationError) as captured:
            migrator.plan()

    assert captured.value.stage == "migration_list_datasets"


def test_migrator_filters_requested_datasets_and_rejects_unknown_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        migrator = RagFlowBailianIndexMigrator(client=client, authorization="Bearer token")
        monkeypatch.setattr(
            migrator,
            "_request",
            lambda *_args, **_kwargs: [{"id": "other", "embedding_model": "model"}],
        )
        with pytest.raises(RagFlowModelConfigurationError) as captured:
            migrator.plan(dataset_ids=(" wanted ", ""))

    assert captured.value.stage == "migration_dataset_not_found"


@pytest.mark.parametrize(
    "documents",
    [None, {"docs": "invalid"}, {"docs": [None]}, {"docs": [{"id": "", "run": 1}]}],
)
def test_migrator_rejects_malformed_document_inventory(
    monkeypatch: pytest.MonkeyPatch,
    documents: object,
) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        migrator = RagFlowBailianIndexMigrator(client=client, authorization="Bearer token")
        monkeypatch.setattr(migrator, "_request", lambda *_args, **_kwargs: documents)
        with pytest.raises(RagFlowModelConfigurationError) as captured:
            migrator._list_documents("kb")

    assert captured.value.stage == "migration_list_documents"


@pytest.mark.parametrize(
    ("documents", "stage"),
    [
        ((), "migration_document_missing"),
        ((ragflow_models._MigrationDocument("doc", "FAIL"),), "migration_reindex_failed"),
    ],
)
def test_migrator_wait_rejects_missing_or_failed_documents(
    monkeypatch: pytest.MonkeyPatch,
    documents: tuple[ragflow_models._MigrationDocument, ...],
    stage: str,
) -> None:
    expected = ragflow_models._MigrationDataset(
        "kb",
        BAILIAN_EMBEDDING_ID,
        (ragflow_models._MigrationDocument("doc", "DONE"),),
    )
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        migrator = RagFlowBailianIndexMigrator(client=client, authorization="Bearer token")
        monkeypatch.setattr(migrator, "_list_documents", lambda _dataset_id: documents)
        with pytest.raises(RagFlowModelConfigurationError) as captured:
            migrator._wait_for_documents(expected)

    assert captured.value.stage == stage


def test_migrator_wait_times_out_without_leaking_upstream_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = ragflow_models._MigrationDocument("doc", "RUNNING")
    dataset = ragflow_models._MigrationDataset("kb", BAILIAN_EMBEDDING_ID, (document,))
    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(ragflow_models, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(ragflow_models, "sleep", lambda _seconds: None)
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        migrator = RagFlowBailianIndexMigrator(
            client=client,
            authorization="Bearer token",
            timeout_seconds=1,
        )
        monkeypatch.setattr(migrator, "_list_documents", lambda _dataset_id: (document,))
        with pytest.raises(RagFlowModelConfigurationError) as captured:
            migrator._wait_for_documents(dataset)

    assert captured.value.stage == "migration_reindex_timeout"


@pytest.mark.parametrize(
    "response",
    [httpx.Response(503), httpx.Response(200, json={"code": 1})],
)
def test_migrator_sanitizes_transport_and_protocol_failures(response: httpx.Response) -> None:
    with (
        httpx.Client(transport=httpx.MockTransport(lambda _: response)) as client,
        pytest.raises(RagFlowModelConfigurationError) as captured,
    ):
        RagFlowBailianIndexMigrator(
            client=client,
            authorization="Bearer token",
        ).plan()

    assert captured.value.stage == "migration_list_datasets"


def test_configurator_rejects_invalid_provider_and_status_shapes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(200))) as client:
        configurator = RagFlowModelConfigurator(client=client)
        monkeypatch.setattr(configurator, "_authenticate", lambda: None)
        monkeypatch.setattr(configurator, "_request_data", lambda *_args, **_kwargs: {})
        with pytest.raises(RagFlowModelConfigurationError) as providers:
            configurator.apply(
                api_key="key",
                provider_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            )
        with pytest.raises(RagFlowModelConfigurationError) as models:
            configurator.status()

    assert providers.value.stage == "list_providers"
    assert models.value.stage == "status_models"


def test_token_file_rejects_symlinks_public_mode_and_invalid_tokens(
    tmp_path: Path,
) -> None:
    target = tmp_path / "target"
    target.write_text("ragflow-token\n", encoding="utf-8")
    link = tmp_path / "token"
    link.symlink_to(target)
    with pytest.raises(RagFlowModelConfigurationError) as symlink:
        ragflow_models._read_token_file(link)
    with pytest.raises(RagFlowModelConfigurationError) as write_symlink:
        ragflow_models._write_token_file(link, "ragflow-token")
    with pytest.raises(RagFlowModelConfigurationError) as invalid:
        ragflow_models._write_token_file(tmp_path / "invalid", "not-a-token")

    target.chmod(0o644)
    with pytest.raises(RagFlowModelConfigurationError) as mode:
        ragflow_models._read_token_file(target, require_private_mode=True)

    assert symlink.value.stage == "token_file"
    assert write_symlink.value.stage == "token_file"
    assert invalid.value.stage == "token_file"
    assert mode.value.stage == "token_file_mode"


def test_token_file_write_cleans_temporary_file_on_replace_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    token_file = tmp_path / "runtime" / "token"
    monkeypatch.setattr(
        "common_agent.adapters.knowledge.ragflow_models.os.replace",
        lambda *_args: (_ for _ in ()).throw(OSError("replace failed")),
    )

    with pytest.raises(RagFlowModelConfigurationError) as captured:
        ragflow_models._write_token_file(token_file, "ragflow-token")

    assert captured.value.stage == "token_file"
    assert list(token_file.parent.iterdir()) == []


@pytest.mark.parametrize(
    "value",
    [
        "http://dashscope.aliyuncs.com/compatible-mode/v1",
        "https://attacker.example/compatible-mode/v1",
        "https://user@dashscope.aliyuncs.com/compatible-mode/v1",
        "https://dashscope.aliyuncs.com/compatible-mode/v1?key=value",
    ],
)
def test_bailian_url_normalization_rejects_non_official_endpoints(value: str) -> None:
    assert ragflow_models._ragflow_provider_base_url(value) is None
    assert ragflow_models._ragflow_compatible_base_urls(value) is None


def test_bailian_helpers_cover_supported_regions_and_model_shapes() -> None:
    assert ragflow_models._bailian_endpoint_scope(
        "https://x.ap-southeast-1.maas.aliyuncs.com/compatible-mode/v1"
    ) == ("business-space", "ap-southeast-1")
    assert ragflow_models._bailian_endpoint_scope(
        "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
    ) == ("public", "international")
    assert ragflow_models._bailian_endpoint_scope(
        "https://dashscope.aliyuncs.com/compatible-mode/v1"
    ) == ("public", "cn")
    assert ragflow_models._model_types("embedding") == ("embedding",)
    assert ragflow_models._model_types(["embedding", 1]) == ("embedding",)
    assert ragflow_models._model_types(None) == ()
    assert ragflow_models._is_busy("1") is True
    assert ragflow_models._batches(("1", "2", "3"), size=2) == (("1", "2"), ("3",))


def test_cli_reports_usage_and_configuration_errors_without_secrets(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["unknown"]) == 2
    usage = capsys.readouterr()
    assert "用法" in usage.err

    def invalid_settings() -> object:
        raise ConfigurationError("invalid")

    monkeypatch.setattr(ModelSettings, "from_env", invalid_settings)
    assert main(["native-base-url"]) == 1
    failure = capsys.readouterr()
    assert failure.err.strip() == "ragflow_model_configuration_failed:input"


def test_cli_token_actions_require_and_dispatch_private_file(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ClientProbe:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> ClientProbe:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    checked: list[Path] = []
    monkeypatch.setattr(httpx, "Client", ClientProbe)
    monkeypatch.setattr(
        RagFlowSettings,
        "from_env",
        lambda: SimpleNamespace(base_url="http://127.0.0.1", timeout_seconds=1),
    )
    monkeypatch.setattr(
        RagFlowModelConfigurator,
        "check_api_token",
        lambda _self, *, token_file: checked.append(token_file),
    )
    monkeypatch.delenv("RAGFLOW_TOKEN_FILE", raising=False)
    assert main(["check-token"]) == 1
    assert "token_file" in capsys.readouterr().err

    token_file = tmp_path / "token"
    monkeypatch.setenv("RAGFLOW_TOKEN_FILE", str(token_file))
    assert main(["check-token"]) == 0
    assert checked == [token_file]
    assert "ready" in capsys.readouterr().out


def test_cli_applies_models_and_executes_confirmed_migration_actions(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class ClientProbe:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> ClientProbe:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    ready = RagFlowModelStatus(True, True, True)
    observed: list[tuple[str, tuple[str, ...]]] = []

    def plan(
        _self: RagFlowBailianIndexMigrator,
        *,
        dataset_ids: tuple[str, ...],
    ) -> RagFlowBailianMigrationPlan:
        observed.append(("plan", dataset_ids))
        return RagFlowBailianMigrationPlan(2, 3, 1, 0)

    def migrate(
        _self: RagFlowBailianIndexMigrator,
        *,
        dataset_ids: tuple[str, ...],
    ) -> RagFlowBailianMigrationResult:
        observed.append(("migrate", dataset_ids))
        return RagFlowBailianMigrationResult(2, 3, 1)

    monkeypatch.setattr(httpx, "Client", ClientProbe)
    monkeypatch.setattr(
        RagFlowSettings,
        "from_env",
        lambda: SimpleNamespace(base_url="http://127.0.0.1", timeout_seconds=1),
    )
    monkeypatch.setattr(
        ModelSettings,
        "from_env",
        lambda: SimpleNamespace(
            api_key=SimpleNamespace(get_secret_value=lambda: "secret"),
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        ),
    )
    monkeypatch.setattr(RagFlowModelConfigurator, "apply", lambda *_args, **_kwargs: ready)
    monkeypatch.setattr(RagFlowModelConfigurator, "status", lambda _self: ready)
    monkeypatch.setattr(
        RagFlowModelConfigurator,
        "authorization",
        lambda _self: "Bearer token",
    )
    monkeypatch.setattr(
        RagFlowBailianIndexMigrator,
        "plan",
        plan,
    )
    monkeypatch.setattr(
        RagFlowBailianIndexMigrator,
        "migrate",
        migrate,
    )
    monkeypatch.setenv("RAGFLOW_BAILIAN_MIGRATION_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("RAGFLOW_BAILIAN_MIGRATION_DATASET_IDS", " kb-1, ,kb-2 ")

    assert main(["apply"]) == 0
    assert "embedding=ready" in capsys.readouterr().out
    assert main(["plan-migration"]) == 0
    assert "datasets=2" in capsys.readouterr().out
    monkeypatch.setenv("RAGFLOW_CONFIRM_BAILIAN_REINDEX", "yes")
    assert main(["migrate"]) == 0
    assert "model_updates=1" in capsys.readouterr().out
    assert observed == [
        ("plan", ("kb-1", "kb-2")),
        ("migrate", ("kb-1", "kb-2")),
    ]


@pytest.mark.parametrize("timeout", ["invalid", "0", "86401"])
def test_migration_cli_rejects_invalid_timeout_before_reindex(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    timeout: str,
) -> None:
    class ClientProbe:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> ClientProbe:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(httpx, "Client", ClientProbe)
    monkeypatch.setattr(
        RagFlowSettings,
        "from_env",
        lambda: SimpleNamespace(base_url="http://127.0.0.1", timeout_seconds=1),
    )
    monkeypatch.setattr(
        RagFlowModelConfigurator,
        "status",
        lambda _self: RagFlowModelStatus(True, True, True),
    )
    monkeypatch.setenv("RAGFLOW_BAILIAN_MIGRATION_TIMEOUT_SECONDS", timeout)

    assert main(["plan-migration"]) == 1
    assert "migration_input" in capsys.readouterr().err
