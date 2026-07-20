from __future__ import annotations

import asyncio
import json
from time import monotonic, sleep
from typing import cast
from uuid import UUID, uuid4

import httpx

from tests.support.http import assert_error_response, running_api
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows_from_database_url


def _workflow_body() -> dict[str, object]:
    return {
        "name": "运行接口工作流",
        "description": "W5-04 正式 Uvicorn 验收",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
            {
                "id": "chat",
                "type": "ai_chat",
                "position": {"x": 240, "y": 0},
                "config": {"prompt": "直接回答工作流输入"},
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 480, "y": 0},
                "config": {},
            },
        ],
        "edges": [
            {"id": "edge-1", "source": "start", "target": "chat"},
            {"id": "edge-2", "source": "chat", "target": "end"},
        ],
    }


def _terminal(client: httpx.Client, run_id: str) -> dict[str, object]:
    deadline = monotonic() + 10
    while monotonic() < deadline:
        response = client.get(f"/api/v1/workflow-runs/{run_id}")
        assert response.status_code == 200
        run = cast(dict[str, object], response.json())
        if run["status"] in {"completed", "failed", "stopped"}:
            return run
        sleep(0.02)
    raise AssertionError("工作流运行未进入终态")


def _event_types(client: httpx.Client, run_id: str, terminal_type: str) -> list[str]:
    event_types: list[str] = []
    with client.stream("GET", f"/api/v1/workflow-runs/{run_id}/events") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
                event_types.append(event_type)
                if event_type == terminal_type:
                    break
            if line.startswith("data: "):
                payload = json.loads(line.removeprefix("data: "))
                assert payload["schema_version"] == "1"
                assert payload["run_id"] == run_id
    return event_types


def test_workflow_run_http_and_sse_persist_summary_across_restart() -> None:
    workflow_id: str | None = None
    completed_run_id = str(uuid4())
    stopped_run_id = str(uuid4())
    environment = {"COMMON_AGENT_INTEGRATION_MODE": "demo"}
    try:
        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as api_url,
            httpx.Client(base_url=api_url, timeout=10) as client,
        ):
            created = client.post("/api/v1/workflows", json=_workflow_body())
            assert created.status_code == 201
            workflow_id = str(created.json()["id"])

            accepted = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={"run_id": completed_run_id, "input": "HTTP 运行输入"},
            )
            assert accepted.status_code == 202
            assert accepted.json()["status"] == "running"
            assert accepted.json()["origin"] is None
            completed = _terminal(client, completed_run_id)
            assert completed["status"] == "completed"
            assert "HTTP 运行输入" in str(completed["output"])
            assert completed["completed_node_ids"] == ["start", "chat", "end"]
            assert _event_types(client, completed_run_id, "workflow.run.completed") == [
                "workflow.run.started",
                "workflow.node.started",
                "workflow.node.completed",
                "workflow.node.started",
                "workflow.node.completed",
                "workflow.node.started",
                "workflow.node.completed",
                "workflow.run.completed",
            ]

            duplicate = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={"run_id": completed_run_id, "input": "重复请求"},
            )
            assert_error_response(duplicate, status=409, code="workflow_run_conflict")

            stop_accepted = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={"run_id": stopped_run_id, "input": "停止这个较长的演示工作流"},
            )
            assert stop_accepted.status_code == 202
            stopped = client.post(f"/api/v1/workflow-runs/{stopped_run_id}/stop")
            assert stopped.status_code == 202
            assert stopped.json() == {"run_id": stopped_run_id}
            stopped_summary = _terminal(client, stopped_run_id)
            assert stopped_summary["status"] == "stopped"
            assert _event_types(client, stopped_run_id, "workflow.run.stopped")[-1] == (
                "workflow.run.stopped"
            )

            missing_workflow = client.post(
                f"/api/v1/workflows/{uuid4()}/runs",
                json={"run_id": str(uuid4()), "input": "missing"},
            )
            assert_error_response(missing_workflow, status=404, code="workflow_not_found")
            invalid_input = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={"run_id": str(uuid4()), "input": ""},
            )
            assert_error_response(invalid_input, status=422, code="validation_error")
            missing_run = client.get(f"/api/v1/workflow-runs/{uuid4()}")
            assert_error_response(missing_run, status=404, code="workflow_run_not_found")
            unrelated_runs = client.get(
                "/api/v1/workflow-runs",
                params={"conversation_id": str(uuid4())},
            )
            assert unrelated_runs.status_code == 200
            assert unrelated_runs.json() == {"items": [], "next_cursor": None}
            invalid_conversation = client.get(
                "/api/v1/workflow-runs",
                params={"conversation_id": "not-a-uuid"},
            )
            assert_error_response(
                invalid_conversation,
                status=422,
                code="validation_error",
            )

        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as restarted_url,
            httpx.Client(base_url=restarted_url, timeout=10) as restarted,
        ):
            restored = restarted.get(f"/api/v1/workflow-runs/{completed_run_id}")
            assert restored.status_code == 200
            assert restored.json()["status"] == "completed"
            UUID(restored.json()["workflow_id"])
    finally:
        if workflow_id is not None:
            asyncio.run(delete_workflows_from_database_url(TEST_DATABASE_URL, workflow_id))
