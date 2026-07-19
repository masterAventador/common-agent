from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx

from tests.support.http import assert_error_response, running_api
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows_from_database_url


def _body(*, include_end: bool = True, knowledge_base_id: str | None = None) -> dict[str, object]:
    processing: dict[str, object] = (
        {
            "id": "retrieve",
            "type": "knowledge_retrieval",
            "position": {"x": 240, "y": 40},
            "config": {"knowledge_base_id": knowledge_base_id},
        }
        if knowledge_base_id is not None
        else {
            "id": "chat",
            "type": "ai_chat",
            "position": {"x": 240, "y": 40},
            "config": {"prompt": "根据工作流输入回答"},
        }
    )
    nodes: list[dict[str, object]] = [
        {
            "id": "start",
            "type": "start",
            "position": {"x": 0, "y": 40},
            "config": {},
        },
        processing,
    ]
    edges: list[dict[str, object]] = [
        {"id": "edge-1", "source": "start", "target": processing["id"]}
    ]
    if include_end:
        nodes.append(
            {
                "id": "end",
                "type": "end",
                "position": {"x": 480, "y": 40},
                "config": {},
            }
        )
        edges.append({"id": "edge-2", "source": processing["id"], "target": "end"})
    return {
        "name": "通用工作流",
        "description": "正式 API 验收",
        "nodes": nodes,
        "edges": edges,
    }


def test_workflow_crud_uses_formal_uvicorn_mysql_and_survives_restart() -> None:
    workflow_id: str | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            httpx.Client(base_url=api_url, timeout=5) as client,
        ):
            created = client.post("/api/v1/workflows", json=_body())
            assert created.status_code == 201
            payload = created.json()
            workflow_id = str(payload["id"])
            UUID(workflow_id)
            assert payload["nodes"][0]["position"] == {"x": 0.0, "y": 40.0}
            assert payload["nodes"][1]["config"] == {"prompt": "根据工作流输入回答"}

            listed = client.get("/api/v1/workflows")
            detailed = client.get(f"/api/v1/workflows/{workflow_id}")
            updated_body = _body()
            updated_body["name"] = "更新后的工作流"
            updated = client.put(f"/api/v1/workflows/{workflow_id}", json=updated_body)

            assert listed.status_code == 200
            assert workflow_id in {item["id"] for item in listed.json()}
            assert detailed.status_code == 200
            assert detailed.json()["description"] == "正式 API 验收"
            assert updated.status_code == 200
            assert updated.json()["name"] == "更新后的工作流"

        with (
            running_api(TEST_DATABASE_URL) as restarted_url,
            httpx.Client(base_url=restarted_url, timeout=5) as restarted_client,
        ):
            restored = restarted_client.get(f"/api/v1/workflows/{workflow_id}")
            assert restored.status_code == 200
            assert restored.json()["name"] == "更新后的工作流"
    finally:
        if workflow_id is not None:
            asyncio.run(delete_workflows_from_database_url(TEST_DATABASE_URL, workflow_id))


def test_workflow_validate_returns_complete_graph_issues_without_writing() -> None:
    with (
        running_api(TEST_DATABASE_URL) as api_url,
        httpx.Client(base_url=api_url, timeout=5) as client,
    ):
        valid = client.post("/api/v1/workflows/validate", json=_body())
        invalid = client.post(
            "/api/v1/workflows/validate",
            json=_body(include_end=False),
        )
        listed = client.get("/api/v1/workflows")

    assert valid.status_code == 200
    assert valid.json() == {"valid": True, "issues": []}
    assert invalid.status_code == 200
    assert invalid.json()["valid"] is False
    assert "missing_end" in {issue["code"] for issue in invalid.json()["issues"]}
    assert not any(item["name"] == "通用工作流" for item in listed.json())


def test_workflow_schema_and_missing_resources_use_stable_errors() -> None:
    invalid_type = _body()
    invalid_type["nodes"][1]["type"] = "script"  # type: ignore[index]
    wrong_config = _body()
    wrong_config["nodes"][1]["config"] = {"knowledge_base_id": "kb"}  # type: ignore[index]
    extra_config = _body()
    extra_config["nodes"][0]["config"] = {"unexpected": True}  # type: ignore[index]

    with (
        running_api(TEST_DATABASE_URL) as api_url,
        httpx.Client(base_url=api_url, timeout=5) as client,
    ):
        responses = (
            client.post("/api/v1/workflows", json=invalid_type),
            client.post("/api/v1/workflows", json=wrong_config),
            client.post("/api/v1/workflows", json=extra_config),
            client.get("/api/v1/workflows/not-a-uuid"),
        )
        missing = client.get(f"/api/v1/workflows/{uuid4()}")
        missing_update = client.put(f"/api/v1/workflows/{uuid4()}", json=_body())

    for response in responses:
        assert_error_response(response, status=422, code="validation_error")
    assert_error_response(missing, status=404, code="workflow_not_found")
    assert_error_response(missing_update, status=404, code="workflow_not_found")


def test_invalid_graph_and_missing_knowledge_configuration_fail_without_write() -> None:
    invalid_name = f"invalid-{uuid4().hex}"
    invalid_graph = _body(include_end=False)
    invalid_graph["name"] = invalid_name
    knowledge_name = f"knowledge-{uuid4().hex}"
    knowledge_graph = _body(knowledge_base_id="kb-1")
    knowledge_graph["name"] = knowledge_name

    with (
        running_api(TEST_DATABASE_URL) as api_url,
        httpx.Client(base_url=api_url, timeout=5) as client,
    ):
        rejected_graph = client.post("/api/v1/workflows", json=invalid_graph)
        rejected_knowledge = client.post("/api/v1/workflows", json=knowledge_graph)
        listed = client.get("/api/v1/workflows")

    assert_error_response(rejected_graph, status=422, code="workflow_invalid")
    assert_error_response(rejected_knowledge, status=503, code="configuration_missing")
    assert {invalid_name, knowledge_name}.isdisjoint({item["name"] for item in listed.json()})
