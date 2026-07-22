from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlsplit
from uuid import UUID, uuid4

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from tests.support.http import assert_error_response, authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL

_TOKEN = "managed-http-formal-secret"


class _BusinessHandler(BaseHTTPRequestHandler):
    calls: ClassVar[list[dict[str, object]]] = []

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        self.__class__.calls.append(
            {
                "path": parsed.path,
                "query": parse_qs(parsed.query),
                "authorization": self.headers.get("Authorization"),
            }
        )
        if self.headers.get("Authorization") != f"Bearer {_TOKEN}":
            self.send_response(401)
            self.end_headers()
            return
        body = json.dumps(
            {
                "data": {
                    "order": {
                        "id": parsed.path.rsplit("/", 1)[-1],
                        "fields": parse_qs(parsed.query).get("field", []),
                    }
                }
            }
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


def _capability_body(*, enabled: bool = True) -> dict[str, object]:
    return {
        "remote_name": "orders.get",
        "display_name": "查询订单",
        "description": "按订单编号查询订单。",
        "input_schema": {
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单编号"},
                "fields": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "返回字段",
                },
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
        "method": "GET",
        "path_template": "/orders/{order_id}",
        "parameter_bindings": [
            {"argument_name": "order_id", "location": "path", "target_name": "order_id"},
            {"argument_name": "fields", "location": "query", "target_name": "field"},
        ],
        "timeout_seconds": 10,
        "response_json_pointer": "/data/order",
        "enabled": enabled,
    }


def _openapi_document() -> dict[str, object]:
    return {
        "openapi": "3.0.3",
        "info": {"title": "订单业务", "version": "1.0.0"},
        "paths": {
            "/orders/{order_id}": {
                "get": {
                    "operationId": "ordersGet",
                    "summary": "查询订单",
                    "description": "按编号查询订单。",
                    "parameters": [
                        {
                            "name": "order_id",
                            "in": "path",
                            "required": True,
                            "description": "订单编号",
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "成功"}},
                }
            },
            "/orders": {
                "post": {
                    "operationId": "ordersCreate",
                    "summary": "创建订单",
                    "description": "创建新订单。",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["customer_id"],
                                    "properties": {
                                        "customer_id": {
                                            "type": "string",
                                            "description": "",
                                        }
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"201": {"description": "已创建"}},
                }
            },
        },
    }


def _import_body(draft: dict[str, object]) -> dict[str, object]:
    return {
        key: value
        for key, value in draft.items()
        if key not in {"operation_key", "issues"}
    }


async def _cleanup(source_id: UUID | None) -> None:
    if source_id is None:
        return
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            capability_ids = [
                row[0]
                for row in (
                    await session.execute(
                        text(
                            "SELECT id FROM tool_capabilities "
                            "WHERE source_id = :source_id"
                        ),
                        {"source_id": str(source_id)},
                    )
                ).all()
            ]
            for capability_id in capability_ids:
                await session.execute(
                    text("DELETE FROM employee_tool_grants WHERE capability_id = :id"),
                    {"id": capability_id},
                )
                await session.execute(
                    text("DELETE FROM conversation_tool_grants WHERE capability_id = :id"),
                    {"id": capability_id},
                )
            await session.execute(
                text("DELETE FROM mcp_sources WHERE id = :id"),
                {"id": str(source_id)},
            )
            await session.commit()
    finally:
        await database.stop()


def test_managed_http_mcp_crud_discovery_and_real_call_use_formal_api_mysql_and_mcp() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _BusinessHandler)
    _BusinessHandler.calls = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    source_id: UUID | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=10) as client,
        ):
            created = client.post(
                "/api/v1/managed-mcp-sources",
                json={
                    "name": f"订单系统-{uuid4().hex}",
                    "description": "正式托管 HTTP MCP 验收",
                    "base_url": f"http://localhost:{server.server_port}/api",
                    "enabled": True,
                },
            )
            assert created.status_code == 201
            created_payload = created.json()
            source_id = UUID(created_payload["id"])
            assert created_payload["capabilities"] == []

            credential = client.put(
                f"/api/v1/mcp-sources/{source_id}/credentials",
                json={
                    "action": "replace",
                    "kind": "bearer",
                    "bearer_token": _TOKEN,
                },
            )
            assert credential.status_code == 200
            assert credential.json()["credential"]["bearer_token"] == "********"
            assert _TOKEN not in credential.text

            added = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/capabilities",
                json=_capability_body(),
            )
            assert added.status_code == 201
            capability_id = UUID(added.json()["id"])

            discovered = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/discover"
            )
            assert discovered.status_code == 200
            assert discovered.json()["tools"] == [
                {
                    "capability_id": str(capability_id),
                    "name": "orders.get",
                    "display_name": "查询订单",
                    "description": "按订单编号查询订单。",
                    "input_schema": _capability_body()["input_schema"],
                    "schema_fingerprint": added.json()["schema_fingerprint"],
                }
            ]

            called = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/capabilities/"
                f"{capability_id}/test-call",
                json={"arguments": {"order_id": "A-100", "fields": ["status", "owner"]}},
            )
            assert called.status_code == 200
            assert called.json() == {
                "capability_id": str(capability_id),
                "output": {"id": "A-100", "fields": ["status", "owner"]},
            }
            assert _BusinessHandler.calls == [
                {
                    "path": "/api/orders/A-100",
                    "query": {"field": ["status", "owner"]},
                    "authorization": f"Bearer {_TOKEN}",
                }
            ]
            assert _TOKEN not in called.text

            employees = client.get("/api/v1/employees", params={"limit": 1})
            assert employees.status_code == 200
            employee_id = employees.json()["items"][0]["id"]
            granted = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": [str(capability_id)]},
            )
            assert granted.status_code == 200
            conflict = client.delete(
                f"/api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}"
            )
            assert_error_response(conflict, status=409, code="managed_mcp_conflict")
            cleared = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": []},
            )
            assert cleared.status_code == 200

            disabled = client.put(
                f"/api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}",
                json=_capability_body(enabled=False),
            )
            assert disabled.status_code == 200
            assert disabled.json()["enabled"] is False
            rediscovered = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/discover"
            )
            assert rediscovered.status_code == 200
            assert rediscovered.json()["tools"] == []

            deleted_capability = client.delete(
                f"/api/v1/managed-mcp-sources/{source_id}/capabilities/{capability_id}"
            )
            assert deleted_capability.status_code == 204

            endpoint_changed = client.put(
                f"/api/v1/managed-mcp-sources/{source_id}",
                json={
                    "name": created_payload["name"],
                    "description": created_payload["description"],
                    "base_url": "https://business-v2.example/api",
                    "enabled": True,
                },
            )
            assert endpoint_changed.status_code == 200
            credential_after_change = client.get(
                f"/api/v1/mcp-sources/{source_id}/credentials"
            )
            assert credential_after_change.status_code == 200
            assert credential_after_change.json()["configured"] is False

            deleted_source = client.delete(f"/api/v1/managed-mcp-sources/{source_id}")
            assert deleted_source.status_code == 204
            assert client.get(f"/api/v1/managed-mcp-sources/{source_id}").status_code == 404
            source_id = None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        asyncio.run(_cleanup(source_id))


