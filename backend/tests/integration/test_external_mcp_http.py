from __future__ import annotations

import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from uuid import UUID, uuid4

import uvicorn
from mcp.server.fastmcp import FastMCP
from sqlalchemy import text
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from common_agent.adapters.persistence.database import Database
from tests.support.employees import DEFAULT_TEST_MODEL_CONFIGURATION_ID
from tests.support.http import authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL

_TOKEN = "external-mcp-formal-secret"


@dataclass(slots=True)
class _RunningMcp:
    endpoint: str
    server: FastMCP[object]
    request_count: int = 0


class _BearerMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: object, state: _RunningMcp) -> None:
        super().__init__(app)  # type: ignore[arg-type]
        self._state = state

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        self._state.request_count += 1
        if request.headers.get("Authorization") != f"Bearer {_TOKEN}":
            return Response(status_code=401)
        return await call_next(request)


def _orders_get(order_id: str) -> dict[str, object]:
    return {"id": order_id, "status": "paid"}


def _orders_get_v2(order_id: int) -> dict[str, object]:
    return {"id": order_id, "status": "paid-v2"}


def _orders_delete(order_id: str) -> dict[str, object]:
    return {"deleted": order_id}


@contextmanager
def _real_external_mcp() -> Iterator[_RunningMcp]:
    mcp: FastMCP[object] = FastMCP(
        "外部订单正式测试",
        stateless_http=True,
        json_response=True,
    )
    mcp.add_tool(
        _orders_get,
        name="orders_get",
        title="查询订单",
        description="按编号查询订单。",
        structured_output=True,
    )
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = int(listener.getsockname()[1])
    state = _RunningMcp(f"http://localhost:{port}/mcp", mcp)
    app = mcp.streamable_http_app()
    app.add_middleware(_BearerMiddleware, state=state)
    uvicorn_server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error")
    )
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    for _ in range(100):
        if uvicorn_server.started:
            break
        time.sleep(0.05)
    if not uvicorn_server.started:
        raise RuntimeError("正式 MCP 测试服务启动失败")
    try:
        yield state
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=5)


def _employee_body() -> dict[str, object]:
    return {
        "name": f"外部 MCP 授权员工-{uuid4().hex}",
        "description": "验证集合授权不会随同步自动扩张",
        "system_prompt": "只调用明确授权的工具。",
        "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
        "knowledge_base_id": None,
        "allowed_workflow_ids": [],
    }


