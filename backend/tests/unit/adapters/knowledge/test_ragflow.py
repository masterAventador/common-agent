from __future__ import annotations

import asyncio
import json
from collections.abc import Coroutine
from typing import Any

import httpx
import pytest

from common_agent.adapters.knowledge.ragflow import RagFlowKnowledgeService
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeRetrievalRequest,
    KnowledgeServiceAvailability,
)
from common_agent.knowledge.base import (
    KnowledgeBaseNotFound,
    KnowledgeConfigurationMissing,
    KnowledgeDocumentUploadFailed,
    KnowledgeDocumentUploadResultUnknown,
    KnowledgeProviderResponseInvalid,
    KnowledgeRequestRejected,
    KnowledgeService,
    KnowledgeServiceUnavailable,
)
from common_agent.observability import bind_observation_context


def _run[Result](awaitable: Coroutine[Any, Any, Result]) -> Result:
    return asyncio.run(awaitable)


def test_owned_ragflow_client_ignores_system_proxy(monkeypatch: pytest.MonkeyPatch) -> None:
    client_options: dict[str, object] = {}

    class ClientProbe:
        def __init__(self, **kwargs: object) -> None:
            client_options.update(kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", ClientProbe)

    RagFlowKnowledgeService(
        base_url="http://127.0.0.1:19380",
        api_key="test-key",
        expected_version="v0.25.6",
    )

    assert client_options["trust_env"] is False


def test_ragflow_requests_forward_trace_context_without_exposing_credentials() -> None:
    captured: httpx.Request | None = None

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal captured
        captured = request
        return httpx.Response(200, json={"code": 0, "data": "v0.25.6"})

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="private-ragflow-key",
                expected_version="v0.25.6",
                client=client,
            )
            with bind_observation_context(
                request_id="request-1",
                traceparent="00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01",
            ):
                await service.status()

    _run(scenario())
    assert captured is not None
    assert captured.headers["traceparent"].startswith("00-4bf92f3577b34da6a3ce929d0e0e4736-")
    assert captured.headers["x-request-id"] == "request-1"
    assert captured.headers["authorization"] == "Bearer private-ragflow-key"


def test_ragflow_adapter_uses_only_the_public_v0_25_6_api_surface() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        if path == "/api/v1/system/version":
            return httpx.Response(200, json={"code": 0, "data": "v0.25.6"})
        if path == "/api/v1/datasets" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [
                        {
                            "id": "kb-1",
                            "name": "制度库",
                            "description": "内部制度",
                            "document_count": 1,
                        }
                    ],
                },
            )
        if path == "/api/v1/datasets/kb-1" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "id": "kb-1",
                        "name": "制度库",
                        "description": "内部制度",
                        "document_count": 1,
                    },
                },
            )
        if path == "/api/v1/datasets" and request.method == "POST":
            assert json.loads(request.content) == {
                "name": "制度库",
                "description": "内部制度",
                "permission": "me",
                "chunk_method": "naive",
                "embedding_model": "text-embedding-v4@Tongyi-Qianwen",
            }
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "id": "kb-1",
                        "name": "制度库",
                        "description": "内部制度",
                        "document_count": 0,
                    },
                },
            )
        if path == "/api/v1/datasets/kb-1/documents" and request.method == "POST":
            assert b'filename="policy.md"' in request.content
            assert b"unsafe" not in request.content
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [
                        {
                            "id": "doc-1",
                            "dataset_id": "kb-1",
                            "name": "policy.md",
                            "run": "UNSTART",
                            "size": 12,
                        }
                    ],
                },
            )
        if path == "/api/v1/datasets/kb-1/chunks":
            assert json.loads(request.content) == {"document_ids": ["doc-1"]}
            return httpx.Response(200, json={"code": 0, "data": True})
        if path == "/api/v1/datasets/kb-1/documents" and request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "total": 1,
                        "docs": [
                            {
                                "id": "doc-1",
                                "dataset_id": "kb-1",
                                "name": "policy.md",
                                "run": "DONE",
                                "size": 12,
                            }
                        ],
                    },
                },
            )
        if path == "/api/v1/retrieval":
            assert json.loads(request.content) == {
                "question": "年假有几天",
                "dataset_ids": ["kb-1"],
                "page": 1,
                "page_size": 5,
                "top_k": 5,
                "similarity_threshold": 0.2,
                "vector_similarity_weight": 0.3,
                "rerank_id": "qwen3-rerank@Tongyi-Qianwen",
                "include_metadata": True,
            }
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": {
                        "total": 1,
                        "chunks": [
                            {
                                "id": "chunk-1",
                                "document_id": "doc-1",
                                "document_keyword": "policy.md",
                                "content": "年假为十天",
                                "similarity": 0.91,
                            }
                        ],
                    },
                },
            )
        raise AssertionError(f"unexpected request: {request.method} {path}")

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            contract: KnowledgeService = service
            status = await contract.status()
            listed = await contract.list_knowledge_bases()
            detailed = await contract.get_knowledge_base("kb-1")
            created = await contract.create_knowledge_base(
                CreateKnowledgeBaseRequest(name="制度库", description="内部制度")
            )
            uploaded = await contract.upload_document(
                created.id,
                DocumentUpload(
                    file_name="unsafe\\folder/policy.md",
                    content_type="text/markdown",
                    content=b"policy bytes",
                ),
            )
            documents = await contract.list_documents(created.id)
            retrieved = await contract.retrieve(
                KnowledgeRetrievalRequest(knowledge_base_id=created.id, query="年假有几天")
            )

        assert status.availability is KnowledgeServiceAvailability.AVAILABLE
        assert status.error_code is None
        assert listed[0].id == "kb-1"
        assert detailed.id == "kb-1"
        assert uploaded.parsing_status is DocumentParsingStatus.PARSING
        assert documents[0].parsing_status is DocumentParsingStatus.COMPLETED
        assert retrieved.chunks[0].document_name == "policy.md"
        assert retrieved.chunks[0].content == "年假为十天"

    _run(scenario())
    assert all(request.headers["authorization"] == "Bearer test-key" for request in requests)


