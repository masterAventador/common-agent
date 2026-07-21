from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.http import assert_error_response, authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL


def _body(
    *,
    display_name: str = "Qwen Turbo",
    model_identifier: str = "qwen-turbo",
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "display_name": display_name,
        "model_identifier": model_identifier,
        "enabled": enabled,
    }


def test_model_configuration_crud_uses_formal_uvicorn_mysql_and_survives_restart() -> None:
    configuration_id: str | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            created = client.post("/api/v1/model-configurations", json=_body())
            assert created.status_code == 201
            payload = created.json()
            configuration_id = payload["id"]
            assert payload == {
                "id": configuration_id,
                "display_name": "Qwen Turbo",
                "provider": "bailian",
                "model_identifier": "qwen-turbo",
                "enabled": True,
                "created_at": payload["created_at"],
                "updated_at": payload["updated_at"],
            }

            listed = client.get("/api/v1/model-configurations")
            assert listed.status_code == 200
            assert configuration_id in {item["id"] for item in listed.json()["items"]}

            updated = client.put(
                f"/api/v1/model-configurations/{configuration_id}",
                json=_body(
                    display_name="Qwen Max",
                    model_identifier="qwen-max-latest",
                    enabled=False,
                ),
            )
            assert updated.status_code == 200
            assert updated.json()["display_name"] == "Qwen Max"
            assert updated.json()["enabled"] is False

            enabled_only = client.get(
                "/api/v1/model-configurations",
                params={"enabled_only": True},
            )
            assert enabled_only.status_code == 200
            assert configuration_id not in {item["id"] for item in enabled_only.json()["items"]}

            audit = client.get(
                "/api/v1/audit-events",
                params={
                    "resource_type": "model_configuration",
                    "resource_id": configuration_id,
                },
            )
            assert audit.status_code == 200
            assert {item["action"] for item in audit.json()["items"]} >= {
                "model.configuration.created",
                "model.configuration.updated",
            }

        with (
            running_api(TEST_DATABASE_URL) as restarted_url,
            authenticated_client(base_url=restarted_url, timeout=5) as client,
        ):
            restored = client.get(f"/api/v1/model-configurations/{configuration_id}")
            assert restored.status_code == 200
            assert restored.json()["model_identifier"] == "qwen-max-latest"
            assert restored.json()["enabled"] is False
            assert (
                client.delete(f"/api/v1/model-configurations/{configuration_id}").status_code == 204
            )
            configuration_id = None
    finally:
        if configuration_id is not None:
            asyncio.run(_delete_model_configuration(configuration_id))


def test_model_configuration_delete_fails_closed_while_reference_exists() -> None:
    configuration_id: str | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            created = client.post(
                "/api/v1/model-configurations",
                json=_body(display_name=f"引用阻断-{uuid4().hex}"),
            )
            assert created.status_code == 201
            configuration_id = created.json()["id"]
            asyncio.run(_add_reference(configuration_id))

            blocked = client.delete(f"/api/v1/model-configurations/{configuration_id}")
            assert_error_response(
                blocked,
                status=409,
                code="model_configuration_in_use",
            )
            assert client.get(f"/api/v1/model-configurations/{configuration_id}").status_code == 200
    finally:
        if configuration_id is not None:
            asyncio.run(_delete_reference(configuration_id))
            asyncio.run(_delete_model_configuration(configuration_id))


def test_model_configuration_is_tenant_isolated_and_demo_verification_uses_selected_model() -> None:
    configuration_ids: list[str] = []
    tenant_b: str | None = None
    try:
        with (
            running_api(
                TEST_DATABASE_URL,
                env_overrides={"COMMON_AGENT_INTEGRATION_MODE": "demo"},
            ) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            default = client.get("/api/v1/tenants").json()[0]
            created_tenant = client.post(
                "/api/v1/tenants",
                json={
                    "organization_id": default["organization_id"],
                    "name": f"模型隔离-{uuid4().hex}",
                },
            )
            assert created_tenant.status_code == 201
            tenant_b = created_tenant.json()["id"]

            created_a = client.post(
                "/api/v1/model-configurations",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                json=_body(display_name="同名模型"),
            )
            created_b = client.post(
                "/api/v1/model-configurations",
                headers={"X-Tenant-ID": tenant_b},
                json=_body(display_name="同名模型", model_identifier="qwen-max"),
            )
            assert created_a.status_code == created_b.status_code == 201
            configuration_ids.extend([created_a.json()["id"], created_b.json()["id"]])

            hidden = client.get(
                f"/api/v1/model-configurations/{created_a.json()['id']}",
                headers={"X-Tenant-ID": tenant_b},
            )
            assert_error_response(hidden, status=404, code="model_configuration_not_found")

            verified = client.post(
                f"/api/v1/model-configurations/{created_b.json()['id']}/verify",
                headers={"X-Tenant-ID": tenant_b},
            )
            assert verified.status_code == 200
            assert verified.json() == {
                "status": "available",
                "model_identifier": "qwen-max",
                "response_preview": "演示模式模型连接正常",
            }
    finally:
        for configuration_id in configuration_ids:
            asyncio.run(_delete_model_configuration(configuration_id))
        if tenant_b is not None:
            asyncio.run(_delete_tenant(tenant_b))


async def _add_reference(configuration_id: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                text(
                    "INSERT INTO model_configuration_references "
                    "(tenant_id, model_configuration_id, resource_type, resource_id, created_at) "
                    "VALUES (:tenant_id, :configuration_id, 'employee', :resource_id, :created_at)"
                ),
                {
                    "tenant_id": str(DEFAULT_TENANT_ID),
                    "configuration_id": configuration_id,
                    "resource_id": str(uuid4()),
                    "created_at": datetime.now(UTC).replace(tzinfo=None),
                },
            )
            await session.commit()
    finally:
        await database.stop()


async def _delete_reference(configuration_id: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                text(
                    "DELETE FROM model_configuration_references "
                    "WHERE model_configuration_id = :configuration_id"
                ),
                {"configuration_id": configuration_id},
            )
            await session.commit()
    finally:
        await database.stop()


async def _delete_model_configuration(configuration_id: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                text("DELETE FROM model_configurations WHERE id = :configuration_id"),
                {"configuration_id": configuration_id},
            )
            await session.commit()
    finally:
        await database.stop()


async def _delete_tenant(tenant_id: str) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                text("DELETE FROM tenants WHERE id = :tenant_id"),
                {"tenant_id": tenant_id},
            )
            await session.commit()
    finally:
        await database.stop()