def test_external_mcp_sync_collection_and_call_use_formal_api_mysql_and_protocol() -> None:
    source_id: UUID | None = None
    managed_source_id: UUID | None = None
    collection_id: UUID | None = None
    employee_id: UUID | None = None
    try:
        with _real_external_mcp() as remote, running_api(
            TEST_DATABASE_URL,
            env_overrides={"COMMON_AGENT_ENVIRONMENT": "local"},
        ) as api_url, authenticated_client(base_url=api_url, timeout=15) as client:
            created = client.post(
                "/api/v1/external-mcp-sources",
                json={
                    "name": f"合作方 MCP-{uuid4().hex}",
                    "description": "正式 Streamable HTTP 测试",
                    "endpoint_url": remote.endpoint,
                },
            )
            assert created.status_code == 201
            source = created.json()
            source_id = UUID(source["id"])
            assert source["status"] == "draft"
            assert source["capabilities"] == []
            assert remote.request_count == 0

            credential = client.put(
                f"/api/v1/mcp-sources/{source_id}/credentials",
                json={
                    "action": "replace",
                    "kind": "bearer",
                    "bearer_token": _TOKEN,
                    "headers": None,
                },
            )
            assert credential.status_code == 200
            assert credential.json()["credential"]["bearer_token"] == "********"

            first_sync = client.post(f"/api/v1/external-mcp-sources/{source_id}/sync")
            assert first_sync.status_code == 200
            first_payload = first_sync.json()
            assert first_payload["added"] == 1
            assert first_payload["source"]["status"] == "ready"
            first_capability = first_payload["source"]["capabilities"][0]
            first_capability_id = UUID(first_capability["id"])
            assert first_capability["status"] == "active"

            managed = client.post(
                "/api/v1/managed-mcp-sources",
                json={
                    "name": f"内部订单-{uuid4().hex}",
                    "description": "集合中的平台托管来源",
                    "base_url": "https://business.example/api",
                    "enabled": True,
                },
            )
            assert managed.status_code == 201
            managed_source_id = UUID(managed.json()["id"])

            collection = client.post(
                "/api/v1/tool-collections",
                json={
                    "name": f"订单工具集-{uuid4().hex}",
                    "description": "聚合内部与外部 MCP",
                    "source_ids": [str(managed_source_id), str(source_id)],
                },
            )
            assert collection.status_code == 201
            collection_id = UUID(collection.json()["id"])
            assert set(collection.json()["source_ids"]) == {
                str(managed_source_id),
                str(source_id),
            }

            employee = client.post("/api/v1/employees", json=_employee_body())
            assert employee.status_code == 201
            employee_id = UUID(employee.json()["id"])
            grant = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [str(collection_id)], "capability_ids": []},
            )
            assert grant.status_code == 200
            assert grant.json()["capability_ids"] == [str(first_capability_id)]

            remote.server.remove_tool("orders_get")
            remote.server.add_tool(
                _orders_get_v2,
                name="orders_get",
                title="查询订单 V2",
                description="按数字编号查询订单。",
                structured_output=True,
            )
            remote.server.add_tool(
                _orders_delete,
                name="orders_delete",
                title="删除订单",
                description="删除指定订单。",
                structured_output=True,
            )
            drift = client.post(f"/api/v1/external-mcp-sources/{source_id}/sync")
            assert drift.status_code == 200
            drift_payload = drift.json()
            assert drift_payload["added"] == 1
            assert drift_payload["schema_changed"] == 1
            drift_by_name = {
                item["remote_name"]: item for item in drift_payload["source"]["capabilities"]
            }
            assert UUID(drift_by_name["orders_get"]["id"]) == first_capability_id
            assert drift_by_name["orders_get"]["status"] == "unavailable"

            unchanged_grant = client.get(f"/api/v1/employees/{employee_id}/tool-grants")
            assert unchanged_grant.status_code == 200
            assert unchanged_grant.json()["capability_ids"] == [str(first_capability_id)]

            confirmed = client.post(f"/api/v1/external-mcp-sources/{source_id}/sync")
            assert confirmed.status_code == 200
            assert confirmed.json()["reactivated"] == 1
            confirmed_get = next(
                item
                for item in confirmed.json()["source"]["capabilities"]
                if item["remote_name"] == "orders_get"
            )
            assert UUID(confirmed_get["id"]) == first_capability_id
            assert confirmed_get["status"] == "active"

            called = client.post(
                f"/api/v1/external-mcp-sources/{source_id}/capabilities/"
                f"{first_capability_id}/test-call",
                json={"arguments": {"order_id": 100}},
            )
            assert called.status_code == 200
            assert called.json()["output"] == {"id": 100, "status": "paid-v2"}

            remote.server.remove_tool("orders_delete")
            removed = client.post(f"/api/v1/external-mcp-sources/{source_id}/sync")
            assert removed.status_code == 200
            assert removed.json()["removed"] == 1
            removed_tool = next(
                item
                for item in removed.json()["source"]["capabilities"]
                if item["remote_name"] == "orders_delete"
            )
            assert removed_tool["status"] == "unavailable"

            blocked = client.delete(f"/api/v1/external-mcp-sources/{source_id}")
            assert blocked.status_code == 409
            assert blocked.json()["code"] == "external_mcp_conflict"

            assert client.delete(f"/api/v1/tool-collections/{collection_id}").status_code == 204
            collection_id = None
            cleared = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": []},
            )
            assert cleared.status_code == 200

            endpoint_changed = client.put(
                f"/api/v1/external-mcp-sources/{source_id}",
                json={
                    "name": source["name"],
                    "description": source["description"],
                    "endpoint_url": "https://mcp-v2.partner.example/mcp",
                },
            )
            assert endpoint_changed.status_code == 200
            assert endpoint_changed.json()["status"] == "draft"
            credential_after_change = client.get(
                f"/api/v1/mcp-sources/{source_id}/credentials"
            )
            assert credential_after_change.status_code == 200
            assert credential_after_change.json()["configured"] is False

            assert client.delete(f"/api/v1/external-mcp-sources/{source_id}").status_code == 204
            source_id = None
            assert client.delete(
                f"/api/v1/managed-mcp-sources/{managed_source_id}"
            ).status_code == 204
            managed_source_id = None
            assert client.delete(f"/api/v1/employees/{employee_id}").status_code == 204
            employee_id = None
    finally:
        asyncio.run(
            _cleanup(
                source_id=source_id,
                managed_source_id=managed_source_id,
                collection_id=collection_id,
                employee_id=employee_id,
            )
        )


async def _cleanup(
    *,
    source_id: UUID | None,
    managed_source_id: UUID | None,
    collection_id: UUID | None,
    employee_id: UUID | None,
) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            if employee_id is not None:
                await session.execute(
                    text("DELETE FROM employees WHERE id = :id"),
                    {"id": str(employee_id)},
                )
            if collection_id is not None:
                await session.execute(
                    text("DELETE FROM tool_collections WHERE id = :id"),
                    {"id": str(collection_id)},
                )
            for value in (source_id, managed_source_id):
                if value is not None:
                    await session.execute(
                        text("DELETE FROM mcp_sources WHERE id = :id"),
                        {"id": str(value)},
                    )
            await session.commit()
    finally:
        await database.stop()
