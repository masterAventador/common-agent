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
            source_id = UUID(created.json()["id"])
            assert created.json()["capabilities"] == []

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
            deleted_source = client.delete(f"/api/v1/managed-mcp-sources/{source_id}")
            assert deleted_source.status_code == 204
            assert client.get(f"/api/v1/managed-mcp-sources/{source_id}").status_code == 404
            source_id = None
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        asyncio.run(_cleanup(source_id))
