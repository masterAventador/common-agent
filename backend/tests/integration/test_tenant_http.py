from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx
from sqlalchemy import delete, update

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    AuthUserRow,
    ConversationRow,
    TenantMembershipRow,
    TenantRow,
)
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


def test_tenant_http_isolates_rest_sse_and_viewer_writes() -> None:
    tenant_b: UUID | None = None
    employee_a: UUID | None = None
    member_email = f"viewer-{uuid4().hex}@example.com"
    member_password = "Viewer#8"
    try:
        with (
            running_api(TEST_DATABASE_URL, env_overrides=_DEMO_ENV) as api_url,
            authenticated_client(base_url=api_url, timeout=15) as client,
        ):
            accesses = client.get("/api/v1/tenants")
            assert accesses.status_code == 200
            default = next(item for item in accesses.json() if item["id"] == str(DEFAULT_TENANT_ID))

            provisioned = client.post(
                f"/api/v1/tenants/{DEFAULT_TENANT_ID}/members",
                json={
                    "email": member_email,
                    "password": member_password,
                    "role": "viewer",
                },
            )
            assert provisioned.status_code == 201
            assert provisioned.json()["role"] == "viewer"
            assert len(provisioned.json()["recovery_codes"]) == 8

            duplicate = client.post(
                f"/api/v1/tenants/{DEFAULT_TENANT_ID}/members",
                json={
                    "email": member_email,
                    "password": member_password,
                    "role": "editor",
                },
            )
            assert_error_response(duplicate, status=409, code="member_conflict")

            owner_member = client.post(
                f"/api/v1/tenants/{DEFAULT_TENANT_ID}/members",
                json={
                    "email": f"owner-member-{uuid4().hex}@example.com",
                    "password": member_password,
                    "role": "owner",
                },
            )
            assert_error_response(owner_member, status=422, code="validation_error")

            with _member_client(api_url, member_email, member_password) as viewer:
                viewer_accesses = viewer.get("/api/v1/tenants")
                assert viewer_accesses.status_code == 200
                assert viewer_accesses.json() == [
                    {
                        **default,
                        "role": "viewer",
                    }
                ]
                forbidden_admin = viewer.post(
                    f"/api/v1/tenants/{DEFAULT_TENANT_ID}/members",
                    json={
                        "email": f"blocked-{uuid4().hex}@example.com",
                        "password": "blocked member password is long enough",
                        "role": "editor",
                    },
                )
                assert_error_response(
                    forbidden_admin,
                    status=403,
                    code="tenant_admin_forbidden",
                )

            created_tenant = client.post(
                "/api/v1/tenants",
                json={
                    "organization_id": default["organization_id"],
                    "name": f"隔离工作区-{uuid4().hex}",
                },
            )
            assert created_tenant.status_code == 201
            tenant_b = UUID(created_tenant.json()["id"])

            ambiguous = client.get("/api/v1/employees")
            assert_error_response(
                ambiguous,
                status=409,
                code="tenant_selection_required",
            )

            created_employee = client.post(
                "/api/v1/employees",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                json={
                    "name": f"租户 A 员工-{uuid4().hex}",
                    "description": "跨租户关闭失败测试",
                    "system_prompt": "只处理当前工作区数据。",
                    "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                    "knowledge_base_id": None,
                    "allowed_workflow_ids": [],
                },
            )
            assert created_employee.status_code == 201
            employee_a = UUID(created_employee.json()["id"])

            hidden = client.get(
                f"/api/v1/employees/{employee_a}",
                headers={"X-Tenant-ID": str(tenant_b)},
            )
            assert_error_response(hidden, status=404, code="employee_not_found")

            conversation_id = uuid4()
            conversation = client.post(
                "/api/v1/conversations",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                json={
                    "conversation_id": str(conversation_id),
                    "employee_id": str(employee_a),
                    "title": "租户 A 会话",
                },
            )
            assert conversation.status_code == 201

            cross_tenant_sse = client.get(
                f"/api/v1/conversations/{conversation_id}/events",
                params={"tenant_id": str(tenant_b)},
            )
            assert_error_response(
                cross_tenant_sse,
                status=404,
                code="conversation_not_found",
            )

            denied = client.get(
                "/api/v1/employees",
                headers={"X-Tenant-ID": str(uuid4())},
            )
            assert_error_response(denied, status=403, code="tenant_access_denied")

            asyncio.run(_set_role(tenant_b, "viewer"))
            viewer_write = client.post(
                "/api/v1/employees",
                headers={"X-Tenant-ID": str(tenant_b)},
                json={
                    "name": "Viewer 不可创建",
                    "description": "",
                    "system_prompt": "必须被 RBAC 拒绝。",
                    "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                    "knowledge_base_id": None,
                    "allowed_workflow_ids": [],
                },
            )
            assert_error_response(
                viewer_write,
                status=403,
                code="tenant_write_forbidden",
            )
    finally:
        asyncio.run(
            _cleanup(
                tenant_b=tenant_b,
                employee_a=employee_a,
                member_email=member_email,
            )
        )


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


async def _set_role(tenant_id: UUID, role: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                update(TenantMembershipRow)
                .where(TenantMembershipRow.tenant_id == str(tenant_id))
                .values(role=role)
            )
            await session.commit()
    finally:
        await database.stop()


async def _cleanup(
    *,
    tenant_b: UUID | None,
    employee_a: UUID | None,
    member_email: str,
) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            if tenant_b is not None:
                await session.execute(delete(TenantRow).where(TenantRow.id == str(tenant_b)))
            if employee_a is not None:
                await session.execute(
                    delete(ConversationRow).where(ConversationRow.employee_id == str(employee_a))
                )
            await session.execute(delete(AuthUserRow).where(AuthUserRow.email == member_email))
            await session.commit()
        if employee_a is not None:
            await delete_employees(database, employee_a)
    finally:
        await database.stop()
