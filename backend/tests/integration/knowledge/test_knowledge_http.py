from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from socketserver import TCPServer
from typing import Any, cast

import httpx

from tests.support.http import assert_error_response, available_port, running_api
from tests.support.settings import TEST_DATABASE_URL

_MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024


@dataclass(slots=True)
class _RagFlowProbe:
    version: str = "v0.25.6"
    create_payloads: list[dict[str, Any]] = field(default_factory=list)
    upload_bodies: list[bytes] = field(default_factory=list)
    parse_payloads: list[dict[str, Any]] = field(default_factory=list)


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
                                    "run": "DONE",
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

        def do_POST(self) -> None:
            body = _read_body(self)
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

    return Handler


@contextmanager
def _fake_ragflow() -> Iterator[tuple[str, _RagFlowProbe]]:
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


def _ragflow_env(base_url: str, *, api_key: str = "layered-test-key") -> dict[str, str]:
    return {
        "RAGFLOW_BASE_URL": base_url,
        "RAGFLOW_API_KEY": api_key,
        "RAGFLOW_EXPECTED_VERSION": "v0.25.6",
        "RAGFLOW_TIMEOUT_SECONDS": "2",
    }


def test_knowledge_routes_use_formal_uvicorn_and_ragflow_adapter() -> None:
    with (
        _fake_ragflow() as (ragflow_url, probe),
        running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
        httpx.Client(base_url=api_url, timeout=5) as client,
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

    assert listed.status_code == 200
    assert listed.json() == [
        {
            "id": "kb-1",
            "name": "制度库",
            "description": "内部制度",
            "document_count": 1,
            "parsing_count": 0,
        }
    ]
    assert created.status_code == 201
    assert created.json()["id"] == "kb-2"
    assert uploaded.status_code == 202
    assert uploaded.json()["parsing_status"] == "parsing"
    assert documents.status_code == 200
    assert documents.json()[0]["parsing_status"] == "completed"
    assert probe.create_payloads == [
        {
            "name": "员工手册",
            "description": "人事制度",
            "permission": "me",
            "chunk_method": "naive",
        }
    ]
    assert len(probe.upload_bodies) == 1
    assert b'filename="policy.md"' in probe.upload_bodies[0]
    assert probe.parse_payloads == [{"document_ids": ["doc-1"]}]


def test_upload_limits_fail_before_calling_ragflow() -> None:
    with (
        _fake_ragflow() as (ragflow_url, probe),
        running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
        httpx.Client(base_url=api_url, timeout=10) as client,
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
        httpx.Client(base_url=api_url, timeout=5) as client,
    ):
        blank_name = client.post(
            "/api/v1/knowledge-bases",
            json={"name": "   ", "description": "invalid"},
        )
        missing = client.get("/api/v1/knowledge-bases/missing/documents")

    assert_error_response(blank_name, status=422, code="validation_error")
    assert_error_response(missing, status=404, code="knowledge_base_not_found")
    assert "private upstream detail" not in missing.text


def test_knowledge_service_unavailable_is_retryable_and_safe() -> None:
    with running_api(
        TEST_DATABASE_URL,
        env_overrides=_ragflow_env("http://127.0.0.1:1"),
    ) as api_url:
        response = httpx.get(f"{api_url}/api/v1/knowledge-bases", timeout=5)

    assert_error_response(response, status=503, code="knowledge_service_unavailable")
    assert response.json()["retryable"] is True


def test_knowledge_service_missing_configuration_is_permanent_and_safe() -> None:
    with (
        _fake_ragflow() as (ragflow_url, _),
        running_api(
            TEST_DATABASE_URL,
            env_overrides=_ragflow_env(ragflow_url, api_key=""),
        ) as api_url,
    ):
        response = httpx.get(f"{api_url}/api/v1/knowledge-bases", timeout=5)

    assert_error_response(response, status=503, code="configuration_missing")
    assert response.json()["retryable"] is False


def test_ragflow_version_mismatch_fails_closed_before_business_request() -> None:
    with (
        _fake_ragflow() as (ragflow_url, probe),
        running_api(TEST_DATABASE_URL, env_overrides=_ragflow_env(ragflow_url)) as api_url,
    ):
        probe.version = "v0.26.0"
        response = httpx.get(f"{api_url}/api/v1/knowledge-bases", timeout=5)

    assert_error_response(response, status=503, code="knowledge_service_version_mismatch")
    assert response.json()["retryable"] is False
