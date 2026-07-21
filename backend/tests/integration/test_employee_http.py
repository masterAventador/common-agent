from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from tests.support.employees import (
    DEFAULT_TEST_MODEL_CONFIGURATION_ID,
    delete_employees_from_database_url,
)
from tests.support.http import assert_error_response, authenticated_client, running_api
from tests.support.model_configuration_e2e_state import (
    delete_model_configurations_named_from_database_url,
)
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows_from_database_url


def _body(
    *,
    knowledge_base_id: str | None = None,
    allowed_workflow_ids: list[str] | None = None,
    default_model_configuration_id: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {
        "name": "通用助理",
        "description": "与具体业务无关",
        "system_prompt": "根据用户问题提供帮助。",
        "knowledge_base_id": knowledge_base_id,
        "allowed_workflow_ids": allowed_workflow_ids or [],
    }
    body["default_model_configuration_id"] = default_model_configuration_id or str(
        DEFAULT_TEST_MODEL_CONFIGURATION_ID
    )
    return body


def test_employee_persists_an_enabled_tenant_model_reference_through_formal_api() -> None:
    employee_id: str | None = None
    model_configuration_id: str | None = None
    model_name = f"员工默认模型-{uuid4().hex}"
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            configured = client.post(
                "/api/v1/model-configurations",
                json={
                    "display_name": model_name,
                    "model_identifier": "qwen-turbo",
                    "enabled": True,
                },
            )
            assert configured.status_code == 201
            model_configuration_id = configured.json()["id"]

            created = client.post(
                "/api/v1/employees",
                json=_body(default_model_configuration_id=model_configuration_id),
            )
            assert created.status_code == 201
            employee_id = created.json()["id"]
            assert created.json()["default_model_configuration_id"] == model_configuration_id
            assert created.json()["default_model_identifier"] == "qwen-turbo"

            restored = client.get(f"/api/v1/employees/{employee_id}")
            assert restored.status_code == 200
            assert restored.json()["default_model_configuration_id"] == model_configuration_id

            assert client.delete(f"/api/v1/employees/{employee_id}").status_code == 204
            employee_id = None
            assert (
                client.delete(f"/api/v1/model-configurations/{model_configuration_id}").status_code
                == 204
            )
            model_configuration_id = None
    finally:
        if employee_id is not None:
            asyncio.run(delete_employees_from_database_url(TEST_DATABASE_URL, employee_id))
        asyncio.run(
            delete_model_configurations_named_from_database_url(
                TEST_DATABASE_URL,
                model_name,
            )
        )

    assert employee_id is None
    assert model_configuration_id is None


def test_disabled_employee_model_preserves_existing_binding_and_blocks_new_selection() -> None:
    employee_id: str | None = None
    model_name = f"停用员工模型-{uuid4().hex}"
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            configured = client.post(
                "/api/v1/model-configurations",
                json={
                    "display_name": model_name,
                    "model_identifier": "qwen-turbo",
                    "enabled": True,
                },
            )
            assert configured.status_code == 201
            model_configuration_id = configured.json()["id"]
            created = client.post(
                "/api/v1/employees",
                json=_body(default_model_configuration_id=model_configuration_id),
            )
            assert created.status_code == 201
            employee_id = created.json()["id"]

            disabled = client.put(
                f"/api/v1/model-configurations/{model_configuration_id}",
                json={
                    "display_name": model_name,
                    "model_identifier": "qwen-turbo",
                    "enabled": False,
                },
            )
            assert disabled.status_code == 200

            preserved = client.put(
                f"/api/v1/employees/{employee_id}",
                json={
                    **_body(default_model_configuration_id=model_configuration_id),
                    "description": "停用后仍可保留现有绑定",
                },
            )
            assert preserved.status_code == 200
            assert preserved.json()["description"] == "停用后仍可保留现有绑定"

            rejected = client.post(
                "/api/v1/employees",
                json={
                    **_body(default_model_configuration_id=model_configuration_id),
                    "name": "不能新选停用模型",
                },
            )
            assert_error_response(rejected, status=409, code="employee_model_disabled")
            blocked_delete = client.delete(f"/api/v1/model-configurations/{model_configuration_id}")
            assert_error_response(
                blocked_delete,
                status=409,
                code="model_configuration_in_use",
            )

            assert client.delete(f"/api/v1/employees/{employee_id}").status_code == 204
            employee_id = None
            assert (
                client.delete(f"/api/v1/model-configurations/{model_configuration_id}").status_code
                == 204
            )
    finally:
        if employee_id is not None:
            asyncio.run(delete_employees_from_database_url(TEST_DATABASE_URL, employee_id))
        asyncio.run(
            delete_model_configurations_named_from_database_url(
                TEST_DATABASE_URL,
                model_name,
            )
        )


def _workflow_body() -> dict[str, object]:
    return {
        "name": f"员工授权工作流-{uuid4().hex}",
        "description": "员工 API allowlist 验收",
        "nodes": [
            {"id": "start", "type": "start", "position": {"x": 0, "y": 0}, "config": {}},
            {"id": "end", "type": "end", "position": {"x": 240, "y": 0}, "config": {}},
        ],
        "edges": [{"id": "edge", "source": "start", "target": "end"}],
    }


def test_employee_crud_uses_formal_uvicorn_mysql_and_survives_restart() -> None:
    employee_id: str | None = None
    workflow_id: str | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            workflow = client.post("/api/v1/workflows", json=_workflow_body())
            assert workflow.status_code == 201
            workflow_id = workflow.json()["id"]
            created = client.post(
                "/api/v1/employees",
                json=_body(allowed_workflow_ids=[workflow_id]),
            )
            assert created.status_code == 201
            payload = created.json()
            employee_id = str(payload["id"])
            UUID(employee_id)
            assert payload["allowed_workflow_ids"] == [workflow_id]
            assert payload["knowledge_base_id"] is None

            listed = client.get("/api/v1/employees")
            detailed = client.get(f"/api/v1/employees/{employee_id}")
            updated = client.put(
                f"/api/v1/employees/{employee_id}",
                json={
                    **_body(allowed_workflow_ids=[workflow_id]),
                    "name": "更新后的通用助理",
                },
            )

            assert listed.status_code == 200
            assert employee_id in {item["id"] for item in listed.json()["items"]}
            assert detailed.status_code == 200
            assert detailed.json()["system_prompt"] == "根据用户问题提供帮助。"
            assert updated.status_code == 200
            assert updated.json()["name"] == "更新后的通用助理"

        with (
            running_api(TEST_DATABASE_URL) as restarted_url,
            authenticated_client(base_url=restarted_url, timeout=5) as restarted_client,
        ):
            restored = restarted_client.get(f"/api/v1/employees/{employee_id}")
            assert restored.status_code == 200
            assert restored.json()["name"] == "更新后的通用助理"
            assert restored.json()["allowed_workflow_ids"] == [workflow_id]
    finally:
        if employee_id is not None:
            asyncio.run(delete_employees_from_database_url(TEST_DATABASE_URL, employee_id))
        if workflow_id is not None:
            asyncio.run(delete_workflows_from_database_url(TEST_DATABASE_URL, workflow_id))


def test_employee_http_cursor_is_stable_across_concurrent_insert_and_anchor_delete() -> None:
    token = f"page-{uuid4().hex}"
    employee_ids: list[str] = []
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            for index in range(4):
                created = client.post(
                    "/api/v1/employees",
                    json={**_body(), "name": f"{token}-{index}"},
                )
                assert created.status_code == 201
                employee_ids.append(created.json()["id"])

            first = client.get(
                "/api/v1/employees",
                params={"search": token, "limit": 2},
            )
            assert first.status_code == 200
            first_payload = first.json()
            first_ids = [item["id"] for item in first_payload["items"]]
            assert first_ids == employee_ids[3:1:-1]
            assert isinstance(first_payload["next_cursor"], str)

            anchor_id = first_ids[-1]
            assert client.delete(f"/api/v1/employees/{anchor_id}").status_code == 204

            newer = client.post(
                "/api/v1/employees",
                json={**_body(), "name": f"{token}-newer"},
            )
            assert newer.status_code == 201
            newer_id = newer.json()["id"]
            employee_ids.append(newer_id)

            second = client.get(
                "/api/v1/employees",
                params={
                    "search": token,
                    "limit": 2,
                    "cursor": first_payload["next_cursor"],
                },
            )
            assert second.status_code == 200
            second_payload = second.json()
            second_ids = [item["id"] for item in second_payload["items"]]
            assert second_ids == employee_ids[1::-1]
            assert second_payload["next_cursor"] is None
            assert len(set(first_ids + second_ids)) == 4
            assert newer_id not in first_ids + second_ids

            mismatched = client.get(
                "/api/v1/employees",
                params={
                    "search": f"{token}-changed",
                    "limit": 2,
                    "cursor": first_payload["next_cursor"],
                },
            )
            assert_error_response(
                mismatched,
                status=422,
                code="invalid_page_cursor",
            )
    finally:
        for employee_id in employee_ids:
            asyncio.run(delete_employees_from_database_url(TEST_DATABASE_URL, employee_id))


def test_employee_validation_and_missing_resources_use_stable_errors() -> None:
    with (
        running_api(TEST_DATABASE_URL) as api_url,
        authenticated_client(base_url=api_url, timeout=5) as client,
    ):
        blank_name = client.post("/api/v1/employees", json={**_body(), "name": "   "})
        missing_workflow = client.post(
            "/api/v1/employees",
            json={**_body(), "allowed_workflow_ids": [str(uuid4())]},
        )
        duplicate_workflow = client.post(
            "/api/v1/employees",
            json={**_body(), "allowed_workflow_ids": [str(uuid4())] * 2},
        )
        invalid_id = client.get("/api/v1/employees/not-a-uuid")
        missing = client.get(f"/api/v1/employees/{uuid4()}")
        missing_update = client.put(
            f"/api/v1/employees/{uuid4()}",
            json=_body(knowledge_base_id="kb-1"),
        )

    assert_error_response(blank_name, status=422, code="validation_error")
    assert_error_response(missing_workflow, status=404, code="workflow_not_found")
    assert_error_response(duplicate_workflow, status=422, code="validation_error")
    assert_error_response(invalid_id, status=422, code="validation_error")
    assert_error_response(missing, status=404, code="employee_not_found")
    assert_error_response(missing_update, status=404, code="employee_not_found")


def test_binding_without_knowledge_configuration_fails_closed_without_write() -> None:
    name = f"missing-config-{uuid4().hex}"
    with (
        running_api(TEST_DATABASE_URL) as api_url,
        authenticated_client(base_url=api_url, timeout=5) as client,
    ):
        rejected = client.post(
            "/api/v1/employees",
            json={**_body(knowledge_base_id="kb-1"), "name": name},
        )
        listed = client.get("/api/v1/employees")

    assert_error_response(rejected, status=503, code="configuration_missing")
    assert name not in {item["name"] for item in listed.json()["items"]}


def test_binding_when_knowledge_service_is_unavailable_fails_closed_without_write() -> None:
    name = f"unavailable-{uuid4().hex}"
    with (
        running_api(
            TEST_DATABASE_URL,
            env_overrides={
                "RAGFLOW_BASE_URL": "http://127.0.0.1:1",
                "RAGFLOW_API_KEY": "safe-test-key",
                "RAGFLOW_EXPECTED_VERSION": "v0.26.4",
                "RAGFLOW_TIMEOUT_SECONDS": "0.2",
            },
        ) as api_url,
        authenticated_client(base_url=api_url, timeout=5) as client,
    ):
        rejected = client.post(
            "/api/v1/employees",
            json={**_body(knowledge_base_id="kb-1"), "name": name},
        )
        listed = client.get("/api/v1/employees")

    assert_error_response(rejected, status=503, code="knowledge_service_unavailable")
    assert rejected.json()["retryable"] is True
    assert name not in {item["name"] for item in listed.json()["items"]}