def test_status_is_not_configured_without_calling_ragflow_when_key_is_missing() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(500)

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="",
                expected_version="v0.25.6",
                client=client,
            )
            status = await service.status()
            assert status.availability is KnowledgeServiceAvailability.NOT_CONFIGURED
            assert status.error_code == "configuration_missing"
            with pytest.raises(KnowledgeConfigurationMissing):
                await service.list_knowledge_bases()

    _run(scenario())
    assert called is False


def test_status_fails_closed_when_the_real_version_does_not_match() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"code": 0, "data": "v0.26.0"})
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            status = await service.status()

        assert status.availability is KnowledgeServiceAvailability.UNAVAILABLE
        assert status.version == "v0.26.0"
        assert status.error_code == "knowledge_service_version_mismatch"

    _run(scenario())


@pytest.mark.parametrize("run", ["0", "UNSTART"])
def test_unstarted_document_status_maps_to_uploaded(run: str) -> None:
    assert _document_status(run) is DocumentParsingStatus.UPLOADED


@pytest.mark.parametrize("run", ["1", "RUNNING"])
def test_running_document_status_maps_to_parsing(run: str) -> None:
    assert _document_status(run) is DocumentParsingStatus.PARSING


@pytest.mark.parametrize("run", ["3", "DONE"])
def test_done_document_status_maps_to_completed(run: str) -> None:
    assert _document_status(run) is DocumentParsingStatus.COMPLETED


@pytest.mark.parametrize("run", ["2", "CANCEL", "4", "FAIL"])
def test_cancelled_or_failed_document_status_maps_to_failed(run: str) -> None:
    assert _document_status(run) is DocumentParsingStatus.FAILED


def _document_status(run: str) -> DocumentParsingStatus:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "total": 1,
                    "docs": [
                        {
                            "id": "doc-1",
                            "dataset_id": "kb-1",
                            "name": "policy.md",
                            "run": run,
                            "size": 12,
                        }
                    ],
                },
            },
        )
    )

    async def scenario() -> DocumentParsingStatus:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            documents = await service.list_documents("kb-1")
        return documents[0].parsing_status

    return _run(scenario())


@pytest.mark.parametrize("status_code", [401, 403])
def test_auth_rejection_is_permanent_and_does_not_leak_provider_detail(status_code: int) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(status_code, text="secret provider response")
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="invalid",
                expected_version="v0.25.6",
                client=client,
            )
            with pytest.raises(KnowledgeRequestRejected) as captured:
                await service.list_knowledge_bases()
        assert "secret provider response" not in str(captured.value)

    _run(scenario())


@pytest.mark.parametrize(
    "handler",
    [
        lambda request: httpx.Response(503, text="private upstream error"),
        lambda request: (_ for _ in ()).throw(httpx.ConnectError("refused", request=request)),
        lambda request: (_ for _ in ()).throw(httpx.ReadTimeout("timed out", request=request)),
    ],
)
def test_transport_and_server_failures_are_retryable_unavailable(handler: object) -> None:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            with pytest.raises(KnowledgeServiceUnavailable) as captured:
                await service.create_knowledge_base(
                    CreateKnowledgeBaseRequest(name="失败库", description="")
                )
        assert captured.value.retryable is True
        assert "private upstream error" not in str(captured.value)

    _run(scenario())


