from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx

from tests.support.employees import delete_employees_from_database_url
from tests.support.http import assert_error_response, running_api
from tests.support.settings import TEST_DATABASE_URL


def _body(*, knowledge_base_id: str | None = None) -> dict[str, str | None]:
    return {
        "name": "通用助理",
        "description": "与具体业务无关",
        "system_prompt": "根据用户问题提供帮助。",
        "knowledge_base_id": knowledge_base_id,
    }


def test_employee_crud_uses_formal_uvicorn_mysql_and_survives_restart() -> None:
    employee_id: str | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            httpx.Client(base_url=api_url, timeout=5) as client,
        ):
            created = client.post("/api/v1/employees", json=_body())
            assert created.status_code == 201
            payload = created.json()
            employee_id = str(payload["id"])
            UUID(employee_id)
            assert payload["allowed_workflow_ids"] == []
            assert payload["knowledge_base_id"] is None

            listed = client.get("/api/v1/employees")
            detailed = client.get(f"/api/v1/employees/{employee_id}")
            updated = client.put(
                f"/api/v1/employees/{employee_id}",
                json={**_body(), "name": "更新后的通用助理"},
            )

            assert listed.status_code == 200
            assert employee_id in {item["id"] for item in listed.json()}
            assert detailed.status_code == 200
            assert detailed.json()["system_prompt"] == "根据用户问题提供帮助。"
            assert updated.status_code == 200
            assert updated.json()["name"] == "更新后的通用助理"

        with (
            running_api(TEST_DATABASE_URL) as restarted_url,
            httpx.Client(base_url=restarted_url, timeout=5) as restarted_client,
        ):
            restored = restarted_client.get(f"/api/v1/employees/{employee_id}")
            assert restored.status_code == 200
            assert restored.json()["name"] == "更新后的通用助理"
    finally:
        if employee_id is not None:
            asyncio.run(delete_employees_from_database_url(TEST_DATABASE_URL, employee_id))


def test_employee_validation_and_missing_resources_use_stable_errors() -> None:
    with (
        running_api(TEST_DATABASE_URL) as api_url,
        httpx.Client(base_url=api_url, timeout=5) as client,
    ):
        blank_name = client.post("/api/v1/employees", json={**_body(), "name": "   "})
        forbidden_workflow = client.post(
            "/api/v1/employees",
            json={**_body(), "allowed_workflow_ids": [str(uuid4())]},
        )
        invalid_id = client.get("/api/v1/employees/not-a-uuid")
        missing = client.get(f"/api/v1/employees/{uuid4()}")
        missing_update = client.put(
            f"/api/v1/employees/{uuid4()}",
            json=_body(knowledge_base_id="kb-1"),
        )

    assert_error_response(blank_name, status=422, code="validation_error")
    assert_error_response(forbidden_workflow, status=422, code="validation_error")
    assert_error_response(invalid_id, status=422, code="validation_error")
    assert_error_response(missing, status=404, code="employee_not_found")
    assert_error_response(missing_update, status=404, code="employee_not_found")


def test_binding_without_knowledge_configuration_fails_closed_without_write() -> None:
    name = f"missing-config-{uuid4().hex}"
    with (
        running_api(TEST_DATABASE_URL) as api_url,
        httpx.Client(base_url=api_url, timeout=5) as client,
    ):
        rejected = client.post(
            "/api/v1/employees",
            json={**_body(knowledge_base_id="kb-1"), "name": name},
        )
        listed = client.get("/api/v1/employees")

    assert_error_response(rejected, status=503, code="configuration_missing")
    assert name not in {item["name"] for item in listed.json()}


def test_binding_when_knowledge_service_is_unavailable_fails_closed_without_write() -> None:
    name = f"unavailable-{uuid4().hex}"
    with (
        running_api(
            TEST_DATABASE_URL,
            env_overrides={
                "RAGFLOW_BASE_URL": "http://127.0.0.1:1",
                "RAGFLOW_API_KEY": "safe-test-key",
                "RAGFLOW_EXPECTED_VERSION": "v0.25.6",
                "RAGFLOW_TIMEOUT_SECONDS": "0.2",
            },
        ) as api_url,
        httpx.Client(base_url=api_url, timeout=5) as client,
    ):
        rejected = client.post(
            "/api/v1/employees",
            json={**_body(knowledge_base_id="kb-1"), "name": name},
        )
        listed = client.get("/api/v1/employees")

    assert_error_response(rejected, status=503, code="knowledge_service_unavailable")
    assert rejected.json()["retryable"] is True
    assert name not in {item["name"] for item in listed.json()}
