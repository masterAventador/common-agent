from __future__ import annotations

import asyncio
import json
import os
from time import monotonic, sleep
from typing import cast
from uuid import uuid4

import httpx
import pytest

from tests.support.http import running_api
from tests.support.ragflow import delete_dataset, provision_api_key
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows_from_database_url


def test_real_workflow_run_http_uses_ragflow_langgraph_and_bailian() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实百炼验收")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    environment = {
        "COMMON_AGENT_INTEGRATION_MODE": "real",
        "RAGFLOW_BASE_URL": base_url,
        "RAGFLOW_API_KEY": api_key,
        "RAGFLOW_EXPECTED_VERSION": expected_version,
        "RAGFLOW_TIMEOUT_SECONDS": "120",
    }
    dataset_id: str | None = None
    workflow_id: str | None = None
    completed_run_id = str(uuid4())
    stopped_run_id = str(uuid4())
    failed_run_id = str(uuid4())
    marker = f"COMMON_AGENT_W5_04_{uuid4().hex}"
    try:
        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as api_url,
            httpx.Client(base_url=api_url, timeout=180) as client,
        ):
            created_dataset = client.post(
                "/api/v1/knowledge-bases",
                json={
                    "name": f"common-agent-w5-04-{uuid4().hex}",
                    "description": "W5-04 工作流正式运行验收",
                },
            )
            assert created_dataset.status_code == 201
            dataset_id = str(created_dataset.json()["id"])

            uploaded = client.post(
                f"/api/v1/knowledge-bases/{dataset_id}/documents",
                files={
                    "file": (
                        "w5-04-handbook.txt",
                        f"W5-04 工作流运行的唯一验收标记是 {marker}。".encode(),
                        "text/plain",
                    )
                },
            )
            assert uploaded.status_code == 202
            _wait_for_document(client, dataset_id, str(uploaded.json()["id"]))

            created_workflow = client.post("/api/v1/workflows", json=_workflow_body(dataset_id))
            assert created_workflow.status_code == 201
            workflow_id = str(created_workflow.json()["id"])

            accepted = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={
                    "run_id": completed_run_id,
                    "input": f"请从知识库找出 W5-04 的唯一验收标记。提示: {marker}",
                },
            )
            assert accepted.status_code == 202
            assert accepted.json()["status"] == "running"
            completed = _terminal(client, completed_run_id)
            assert completed["status"] == "completed"
            assert marker in str(completed["output"])
            assert completed["completed_node_ids"] == ["start", "retrieve", "chat", "end"]
            assert _events(client, completed_run_id, "workflow.run.completed") == [
                "workflow.run.started",
                "workflow.node.started",
                "workflow.node.completed",
                "workflow.node.started",
                "workflow.node.completed",
                "workflow.node.started",
                "workflow.node.completed",
                "workflow.node.started",
                "workflow.node.completed",
                "workflow.run.completed",
            ]

            stop_started = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={"run_id": stopped_run_id, "input": f"再次检索 {marker}"},
            )
            assert stop_started.status_code == 202
            stop_accepted = client.post(f"/api/v1/workflow-runs/{stopped_run_id}/stop")
            assert stop_accepted.status_code == 202
            stopped = _terminal(client, stopped_run_id)
            assert stopped["status"] == "stopped"
            assert stopped["output"] == ""

            asyncio.run(delete_dataset(base_url, api_key, dataset_id))
            dataset_id = None
            failure_started = client.post(
                f"/api/v1/workflows/{workflow_id}/runs",
                json={"run_id": failed_run_id, "input": f"检索已失效知识库中的 {marker}"},
            )
            assert failure_started.status_code == 202
            failed = _terminal(client, failed_run_id)
            assert failed["status"] == "failed"
            assert failed["failed_node_id"] == "retrieve"
            assert failed["error_code"] == "knowledge_base_not_found"
            assert _events(client, failed_run_id, "workflow.run.failed")[-2:] == [
                "workflow.node.failed",
                "workflow.run.failed",
            ]

        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as restarted_url,
            httpx.Client(base_url=restarted_url, timeout=180) as restarted,
        ):
            restored = restarted.get(f"/api/v1/workflow-runs/{completed_run_id}")
            assert restored.status_code == 200
            assert restored.json()["status"] == "completed"
            assert marker in restored.json()["output"]
    finally:
        if workflow_id is not None:
            asyncio.run(delete_workflows_from_database_url(TEST_DATABASE_URL, workflow_id))
        if dataset_id is not None:
            asyncio.run(delete_dataset(base_url, api_key, dataset_id))


def _workflow_body(knowledge_base_id: str) -> dict[str, object]:
    return {
        "name": f"common-agent-w5-04-{uuid4().hex}",
        "description": "W5-04 正式 API、RAGFlow、LangGraph 与百炼验收",
        "nodes": [
            {
                "id": "start",
                "type": "start",
                "position": {"x": 0, "y": 0},
                "config": {},
            },
            {
                "id": "retrieve",
                "type": "knowledge_retrieval",
                "position": {"x": 240, "y": 0},
                "config": {"knowledge_base_id": knowledge_base_id},
            },
            {
                "id": "chat",
                "type": "ai_chat",
                "position": {"x": 480, "y": 0},
                "config": {"prompt": "根据检索内容回答,只输出唯一验收标记,不要添加其他文字。"},
            },
            {
                "id": "end",
                "type": "end",
                "position": {"x": 720, "y": 0},
                "config": {},
            },
        ],
        "edges": [
            {"id": "edge-1", "source": "start", "target": "retrieve"},
            {"id": "edge-2", "source": "retrieve", "target": "chat"},
            {"id": "edge-3", "source": "chat", "target": "end"},
        ],
    }


def _wait_for_document(client: httpx.Client, dataset_id: str, document_id: str) -> None:
    deadline = monotonic() + 900
    while monotonic() < deadline:
        response = client.get(f"/api/v1/knowledge-bases/{dataset_id}/documents")
        assert response.status_code == 200
        current = next(item for item in response.json() if item["id"] == document_id)
        if current["parsing_status"] == "completed":
            return
        if current["parsing_status"] == "failed":
            pytest.fail(f"W5-04 真实文档解析失败: {current['error_code']}")
        sleep(2)
    pytest.fail("W5-04 真实文档解析超时")


def _terminal(client: httpx.Client, run_id: str) -> dict[str, object]:
    deadline = monotonic() + 300
    while monotonic() < deadline:
        response = client.get(f"/api/v1/workflow-runs/{run_id}")
        assert response.status_code == 200
        run = cast(dict[str, object], response.json())
        if run["status"] in {"completed", "failed", "stopped"}:
            return run
        sleep(0.1)
    pytest.fail("W5-04 工作流运行未进入终态")


def _events(client: httpx.Client, run_id: str, terminal_type: str) -> list[str]:
    types: list[str] = []
    with client.stream("GET", f"/api/v1/workflow-runs/{run_id}/events") as response:
        assert response.status_code == 200
        for line in response.iter_lines():
            if line.startswith("event: "):
                event_type = line.removeprefix("event: ")
                types.append(event_type)
                if event_type == terminal_type:
                    break
            if line.startswith("data: "):
                event = json.loads(line.removeprefix("data: "))
                assert event["schema_version"] == "1"
                assert event["run_id"] == run_id
                assert event["run"]["id"] == run_id
    return types