def test_openapi_preview_selection_and_atomic_import_use_formal_api_and_mysql() -> None:
    source_id: UUID | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=10) as client,
        ):
            created = client.post(
                "/api/v1/managed-mcp-sources",
                json={
                    "name": f"OpenAPI 订单系统-{uuid4().hex}",
                    "description": "OpenAPI 正式验收",
                    "base_url": "https://business.example/api",
                    "enabled": True,
                },
            )
            assert created.status_code == 201
            source_id = UUID(created.json()["id"])

            preview = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/openapi/preview",
                files={
                    "file": (
                        "orders.openapi.json",
                        json.dumps(_openapi_document(), ensure_ascii=False).encode(),
                        "application/json",
                    )
                },
            )
            assert preview.status_code == 200
            payload = preview.json()
            assert payload["title"] == "订单业务"
            assert payload["version"] == "1.0.0"
            assert payload["existing_remote_names"] == []
            assert [item["remote_name"] for item in payload["drafts"]] == [
                "orders_get",
                "orders_create",
            ]
            assert payload["drafts"][0]["issues"] == []
            assert payload["drafts"][1]["issues"] == ["参数 customer_id 缺少含义"]
            assert client.get(
                f"/api/v1/managed-mcp-sources/{source_id}"
            ).json()["capabilities"] == []

            rejected = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/openapi/import",
                json={
                    "capabilities": [
                        _import_body(payload["drafts"][0]),
                        _import_body(payload["drafts"][1]),
                    ]
                },
            )
            assert_error_response(rejected, status=422, code="validation_error")
            assert client.get(
                f"/api/v1/managed-mcp-sources/{source_id}"
            ).json()["capabilities"] == []

            selected = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/openapi/import",
                json={"capabilities": [_import_body(payload["drafts"][0])]},
            )
            assert selected.status_code == 201
            assert [item["remote_name"] for item in selected.json()["items"]] == [
                "orders_get"
            ]

            create_body = _import_body(payload["drafts"][1])
            create_schema = create_body["input_schema"]
            assert isinstance(create_schema, dict)
            properties = create_schema["properties"]
            assert isinstance(properties, dict)
            customer = properties["customer_id"]
            assert isinstance(customer, dict)
            customer["description"] = "客户编号"
            conflict = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/openapi/import",
                json={
                    "capabilities": [
                        create_body,
                        _import_body(payload["drafts"][0]),
                    ]
                },
            )
            assert_error_response(conflict, status=409, code="managed_mcp_conflict")
            detail = client.get(f"/api/v1/managed-mcp-sources/{source_id}").json()
            assert [item["remote_name"] for item in detail["capabilities"]] == [
                "orders_get"
            ]

            imported = client.post(
                f"/api/v1/managed-mcp-sources/{source_id}/openapi/import",
                json={"capabilities": [create_body]},
            )
            assert imported.status_code == 201
            assert [item["remote_name"] for item in imported.json()["items"]] == [
                "orders_create"
            ]
    finally:
        asyncio.run(_cleanup(source_id))
