from __future__ import annotations

import asyncio
from time import monotonic, sleep
from uuid import UUID, uuid4

import httpx

from common_agent.adapters.persistence.database import Database
from tests.support.conversations import delete_conversations
from tests.support.demo_knowledge import delete_demo_knowledge_bases
from tests.support.employees import delete_employees
from tests.support.http import assert_error_response, authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows

_DEMO_ENV = {"COMMON_AGENT_INTEGRATION_MODE": "demo"}


def test_all_resource_delete_apis_enforce_references_cascade_and_idempotency() -> None:
    suffix = uuid4().hex
    conversation_id = uuid4()
    knowledge_base_id = ""
    employee_id: UUID | None = None
    workflow_id: UUID | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL, env_overrides=_DEMO_ENV) as api_url,
            authenticated_client(base_url=api_url, timeout=15) as client,
        ):
            knowledge = client.post(
                "/api/v1/knowledge-bases",
                json={"name": f"U9 删除知识库 {suffix}", "description": "引用边界"},
            )
            assert knowledge.status_code == 201
            knowledge_base_id = str(knowledge.json()["id"])
            uploaded = client.post(
                f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
                files={"file": ("delete.txt", b"delete cascade", "text/plain")},
            )
            assert uploaded.status_code == 202

            workflow = client.post(
                "/api/v1/workflows",
                json=_workflow_body(suffix, knowledge_base_id),
            )
            assert workflow.status_code == 201
            workflow_id = UUID(workflow.json()["id"])

            employee = client.post(
                "/api/v1/employees",
                json=_employee_body(
                    suffix,
                    knowledge_base_id=knowledge_base_id,
                    workflow_id=workflow_id,
                ),
            )
            assert employee.status_code == 201
            employee_id = UUID(employee.json()["id"])
            conversation = client.post(
                "/api/v1/conversations",
                json={
                    "conversation_id": str(conversation_id),
                    "employee_id": str(employee_id),
                    "title": "U9 删除会话",
                },
            )
            assert conversation.status_code == 201
            sent = client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={"message_id": str(uuid4()), "content": "删除前完成一轮消息"},
            )
            assert sent.status_code == 202
            _wait_for_conversation_terminal(client, conversation_id)

            assert_error_response(
                client.delete(f"/api/v1/employees/{employee_id}"),
                status=409,
                code="employee_in_use_by_conversations",
            )
            assert_error_response(
                client.delete(f"/api/v1/knowledge-bases/{knowledge_base_id}"),
                status=409,
                code="knowledge_base_in_use_by_employees",
            )

            employee_without_knowledge = client.put(
                f"/api/v1/employees/{employee_id}",
                json=_employee_body(suffix, knowledge_base_id=None, workflow_id=workflow_id),
            )
            assert employee_without_knowledge.status_code == 200
            assert_error_response(
                client.delete(f"/api/v1/knowledge-bases/{knowledge_base_id}"),
                status=409,
                code="knowledge_base_in_use_by_workflows",
            )
            assert_error_response(
                client.delete(f"/api/v1/workflows/{workflow_id}"),
                status=409,
                code="workflow_in_use_by_employees",
            )
            updated_workflow = client.put(
                f"/api/v1/workflows/{workflow_id}",
                json=_slow_workflow_body(suffix),
            )
            assert updated_workflow.status_code == 200

            unbound = client.put(
                f"/api/v1/employees/{employee_id}",
                json=_employee_body(suffix, knowledge_base_id=None, workflow_id=None),
            )
            assert unbound.status_code == 200
            run_id = uuid4()
            started = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={"run_id": str(run_id), "input": "删除前运行" * 200},
            )
            assert started.status_code == 202
            assert_error_response(
                client.delete(f"/api/v1/workflows/{workflow_id}"),
                status=409,
                code="workflow_has_active_runs",
            )
            _wait_for_workflow_terminal(client, run_id)
            _assert_idempotent_delete(client, f"/api/v1/workflows/{workflow_id}")
            assert client.get(f"/api/v1/workflows/{workflow_id}").status_code == 404
            assert client.get(f"/api/v1/workflow-runs/{run_id}").status_code == 404

            _assert_idempotent_delete(
                client,
                f"/api/v1/knowledge-bases/{knowledge_base_id}",
            )
            assert (
                client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/documents").status_code
                == 404
            )

            _assert_idempotent_delete(client, f"/api/v1/conversations/{conversation_id}")
            assert (
                client.get(f"/api/v1/conversations/{conversation_id}/messages").status_code == 404
            )
            _assert_idempotent_delete(client, f"/api/v1/employees/{employee_id}")
            assert client.get(f"/api/v1/employees/{employee_id}").status_code == 404
    finally:
        asyncio.run(
            _cleanup(
                conversation_id,
                employee_id,
                workflow_id,
                knowledge_base_id,
            )
        )