@pytest.mark.parametrize(
    ("status_code", "body"),
    [
        (404, {"code": 102, "message": "secret missing dataset"}),
        (200, {"code": 102, "message": "secret missing dataset"}),
    ],
)
def test_missing_dataset_maps_to_stable_not_found(
    status_code: int, body: dict[str, object]
) -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(status_code, json=body))

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            with pytest.raises(KnowledgeBaseNotFound) as captured:
                await service.list_documents("missing-kb")
        assert "secret missing dataset" not in str(captured.value)

    _run(scenario())


@pytest.mark.parametrize(
    ("status_code", "provider_message"),
    [
        (400, "secret detail"),
        (200, "duplicated document name: policy.md"),
    ],
)
def test_known_or_duplicate_upload_rejection_is_not_reported_as_safe_to_retry(
    status_code: int,
    provider_message: str,
) -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            status_code,
            json={"code": 101, "message": provider_message},
        )
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            with pytest.raises(KnowledgeDocumentUploadFailed) as captured:
                await service.upload_document(
                    "kb-1",
                    DocumentUpload("policy.md", "text/markdown", b"policy"),
                )
        assert captured.value.retryable is False
        assert provider_message not in str(captured.value)

    _run(scenario())


@pytest.mark.parametrize("fail_after_upload", [False, True])
def test_upload_transport_or_parse_failure_reports_unknown_result(fail_after_upload: bool) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/documents"):
            if not fail_after_upload:
                raise httpx.ReadTimeout("timed out", request=request)
            return httpx.Response(
                200,
                json={
                    "code": 0,
                    "data": [
                        {
                            "id": "doc-1",
                            "dataset_id": "kb-1",
                            "name": "policy.md",
                            "run": "UNSTART",
                            "size": 6,
                        }
                    ],
                },
            )
        return httpx.Response(503, text="parse failed")

    async def scenario() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            with pytest.raises(KnowledgeDocumentUploadResultUnknown):
                await service.upload_document(
                    "kb-1",
                    DocumentUpload("policy.md", "text/markdown", b"policy"),
                )

    _run(scenario())


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json", headers={"content-type": "application/json"}),
        httpx.Response(200, json={"code": 0, "data": {"name": "missing-id"}}),
    ],
)
def test_malformed_provider_response_fails_closed(response: httpx.Response) -> None:
    transport = httpx.MockTransport(lambda request: response)

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            with pytest.raises(KnowledgeProviderResponseInvalid):
                await service.create_knowledge_base(
                    CreateKnowledgeBaseRequest(name="失败库", description="")
                )

    _run(scenario())


def test_empty_retrieval_is_a_successful_empty_result() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={"code": 0, "data": {"total": 0, "chunks": []}},
        )
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            result = await service.retrieve(
                KnowledgeRetrievalRequest(knowledge_base_id="kb-1", query="没有答案")
            )
        assert result.chunks == ()

    _run(scenario())


def test_retrieval_defensively_drops_low_relevance_chunks_and_caps_top_k() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "code": 0,
                "data": {
                    "total": 3,
                    "chunks": [
                        {
                            "id": "below-threshold",
                            "document_id": "doc-1",
                            "document_keyword": "低相关.md",
                            "content": "不应进入模型上下文",
                            "similarity": 0.19,
                        },
                        {
                            "id": "accepted",
                            "document_id": "doc-2",
                            "document_keyword": "可靠.md",
                            "content": "应进入模型上下文",
                            "similarity": 0.91,
                        },
                        {
                            "id": "over-limit",
                            "document_id": "doc-3",
                            "document_keyword": "额外.md",
                            "content": "超过 top_k 不应进入",
                            "similarity": 0.88,
                        },
                    ],
                },
            },
        )
    )

    async def scenario() -> None:
        async with httpx.AsyncClient(transport=transport, base_url="http://ragflow") as client:
            service = RagFlowKnowledgeService(
                base_url="http://ragflow",
                api_key="test-key",
                expected_version="v0.25.6",
                client=client,
            )
            result = await service.retrieve(
                KnowledgeRetrievalRequest(
                    knowledge_base_id="kb-1",
                    query="只要最相关的一条",
                    top_k=1,
                    similarity_threshold=0.2,
                )
            )
        assert [chunk.id for chunk in result.chunks] == ["accepted"]

    _run(scenario())
