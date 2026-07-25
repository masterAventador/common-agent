from __future__ import annotations

import asyncio
import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from typing import Any, cast

from sqlalchemy import delete

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    RagFlowKnowledgeBaseOwnershipRow,
    RagFlowTenantIdentityRow,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.http import (
    assert_error_response,
    authenticated_client,
    available_port,
    running_api,
)
from tests.support.settings import TEST_DATABASE_URL

_MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024


@dataclass(slots=True)
class _RagFlowProbe:
    version: str = "v0.26.4"
    create_payloads: list[dict[str, Any]] = field(default_factory=list)
    upload_bodies: list[bytes] = field(default_factory=list)
    parse_payloads: list[dict[str, Any]] = field(default_factory=list)
    document_run: str = "DONE"


class _LoopbackHTTPServer(ThreadingHTTPServer):
    def server_bind(self) -> None:
        TCPServer.server_bind(self)
        host, port = cast(tuple[str, int], self.server_address)
        self.server_name = str(host)
        self.server_port = int(port)


def _send_json(handler: BaseHTTPRequestHandler, status: int, payload: object) -> None:
    body = json.dumps(payload).encode()
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _read_body(handler: BaseHTTPRequestHandler) -> bytes:
    return handler.rfile.read(int(handler.headers.get("Content-Length", "0")))


