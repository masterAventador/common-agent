from __future__ import annotations

import asyncio
import json
import os
from time import monotonic, sleep
from typing import cast
from uuid import uuid4

import httpx
import pytest

from common_agent.model_configurations.defaults import platform_default_model_configuration_id
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.employees import delete_employees_from_database_url
from tests.support.http import authenticated_client, running_api
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
    employee_target_workflow_id: str | None = None
    employee_id: str | None = None
    completed_run_id = str(uuid4())
    stopped_run_id = str(uuid4())
    failed_run_id = str(uuid4())
    marker = f"COMMON_AGENT_W5_04_{uuid4().hex}"
    try:
        with (
            running_api(TEST_DATABASE_URL, env_overrides=environment) as api_url,
            authenticated_client(base_url=api_url, timeout=180) as client,
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
            assert accepted.json()["status"] == "pending"
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

            employee_marker = f"COMMON_AGENT_S10_07I_EMPLOYEE_{uuid4().hex}"
            created_employee = client.post(
                "/api/v1/employees",
                json=_employee_body(),
            )
            assert created_employee.status_code == 201
            employee_id = str(created_employee.json()["id"])
            employee_workflow = client.post(
                "/api/v1/workflows",
                json=_employee_target_workflow_body(employee_id),
            )
            assert employee_workflow.status_code == 201
            employee_target_workflow_id = str(employee_workflow.json()["id"])
            employee_run_id = str(uuid4())
            employee_accepted = client.post(
                f"/api/v1/workflows/{employee_target_workflow_id}/runs",
                json={
                    "run_id": employee_run_id,
                    "input": f"只输出唯一标记 {employee_marker}",
                },
            )
            assert employee_accepted.status_code == 202
            employee_completed = _terminal(client, employee_run_id)
            assert employee_completed["status"] == "completed"
            assert employee_marker in str(employee_completed["output"])
            assert employee_completed["ai_targets"] == [
                {
                    "node_id": "chat",
                    "target_type": "employee",
                    "target_id": employee_id,
                    "target_name": "S10-07I 真实节点员工",
                    "model_configuration_id": str(
                        platform_default_model_configuration_id(DEFAULT_TENANT_ID)
                    ),
                    "model_identifier": "qwen-plus",
                }
            ]
            assert _events(client, employee_run_id, "workflow.run.completed")[-1] == (
                "workflow.run.completed"
            )

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
            authenticated_client(base_url=restarted_url, timeout=180) as restarted,
        ):
            restored = restarted.get(f"/api/v1/workflow-runs/{completed_run_id}")
            assert restored.status_code == 200
            assert restored.json()["status"] == "completed"
            assert marker in restored.json()["output"]
    finally:
        if employee_target_workflow_id is not None:
            asyncio.run(
                delete_workflows_from_database_url(
                    TEST_DATABASE_URL,
                    employee_target_workflow_id,
                )
            )
        if workflow_id is not None:
            asyncio.run(delete_workflows_from_database_url(TEST_DATABASE_URL, workflow_id))
        if employee_id is not None:
            asyncio.run(delete_employees_from_database_url(TEST_DATABASE_URL, employee_id))
        if dataset_id is not None:
            asyncio.run(delete_dataset(base_url, api_key, dataset_id))


def _workflow_body(knowledge_base_id: str) -> dict[str, object]:
    model_configuration_id = str(platform_default_model_configuration_id(DEFAULT_TENANT_ID))
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
                "config": {
                    "prompt": "根据检索内容回答,只输出唯一验收标记,不要添加其他文字。",
                    "target": {
                        "type": "model",
                        "model_configuration_id": model_configuration_id,
                    },
                },
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


def _employee_body() -> dict[str, object]:
    return {
        "name": "S10-07I 真实节点员工",
        "description": "验证工作流 AI 对话节点继承数字员工运行配置",
        "system_prompt": "只输出用户要求的唯一验收标记,不添加解释。",
        "default_model_configuration_id": str(
            platform_default_model_configuration_id(DEFAULT_TENANT_ID)
        ),
        "knowledge_base_id": None,
        "allowed_workflow_ids": [],
    }


def _employee_target_workflow_body(employee_id: str) -> dict[str, object]:
    return {
        "name": f"common-agent-s10-07i-employee-{uuid4().hex}",
        "description": "S10-07I 正式 Deep Agents 节点验收",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {
                "id": "chat",
                "type": "ai_chat",
                "position": {"x": 240, "y": 0},
                "config": {
                    "prompt": "遵守数字员工指令,只输出用户要求的唯一标记。",
                    "target": {"type": "employee", "employee_id": employee_id},
                },
            },
            {"id": "end", "type": "end", "position": {"x": 480, "y": 0}, "config": {}},
        ],
        "edges": [
            {"id": "edge-start-chat", "source": "start", "target": "chat"},
            {"id": "edge-chat-end", "source": "chat", "target": "end"},
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
