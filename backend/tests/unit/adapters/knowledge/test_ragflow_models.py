from __future__ import annotations

import json

import httpx
import pytest

import common_agent.adapters.knowledge.ragflow_models as ragflow_models
from common_agent.adapters.knowledge.ragflow_models import (
    BAILIAN_EMBEDDING_ID,
    BAILIAN_RERANK_ID,
    RagFlowBailianIndexMigrator,
    RagFlowModelConfigurationError,
    RagFlowModelConfigurator,
    main,
)


def test_configurator_registers_bailian_models_and_sets_tenant_defaults() -> None:
    requests: list[httpx.Request] = []
    tenant = {
        "tenant_id": "tenant-1",
        "llm_id": "",
        "embd_id": "",
        "asr_id": "",
        "img2txt_id": "",
        "rerank_id": "",
    }

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
        if request.url.path == "/v1/llm/add_llm":
            return httpx.Response(200, json={"code": 0, "data": True})
        if request.url.path == "/api/v1/users/me/models" and request.method == "GET":
            return httpx.Response(200, json={"code": 0, "data": dict(tenant)})
        if request.url.path == "/api/v1/users/me/models" and request.method == "PATCH":
            tenant.update(json.loads(request.content))
            return httpx.Response(200, json={"code": 0, "data": True})
        if request.url.path == "/v1/llm/my_llms":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "Tongyi-Qianwen": {
                            "llm": [
                                {"name": "text-embedding-v4", "type": "embedding"},
                                {"name": "qwen3-rerank", "type": "rerank"},
                            ]
                        }
                    },
                },
            )
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

    model_payloads = [
        json.loads(request.content) for request in requests if request.url.path == "/v1/llm/add_llm"
    ]
    assert model_payloads == [
        {
            "llm_factory": "Tongyi-Qianwen",
            "llm_name": "text-embedding-v4",
            "model_type": "embedding",
            "api_base": "https://ws-fixture.cn-beijing.maas.aliyuncs.com/api/v1",
            "api_key": "fixture-bailian-secret",
            "max_tokens": 8192,
        },
        {
            "llm_factory": "Tongyi-Qianwen",
            "llm_name": "qwen3-rerank",
            "model_type": "rerank",
            "api_base": "https://ws-fixture.cn-beijing.maas.aliyuncs.com/api/v1",
            "api_key": "fixture-bailian-secret",
            "max_tokens": 4000,
        },
    ]
    assert tenant["embd_id"] == BAILIAN_EMBEDDING_ID
    assert tenant["rerank_id"] == BAILIAN_RERANK_ID
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
        if request.url.path == "/v1/llm/my_llms":
            return httpx.Response(200, json={"code": 0, "data": {}})
        if request.url.path == "/api/v1/users/me/models":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {"embd_id": "", "rerank_id": ""},
                },
            )
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
        if request.url.path == "/v1/llm/add_llm":
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
    assert captured.value.stage == "register_embedding"
    assert secret not in str(captured.value)
    assert secret not in repr(captured.value)


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
    monkeypatch.setenv("RAGFLOW_EXPECTED_VERSION", "v0.25.6")

    assert main(["status"]) == 0
    assert capsys.readouterr().err == ""
    assert client_options["trust_env"] is False
