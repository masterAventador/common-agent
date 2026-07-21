from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, text

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import AuthUserRow
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.employees import (
    DEFAULT_TEST_MODEL_CONFIGURATION_ID,
    delete_employees,
)
from tests.support.http import (
    TEST_FRONTEND_ORIGIN,
    assert_error_response,
    authenticated_client,
    running_api,
)
from tests.support.settings import TEST_DATABASE_URL

_DEMO_ENV = {"COMMON_AGENT_INTEGRATION_MODE": "demo"}


def test_audit_http_records_mutation_and_permission_denial_without_payloads() -> None:
    employee_id: UUID | None = None
    viewer_email = f"audit-viewer-{uuid4().hex}@example.com"
    viewer_password = "audit viewer password is long enough"
    try:
        with (
            running_api(TEST_DATABASE_URL, env_overrides=_DEMO_ENV) as api_url,
            authenticated_client(base_url=api_url, timeout=15) as owner,
        ):
            created = owner.post(
                "/api/v1/employees",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                json={
                    "name": f"审计员工-{uuid4().hex}",
                    "description": "审计链路测试",
                    "system_prompt": "绝不记录请求正文。",
                    "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                    "knowledge_base_id": None,
                    "allowed_workflow_ids": [],
                },
            )
            assert created.status_code == 201
            employee_id = UUID(created.json()["id"])

            provisioned = owner.post(
                f"/api/v1/tenants/{DEFAULT_TENANT_ID}/members",
                json={
                    "email": viewer_email,
                    "password": viewer_password,
                    "role": "viewer",
                },
            )
            assert provisioned.status_code == 201
            viewer_id = UUID(provisioned.json()["user_id"])
            recovery_code = str(provisioned.json()["recovery_codes"][0])
            with _member_client(api_url, viewer_email, viewer_password) as viewer:
                denied = viewer.get(
                    "/api/v1/audit-events",
                    headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                )
                assert_error_response(denied, status=403, code="tenant_admin_forbidden")

            replacement_password = "replacement audit password is long enough"
            recovered = owner.post(
                "/api/v1/auth/recovery/reset",
                json={
                    "email": viewer_email,
                    "recovery_code": recovery_code,
                    "new_password": replacement_password,
                },
            )
            assert recovered.status_code == 204

            events = owner.get(
                "/api/v1/audit-events",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                params={"resource_type": "employee", "resource_id": str(employee_id)},
            )
            assert events.status_code == 200
            payload = events.json()
            assert payload["items"][0]["action"] == "employee.created"
            assert payload["items"][0]["outcome"] == "succeeded"
            assert payload["items"][0]["resource_id"] == str(employee_id)
            assert set(payload["items"][0]) == {
                "sequence",
                "event_id",
                "tenant_id",
                "actor_user_id",
                "action",
                "outcome",
                "request_id",
                "trace_id",
                "resource_type",
                "resource_id",
                "error_code",
                "occurred_at",
                "retention_until",
                "previous_hash",
                "event_hash",
            }
            serialized = str(payload)
            assert "绝不记录请求正文" not in serialized
            assert viewer_password not in serialized

            denied_events = owner.get(
                "/api/v1/audit-events",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                params={
                    "actor_user_id": str(viewer_id),
                    "action": "security.permission.denied",
                },
            )
            assert denied_events.status_code == 200
            assert denied_events.json()["items"][0]["error_code"] == "tenant_admin_forbidden"

            credential_events = owner.get(
                "/api/v1/audit-events",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                params={"scope": "platform", "action": "auth.recovery.reset"},
            )
            assert credential_events.status_code == 200
            credential_payload = credential_events.json()
            assert credential_payload["items"][0]["action"] == "auth.recovery.reset"
            assert credential_payload["items"][0]["outcome"] == "succeeded"
            serialized_credentials = str(credential_payload)
            assert recovery_code not in serialized_credentials
            assert replacement_password not in serialized_credentials

            platform_integrity = owner.get(
                "/api/v1/audit-events/integrity",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                params={"scope": "platform"},
            )
            assert platform_integrity.status_code == 200
            assert platform_integrity.json()["verified"] is True
            assert platform_integrity.json()["event_count"] >= 2

            integrity = owner.get(
                "/api/v1/audit-events/integrity",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
            )
            assert integrity.status_code == 200
            assert integrity.json()["verified"] is True
            assert integrity.json()["event_count"] >= 3

            policy = owner.get(
                "/api/v1/audit-events/policy",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
            )
            assert policy.status_code == 200
            assert policy.json() == {
                "retention_days": 365,
                "max_events_per_scope": 1_000_000,
                "automatic_deletion": False,
            }
    finally:
        asyncio.run(_cleanup(employee_id=employee_id, viewer_email=viewer_email))


def test_audit_storage_failure_blocks_mutation_before_the_formal_handler() -> None:
    trigger_name = f"trg_test_audit_reject_{uuid4().hex}"
    employee_name = f"审计关闭失败-{uuid4().hex}"
    with (
        running_api(TEST_DATABASE_URL, env_overrides=_DEMO_ENV) as api_url,
        authenticated_client(base_url=api_url, timeout=15) as owner,
    ):
        asyncio.run(_create_rejecting_audit_trigger(trigger_name))
        try:
            rejected = owner.post(
                "/api/v1/employees",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                json={
                    "name": employee_name,
                    "description": "审计不可用时不得落业务数据",
                    "system_prompt": "只用于真实失败注入验收。",
                    "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                    "knowledge_base_id": None,
                    "allowed_workflow_ids": [],
                },
            )
            assert_error_response(rejected, status=503, code="audit_unavailable")
        finally:
            asyncio.run(_drop_trigger(trigger_name))

        listed = owner.get(
            "/api/v1/employees",
            headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
            params={"search": employee_name},
        )
        assert listed.status_code == 200
        assert listed.json()["items"] == []


def _member_client(base_url: str, email: str, password: str) -> httpx.Client:
    login_client = httpx.Client(base_url=base_url, timeout=15)
    authenticated = login_client.post(
        "/api/v1/auth/login",
        headers={"Origin": TEST_FRONTEND_ORIGIN},
        json={"email": email, "password": password},
    )
    authenticated.raise_for_status()
    csrf_token = str(authenticated.json()["csrf_token"])

    def authorize(request: httpx.Request) -> None:
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            request.headers.setdefault("Origin", TEST_FRONTEND_ORIGIN)
            request.headers.setdefault("X-CSRF-Token", csrf_token)

    return httpx.Client(
        base_url=base_url,
        timeout=15,
        cookies=httpx.Cookies(login_client.cookies),
        event_hooks={"request": [authorize]},
    )


async def _cleanup(*, employee_id: UUID | None, viewer_email: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        if employee_id is not None:
            await delete_employees(database, employee_id)
        async with database.session() as session:
            await session.execute(delete(AuthUserRow).where(AuthUserRow.email == viewer_email))
            await session.commit()
    finally:
        await database.stop()


async def _create_rejecting_audit_trigger(trigger_name: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                text(
                    f"CREATE TRIGGER {trigger_name} BEFORE INSERT ON audit_events "
                    "FOR EACH ROW SIGNAL SQLSTATE '45000' "
                    "SET MESSAGE_TEXT = 'injected audit failure'"
                )
            )
            await session.commit()
    finally:
        await database.stop()


async def _drop_trigger(trigger_name: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(text(f"DROP TRIGGER IF EXISTS {trigger_name}"))
            await session.commit()
    finally:
        await database.stop()
