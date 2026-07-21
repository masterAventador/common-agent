from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx

from common_agent.adapters.persistence import Database, MySqlNamedLockProvider
from common_agent.application.resource_locks import ResourceMutationGuard
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.http import authenticated_client, running_apis
from tests.support.settings import TEST_DATABASE_URL


def test_mysql_named_lock_serializes_distinct_application_instances() -> None:
    async def exercise() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        try:
            first = ResourceMutationGuard(distributed=MySqlNamedLockProvider(database))
            second = ResourceMutationGuard(distributed=MySqlNamedLockProvider(database))
            first_entered = asyncio.Event()
            release_first = asyncio.Event()
            second_entered = asyncio.Event()

            async def hold_first() -> None:
                async with first.hold("tenant:test:knowledge:kb-1"):
                    first_entered.set()
                    await release_first.wait()

            async def hold_second() -> None:
                await first_entered.wait()
                async with second.hold("tenant:test:knowledge:kb-1"):
                    second_entered.set()

            first_task = asyncio.create_task(hold_first())
            second_task = asyncio.create_task(hold_second())
            await first_entered.wait()
            await asyncio.sleep(0.05)
            assert second_entered.is_set() is False
            release_first.set()
            await asyncio.gather(first_task, second_task)
            assert second_entered.is_set()
        finally:
            await database.stop()

    asyncio.run(exercise())


def test_two_formal_http_instances_wait_for_the_same_mysql_resource_lock() -> None:
    demo_environment = {"COMMON_AGENT_INTEGRATION_MODE": "demo"}
    with (
        running_apis(TEST_DATABASE_URL, count=2, env_overrides=demo_environment) as api_urls,
        authenticated_client(base_url=api_urls[0], timeout=15) as first_client,
        authenticated_client(base_url=api_urls[1], timeout=15) as second_client,
    ):
        created = first_client.post(
            "/api/v1/employees",
            json={
                "name": f"多实例互斥-{uuid4().hex}",
                "description": "创建态",
                "system_prompt": "保持互斥。",
                "knowledge_base_id": None,
                "allowed_workflow_ids": [],
            },
        )
        assert created.status_code == 201
        employee_id = UUID(created.json()["id"])
        try:

            async def exercise() -> tuple[httpx.Response, httpx.Response]:
                database = Database(TEST_DATABASE_URL)
                await database.start()
                try:
                    external_instance = ResourceMutationGuard(
                        distributed=MySqlNamedLockProvider(database)
                    )
                    resource = f"tenant:{DEFAULT_TENANT_ID}:employee:{employee_id}"
                    async with external_instance.hold(resource):
                        first_update = asyncio.create_task(
                            asyncio.to_thread(
                                first_client.put,
                                f"/api/v1/employees/{employee_id}",
                                json={
                                    "name": "多实例更新-A",
                                    "description": "来自第一个正式 API",
                                    "system_prompt": "保持互斥。",
                                    "knowledge_base_id": None,
                                    "allowed_workflow_ids": [],
                                },
                            )
                        )
                        second_update = asyncio.create_task(
                            asyncio.to_thread(
                                second_client.put,
                                f"/api/v1/employees/{employee_id}",
                                json={
                                    "name": "多实例更新-B",
                                    "description": "来自第二个正式 API",
                                    "system_prompt": "保持互斥。",
                                    "knowledge_base_id": None,
                                    "allowed_workflow_ids": [],
                                },
                            )
                        )
                        await asyncio.sleep(0.1)
                        assert first_update.done() is False
                        assert second_update.done() is False
                    return await asyncio.gather(first_update, second_update)
                finally:
                    await database.stop()

            first_response, second_response = asyncio.run(exercise())
            assert first_response.status_code == 200
            assert second_response.status_code == 200
            persisted = first_client.get(f"/api/v1/employees/{employee_id}")
            assert persisted.status_code == 200
            assert persisted.json()["name"] in {"多实例更新-A", "多实例更新-B"}
        finally:
            deleted = first_client.delete(f"/api/v1/employees/{employee_id}")
            assert deleted.status_code == 204
