from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.http import assert_error_response, authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL


def _unique_identifier() -> str:
    """每次运行取唯一标识。

    平台会给新租户预置一批真实模型(含 qwen-turbo), 测试如果固定用其中一个,
    创建时会撞上"显示名或模型标识已存在"的唯一约束。测试数据必须与预置目录分离。
    """
    return f"test-model-{uuid4().hex[:12]}"


def _body(
    *,
    display_name: str | None = None,
    model_identifier: str | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    return {
        "display_name": display_name or f"测试模型-{uuid4().hex[:8]}",
        "model_identifier": model_identifier or _unique_identifier(),
        "enabled": enabled,
    }


def test_model_configuration_crud_uses_formal_uvicorn_mysql_and_survives_restart() -> None:
    configuration_id: str | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            body = _body()
            created = client.post("/api/v1/model-configurations", json=body)
            assert created.status_code == 201
            payload = created.json()
            configuration_id = payload["id"]
            assert payload == {
                "id": configuration_id,
                "display_name": body["display_name"],
                "provider": "bailian",
                "model_identifier": body["model_identifier"],
                "enabled": True,
                "streaming_breaks_tool_calls": False,
                "created_at": payload["created_at"],
                "updated_at": payload["updated_at"],
            }

            listed = client.get("/api/v1/model-configurations")
            assert listed.status_code == 200
            assert configuration_id in {item["id"] for item in listed.json()["items"]}

            user_managed_compatibility = client.post(
                "/api/v1/model-configurations",
                json={**_body(display_name="非法兼容开关"), "streaming_breaks_tool_calls": True},
            )
            assert user_managed_compatibility.status_code == 422

            renamed_identifier = _unique_identifier()
            updated = client.put(
                f"/api/v1/model-configurations/{configuration_id}",
                json=_body(
                    display_name="改名后的模型",
                    model_identifier=renamed_identifier,
                    enabled=False,
                ),
            )
            assert updated.status_code == 200
            assert updated.json()["display_name"] == "改名后的模型"
            assert updated.json()["enabled"] is False
            # 兼容标记由平台的实测表决定, 未记录的标识一律按可流式处理
            assert updated.json()["streaming_breaks_tool_calls"] is False

            # 预置的 deepseek-v4-pro 在实测表里标记为流式绑定工具会断, 读取时必须反映出来
            seeded = client.get(
                "/api/v1/model-configurations",
                params={"search": "deepseek-v4-pro"},
            )
            assert seeded.status_code == 200
            seeded_pro = [
                item
                for item in seeded.json()["items"]
                if item["model_identifier"] == "deepseek-v4-pro"
            ]
            assert seeded_pro and seeded_pro[0]["streaming_breaks_tool_calls"] is True

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
            assert restored.json()["model_identifier"] == renamed_identifier
            assert restored.json()["enabled"] is False
            assert restored.json()["streaming_breaks_tool_calls"] is False
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

            shared_identifier_b = _unique_identifier()
            created_a = client.post(
                "/api/v1/model-configurations",
                headers={"X-Tenant-ID": str(DEFAULT_TENANT_ID)},
                json=_body(display_name="同名模型"),
            )
            created_b = client.post(
                "/api/v1/model-configurations",
                headers={"X-Tenant-ID": tenant_b},
                json=_body(display_name="同名模型", model_identifier=shared_identifier_b),
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
                "model_identifier": shared_identifier_b,
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