def _handler(probe: _RagFlowProbe) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            del format, args

        def do_GET(self) -> None:
            if self.path == "/api/v1/system/version":
                _send_json(self, 200, {"code": 0, "data": probe.version})
                return
            if self.path == "/api/v1/users/me":
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": {
                            "id": "fake-ragflow-tenant",
                            "email": (
                                f"common-agent-{DEFAULT_TENANT_ID.hex}@local.test"
                                if self.headers.get("Authorization") == "tenant-session"
                                else "common-agent@local.test"
                            ),
                        },
                    },
                )
                return
            if self.path == "/api/v1/providers":
                _send_json(
                    self,
                    200,
                    {"code": 0, "data": [{"name": "OpenAI-API-Compatible"}]},
                )
                return
            if self.path == "/api/v1/providers/OpenAI-API-Compatible/instances":
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": [
                            {
                                "instance_name": "common-agent-embedding",
                                "status": "active",
                            },
                            {
                                "instance_name": "common-agent-rerank",
                                "status": "active",
                            },
                        ],
                    },
                )
                return
            if self.path == "/api/v1/models":
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": [
                            {
                                "name": "text-embedding-v4",
                                "instance_name": "common-agent-embedding",
                                "provider_name": "OpenAI-API-Compatible",
                                "model_type": "embedding",
                            },
                            {
                                "name": "qwen3-rerank",
                                "instance_name": "common-agent-rerank",
                                "provider_name": "OpenAI-API-Compatible",
                                "model_type": "rerank",
                            },
                        ],
                    },
                )
                return
            if self.path == "/api/v1/models/default":
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": {
                            "models": [
                                {
                                    "model_name": "text-embedding-v4",
                                    "model_instance": "common-agent-embedding",
                                    "model_provider": "OpenAI-API-Compatible",
                                    "model_type": "embedding",
                                },
                                {
                                    "model_name": "qwen3-rerank",
                                    "model_instance": "common-agent-rerank",
                                    "model_provider": "OpenAI-API-Compatible",
                                    "model_type": "rerank",
                                },
                            ]
                        },
                    },
                )
                return
            if self.path == "/api/v1/system/tokens":
                _send_json(self, 200, {"code": 0, "data": []})
                return
            if self.path.startswith("/api/v1/datasets?"):
                _send_json(
                    self,
                    200,
                    {
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
                return
            if self.path.startswith("/api/v1/datasets/kb-1/documents/doc-1/chunks"):
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": {
                            "total": 2,
                            "chunks": [
                                {"id": "chunk-1", "content": "第一段正文"},
                                {"id": "chunk-2", "content": "第二段正文"},
                            ],
                        },
                    },
                )
                return
            if self.path.startswith("/api/v1/datasets/kb-1/documents?"):
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": {
                            "total": 1,
                            "docs": [
                                {
                                    "id": "doc-1",
                                    "dataset_id": "kb-1",
                                    "name": "policy.md",
                                    "run": probe.document_run,
                                    "size": 12,
                                }
                            ],
                        },
                    },
                )
                return
            if self.path.startswith("/api/v1/datasets/missing/documents?"):
                _send_json(self, 404, {"code": 102, "message": "private upstream detail"})
                return
            _send_json(self, 404, {"code": 102})

        def do_PUT(self) -> None:
            payload = json.loads(_read_body(self) or b"{}")
            if self.path == "/api/v1/datasets/kb-1":
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": {
                            "id": "kb-1",
                            "name": payload["name"],
                            "description": payload["description"],
                            "document_count": 1,
                        },
                    },
                )
                return
            _send_json(self, 404, {"code": 102})

        def do_POST(self) -> None:
            body = _read_body(self)
            if self.path == "/api/v1/users":
                _send_json(self, 200, {"code": 0, "data": True})
                return
            if self.path == "/api/v1/auth/login":
                response = {"code": 0, "data": True}
                encoded = json.dumps(response).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.send_header("Authorization", "tenant-session")
                self.end_headers()
                self.wfile.write(encoded)
                return
            if self.path == "/api/v1/system/tokens":
                _send_json(
                    self,
                    200,
                    {"code": 0, "data": {"token": "ragflow-fake-token"}},
                )
                return
            if self.path == "/api/v1/datasets":
                probe.create_payloads.append(json.loads(body))
                _send_json(
                    self,
                    200,
                    {
                        "code": 0,
                        "data": {
                            "id": "kb-2",
                            "name": "员工手册",
                            "description": "人事制度",
                            "document_count": 0,
                        },
                    },
                )
                return
            if self.path == "/api/v1/datasets/kb-1/documents":
                probe.upload_bodies.append(body)
                _send_json(
                    self,
                    200,
                    {
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
                return
            if self.path == "/api/v1/datasets/kb-1/chunks":
                probe.parse_payloads.append(json.loads(body))
                _send_json(self, 200, {"code": 0, "data": True})
                return
            _send_json(self, 404, {"code": 102})

        def do_PATCH(self) -> None:
            _read_body(self)
            if self.path == "/api/v1/models/default":
                _send_json(self, 200, {"code": 0, "data": True})
                return
            _send_json(self, 404, {"code": 102})

    return Handler


@contextmanager
def _fake_ragflow() -> Iterator[tuple[str, _RagFlowProbe]]:
    asyncio.run(_clear_fake_identity())
    probe = _RagFlowProbe()
    server = _LoopbackHTTPServer(("127.0.0.1", available_port()), _handler(probe))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = cast(tuple[str, int], server.server_address)
        yield f"http://{host}:{port}", probe
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        asyncio.run(_clear_fake_identity())


def _ragflow_env(base_url: str, *, api_key: str = "layered-test-key") -> dict[str, str]:
    return {
        "RAGFLOW_BASE_URL": base_url,
        "RAGFLOW_API_KEY": api_key,
        "RAGFLOW_EXPECTED_VERSION": "v0.26.4",
        "RAGFLOW_TIMEOUT_SECONDS": "2",
    }


def test_knowledge_routes_use_formal_uvicorn_and_ragflow_adapter() -> None:
    asyncio.run(_clear_fake_ownerships())
    try:
        with (
            _fake_ragflow() as (ragflow_url, probe),
            running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            listed = client.get("/api/v1/knowledge-bases")
            created = client.post(
                "/api/v1/knowledge-bases",
                json={"name": "员工手册", "description": "人事制度"},
            )
            uploaded = client.post(
                "/api/v1/knowledge-bases/kb-1/documents",
                files={"file": ("policy.md", b"policy bytes", "text/markdown")},
            )
            documents = client.get("/api/v1/knowledge-bases/kb-1/documents")
            probe.document_run = "FAIL"
            retried = client.post("/api/v1/knowledge-bases/kb-1/documents/doc-1/retry")
    finally:
        asyncio.run(_clear_fake_ownerships())

    assert listed.status_code == 200
    assert listed.json() == {
        "items": [
            {
                "id": "kb-1",
                "name": "制度库",
                "description": "内部制度",
                "document_count": 1,
                "parsing_count": 0,
            }
        ],
        "next_cursor": None,
    }
    assert created.status_code == 201
    assert created.json()["id"] == "kb-2"
    assert uploaded.status_code == 202
    assert uploaded.json()["parsing_status"] == "parsing"
    assert documents.status_code == 200
    assert documents.json()[0]["parsing_status"] == "completed"
    assert retried.status_code == 202
    assert retried.json()["parsing_status"] == "parsing"
    assert probe.create_payloads == [
        {
            "name": "员工手册",
            "description": "人事制度",
            "permission": "me",
            "chunk_method": "naive",
            "embedding_model": ("text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible"),
        }
    ]
    assert len(probe.upload_bodies) == 1
    assert b'filename="policy.md"' in probe.upload_bodies[0]
    assert probe.parse_payloads == [
        {"document_ids": ["doc-1"]},
        {"document_ids": ["doc-1"]},
    ]


async def _clear_fake_ownerships() -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                delete(RagFlowKnowledgeBaseOwnershipRow).where(
                    RagFlowKnowledgeBaseOwnershipRow.knowledge_base_id.in_(("kb-1", "kb-2"))
                )
            )
            await session.commit()
    finally:
        await database.stop()


def test_knowledge_base_rename_goes_through_the_formal_route_and_ragflow() -> None:
    """改名走真实 Uvicorn 与 RAGFlow 适配层, 返回更新后的名称与描述。"""
    asyncio.run(_clear_fake_ownerships())
    try:
        with (
            _fake_ragflow() as (ragflow_url, _probe),
            running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            # 与真实用户路径一致: 先进列表页 (此处完成历史数据归属认领), 再改名
            client.get("/api/v1/knowledge-bases")
            updated = client.patch(
                "/api/v1/knowledge-bases/kb-1",
                json={"name": "制度库-改", "description": "改后的描述"},
            )
            missing = client.patch(
                "/api/v1/knowledge-bases/missing",
                json={"name": "不存在", "description": ""},
            )
            invalid = client.patch(
                "/api/v1/knowledge-bases/kb-1",
                json={"name": "", "description": ""},
            )
    finally:
        asyncio.run(_clear_fake_ownerships())

    assert updated.status_code == 200
    assert updated.json() == {
        "id": "kb-1",
        "name": "制度库-改",
        "description": "改后的描述",
        "document_count": 1,
        "parsing_count": 0,
    }
    assert missing.status_code == 404
    assert invalid.status_code == 422


def test_document_chunks_are_listed_through_the_formal_route() -> None:
    """切片浏览走真实 Uvicorn 与 RAGFlow 适配层, 返回带顺序的切片。"""
    asyncio.run(_clear_fake_ownerships())
    try:
        with (
            _fake_ragflow() as (ragflow_url, _probe),
            running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            client.get("/api/v1/knowledge-bases")
            chunks = client.get("/api/v1/knowledge-bases/kb-1/documents/doc-1/chunks")
            foreign = client.get("/api/v1/knowledge-bases/missing/documents/doc-1/chunks")
    finally:
        asyncio.run(_clear_fake_ownerships())

    assert chunks.status_code == 200
    assert chunks.json() == {
        "items": [
            {"id": "chunk-1", "document_id": "doc-1", "content": "第一段正文", "position": 1},
            {"id": "chunk-2", "document_id": "doc-1", "content": "第二段正文", "position": 2},
        ],
        "next_cursor": None,
    }
    assert foreign.status_code == 404


def test_upload_limits_fail_before_calling_ragflow() -> None:
    with (
        _fake_ragflow() as (ragflow_url, probe),
        running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
        authenticated_client(base_url=api_url, timeout=10) as client,
    ):
        empty = client.post(
            "/api/v1/knowledge-bases/kb-1/documents",
            files={"file": ("empty.md", b"", "text/markdown")},
        )
        unsupported = client.post(
            "/api/v1/knowledge-bases/kb-1/documents",
            files={"file": ("payload.pdf", b"binary", "application/octet-stream")},
        )
        oversized = client.post(
            "/api/v1/knowledge-bases/kb-1/documents",
            files={
                "file": (
                    "large.txt",
                    b"x" * (_MAX_DOCUMENT_SIZE_BYTES + 1),
                    "text/plain",
                )
            },
        )
        missing_file = client.post("/api/v1/knowledge-bases/kb-1/documents", data={})

    assert_error_response(empty, status=422, code="empty_document")
    assert_error_response(unsupported, status=415, code="unsupported_document_type")
    assert_error_response(oversized, status=413, code="document_too_large")
    assert_error_response(missing_file, status=422, code="validation_error")
    assert probe.upload_bodies == []


def test_create_validation_and_missing_knowledge_base_use_safe_errors() -> None:
    with (
        _fake_ragflow() as (ragflow_url, _),
        running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
        authenticated_client(base_url=api_url, timeout=5) as client,
    ):
        assert client.get("/api/v1/knowledge-bases").status_code == 200
        blank_name = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "   ", "description": "invalid"},
        )
        missing = client.get("/api/v1/knowledge-bases/missing/documents")
        completed_retry = client.post("/api/v1/knowledge-bases/kb-1/documents/doc-1/retry")
        missing_document = client.post("/api/v1/knowledge-bases/kb-1/documents/missing/retry")

    assert_error_response(blank_name, status=422, code="validation_error")
    assert_error_response(missing, status=404, code="knowledge_base_not_found")
    assert_error_response(
        completed_retry,
        status=409,
        code="knowledge_document_retry_rejected",
    )
    assert_error_response(
        missing_document,
        status=404,
        code="knowledge_document_not_found",
    )
    assert "private upstream detail" not in missing.text


def test_knowledge_service_unavailable_is_retryable_and_safe() -> None:
    with (
        running_api(
            TEST_DATABASE_URL,
            env_overrides=_ragflow_env("http://127.0.0.1:1"),
        ) as api_url,
        authenticated_client(base_url=api_url, timeout=5) as client,
    ):
        response = client.get("/api/v1/knowledge-bases")

    assert_error_response(response, status=503, code="knowledge_service_unavailable")
    assert response.json()["retryable"] is True


def test_fresh_install_provisions_default_ragflow_account_without_a_legacy_api_key() -> None:
    asyncio.run(_clear_fake_identity())
    try:
        with (
            _fake_ragflow() as (ragflow_url, _),
            running_api(
                TEST_DATABASE_URL,
                env_overrides=_ragflow_env(ragflow_url, api_key=""),
            ) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            response = client.get("/api/v1/knowledge-bases")
    finally:
        asyncio.run(_clear_fake_identity())

    assert response.status_code == 200


async def _clear_fake_identity() -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                delete(RagFlowTenantIdentityRow).where(
                    RagFlowTenantIdentityRow.tenant_id == str(DEFAULT_TENANT_ID)
                )
            )
            await session.commit()
    finally:
        await database.stop()


def test_ragflow_version_mismatch_fails_closed_before_business_request() -> None:
    with (
        _fake_ragflow() as (ragflow_url, probe),
        running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
        authenticated_client(base_url=api_url, timeout=5) as client,
    ):
        probe.version = "v0.26.0"
        response = client.get("/api/v1/knowledge-bases")

    assert_error_response(response, status=503, code="knowledge_service_version_mismatch")
    assert response.json()["retryable"] is False