def _assert_idempotent_delete(client: httpx.Client, path: str) -> None:
    assert client.delete(path).status_code == 204
    assert client.delete(path).status_code == 204


def _wait_for_conversation_terminal(client: httpx.Client, conversation_id: UUID) -> None:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        response = client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert response.status_code == 200
        messages = response.json()
        if len(messages) == 2 and messages[-1]["status"] in {
            "completed",
            "failed",
            "stopped",
        }:
            return
        sleep(0.05)
    raise AssertionError("会话未在删除测试期限内进入终态")


def _wait_for_workflow_terminal(client: httpx.Client, run_id: UUID) -> None:
    deadline = monotonic() + 5
    while monotonic() < deadline:
        response = client.get(f"/api/v1/workflow-runs/{run_id}")
        assert response.status_code == 200
        if response.json()["status"] in {"completed", "failed", "stopped"}:
            return
        sleep(0.05)
    raise AssertionError("工作流未在删除测试期限内进入终态")


def _employee_body(
    suffix: str,
    *,
    knowledge_base_id: str | None,
    workflow_id: UUID | None,
) -> dict[str, object]:
    return {
        "name": f"U9 删除员工 {suffix}",
        "description": "引用边界",
        "system_prompt": "只用于删除验收。",
        "knowledge_base_id": knowledge_base_id,
        "allowed_workflow_ids": [] if workflow_id is None else [str(workflow_id)],
    }


def _workflow_body(suffix: str, knowledge_base_id: str) -> dict[str, object]:
    return {
        "name": f"U9 删除工作流 {suffix}",
        "description": "引用边界",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "retrieve",
                "type": "knowledge_retrieval",
                "position": {"x": 200, "y": 0},
                "config": {"knowledge_base_id": knowledge_base_id},
            },
            {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "edge-1", "source": "start", "target": "retrieve"},
            {"id": "edge-2", "source": "retrieve", "target": "end"},
        ],
    }


def _slow_workflow_body(suffix: str) -> dict[str, object]:
    return {
        "name": f"U9 删除工作流 {suffix}",
        "description": "活动运行边界",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "chat",
                "type": "ai_chat",
                "position": {"x": 200, "y": 0},
                "config": {"prompt": "缓慢输出删除验收结果"},
            },
            {"id": "end", "type": "end", "position": {"x": 400, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "edge-1", "source": "start", "target": "chat"},
            {"id": "edge-2", "source": "chat", "target": "end"},
        ],
    }


async def _cleanup(
    conversation_id: UUID,
    employee_id: UUID | None,
    workflow_id: UUID | None,
    knowledge_base_id: str,
) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        await delete_conversations(database, conversation_id)
        if employee_id is not None:
            await delete_employees(database, employee_id)
        if workflow_id is not None:
            await delete_workflows(database, workflow_id)
        if knowledge_base_id:
            await delete_demo_knowledge_bases(database, knowledge_base_id)
    finally:
        await database.stop()
