from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text

from common_agent.adapters.agent.platform_tools import PlatformMcpToolRegistry
from common_agent.adapters.mcp.platform import PlatformMcpRuntime
from common_agent.adapters.persistence.conversations import SqlAlchemyConversationRepository
from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    McpSourceRow,
    ToolCapabilityRow,
    ToolCollectionRow,
    ToolCollectionSourceRow,
)
from common_agent.adapters.persistence.tools import (
    SqlAlchemyToolRepository,
    SqlAlchemyToolUnitOfWorkFactory,
)
from common_agent.domain.conversation import Conversation
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from common_agent.tools import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolGrantSelection,
    ToolGrantTarget,
    ToolGrantTargetType,
    ToolService,
    current_time_capability_id,
)
from tests.support.conversations import delete_conversations
from tests.support.employees import (
    DEFAULT_TEST_MODEL_CONFIGURATION_ID,
    delete_employees_from_database_url,
)
from tests.support.http import assert_error_response, authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL


def _employee_body() -> dict[str, object]:
    return {
        "name": f"工具授权员工-{uuid4().hex}",
        "description": "T2-01 正式授权测试",
        "system_prompt": "只使用明确授权的工具。",
        "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
        "knowledge_base_id": None,
        "allowed_workflow_ids": [],
    }


async def _create_generic_conversation() -> UUID:
    conversation = Conversation.create_generic(
        title="工具授权通用会话",
        model_configuration_id=DEFAULT_TEST_MODEL_CONFIGURATION_ID,
    )
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await SqlAlchemyConversationRepository(session).add(conversation)
            await session.commit()
    finally:
        await database.stop()
    return conversation.id


async def _delete_conversation(conversation_id: UUID) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        await delete_conversations(database, conversation_id)
    finally:
        await database.stop()


async def _seed_catalog() -> tuple[McpSource, ToolCapability, UUID]:
    source = McpSource.create(
        name=f"正式测试来源-{uuid4().hex}",
        source_type=McpSourceType.PLATFORM,
        status=McpSourceStatus.READY,
    )
    capability = ToolCapability.create(
        source_id=source.id,
        remote_name="safe.read",
        display_name="安全读取",
        input_schema={"type": "object"},
    )
    collection_id = uuid4()
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            session.add(
                McpSourceRow(
                    id=str(source.id),
                    tenant_id="00000000-0000-4000-8000-000000000002",
                    name=source.name,
                    description=source.description,
                    source_type=source.source_type.value,
                    endpoint_url=source.endpoint_url,
                    status=source.status.value,
                    created_at=source.created_at.replace(tzinfo=None),
                    updated_at=source.updated_at.replace(tzinfo=None),
                )
            )
            session.add(
                ToolCapabilityRow(
                    id=str(capability.id),
                    tenant_id="00000000-0000-4000-8000-000000000002",
                    source_id=str(source.id),
                    remote_name=capability.remote_name,
                    display_name=capability.display_name,
                    description=capability.description,
                    input_schema=capability.input_schema,
                    schema_fingerprint=capability.schema_fingerprint,
                    status=capability.status.value,
                    created_at=capability.created_at.replace(tzinfo=None),
                    updated_at=capability.updated_at.replace(tzinfo=None),
                )
            )
            now = datetime.now(UTC).replace(tzinfo=None)
            session.add(
                ToolCollectionRow(
                    id=str(collection_id),
                    tenant_id="00000000-0000-4000-8000-000000000002",
                    name=f"正式测试工具集-{uuid4().hex}",
                    description="保存时展开",
                    created_at=now,
                    updated_at=now,
                )
            )
            session.add(
                ToolCollectionSourceRow(
                    tenant_id="00000000-0000-4000-8000-000000000002",
                    collection_id=str(collection_id),
                    source_id=str(source.id),
                    created_at=now,
                )
            )
            await session.commit()
    finally:
        await database.stop()
    return source, capability, collection_id


async def _add_capability(source: McpSource, remote_name: str) -> ToolCapability:
    capability = ToolCapability.create(
        source_id=source.id,
        remote_name=remote_name,
        display_name="危险删除",
        input_schema={"type": "object"},
    )
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            session.add(
                ToolCapabilityRow(
                    id=str(capability.id),
                    tenant_id="00000000-0000-4000-8000-000000000002",
                    source_id=str(source.id),
                    remote_name=capability.remote_name,
                    display_name=capability.display_name,
                    description=capability.description,
                    input_schema=capability.input_schema,
                    schema_fingerprint=capability.schema_fingerprint,
                    status=capability.status.value,
                    created_at=capability.created_at.replace(tzinfo=None),
                    updated_at=capability.updated_at.replace(tzinfo=None),
                )
            )
            await session.commit()
    finally:
        await database.stop()
    return capability


async def _assert_cross_tenant_catalog_is_hidden(
    collection_id: UUID,
    capability_id: UUID,
) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            repository = SqlAlchemyToolRepository(session, uuid4())
            catalog = await repository.catalog()
            resolution = await repository.resolve(
                ToolGrantSelection(
                    collection_ids=(collection_id,),
                    capability_ids=(capability_id,),
                )
            )
            assert catalog.sources == ()
            assert catalog.capabilities == ()
            assert catalog.collections == ()
            assert resolution.missing_collection_ids == (collection_id,)
            assert resolution.unavailable_capability_ids == (capability_id,)
    finally:
        await database.stop()


async def _cleanup_catalog(source_id: UUID, collection_id: UUID) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(
                text("DELETE FROM tool_collections WHERE id = :id"),
                {"id": str(collection_id)},
            )
            await session.execute(
                text("DELETE FROM mcp_sources WHERE id = :id"),
                {"id": str(source_id)},
            )
            await session.commit()
    finally:
        await database.stop()


async def _invoke_current_time_for_both_grant_targets(
    employee_id: UUID,
    conversation_id: UUID,
) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        service = ToolService(
            SqlAlchemyToolUnitOfWorkFactory(database, lambda: DEFAULT_TENANT_ID)
        )
        registry = PlatformMcpToolRegistry(
            service,
            PlatformMcpRuntime(
                clock=lambda: datetime(2026, 7, 22, 8, 9, 10, tzinfo=UTC)
            ),
        )
        capability_id = current_time_capability_id(DEFAULT_TENANT_ID)
        for target in (
            ToolGrantTarget(ToolGrantTargetType.EMPLOYEE, employee_id),
            ToolGrantTarget(ToolGrantTargetType.CONVERSATION, conversation_id),
        ):
            tools = await registry.resolve((capability_id,), target=target)
            assert await tools[0].ainvoke({"utc_offset": "+08:00"}) == (
                '{"iso8601":"2026-07-22T16:09:10+08:00",'
                '"unix_timestamp":1784707750,"utc_offset":"+08:00"}'
            )
    finally:
        await database.stop()


def test_tool_catalog_and_employee_exact_grants_use_formal_http_and_mysql() -> None:
    employee_id: str | None = None
    source: McpSource | None = None
    collection_id: UUID | None = None
    conversation_id: UUID | None = None
    employee_conversation_id: str | None = None
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=5) as client,
        ):
            employee = client.post("/api/v1/employees", json=_employee_body())
            assert employee.status_code == 201
            employee_id = employee.json()["id"]
            employee_conversation = client.post(
                "/api/v1/conversations",
                json={"employee_id": employee_id, "title": "员工工具授权隔离"},
            )
            assert employee_conversation.status_code == 201
            employee_conversation_id = employee_conversation.json()["id"]
            source, first, collection_id = asyncio.run(_seed_catalog())
            asyncio.run(_assert_cross_tenant_catalog_is_hidden(collection_id, first.id))
            conversation_id = asyncio.run(_create_generic_conversation())

            catalog = client.get("/api/v1/tool-catalog")
            assert catalog.status_code == 200
            capability_ids = {item["id"] for item in catalog.json()["capabilities"]}
            current_time_id = str(current_time_capability_id(DEFAULT_TENANT_ID))
            assert str(first.id) in capability_ids
            assert current_time_id in capability_ids

            initial_employee_grants = client.get(
                f"/api/v1/employees/{employee_id}/tool-grants"
            )
            assert initial_employee_grants.status_code == 200
            assert initial_employee_grants.json()["capability_ids"] == []

            explicit_employee_time = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": [current_time_id]},
            )
            explicit_conversation_time = client.put(
                f"/api/v1/conversations/{conversation_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": [current_time_id]},
            )
            assert explicit_employee_time.status_code == 200
            assert explicit_conversation_time.status_code == 200
            asyncio.run(
                _invoke_current_time_for_both_grant_targets(
                    UUID(employee_id),
                    conversation_id,
                )
            )

            saved = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [str(collection_id)], "capability_ids": []},
            )
            assert saved.status_code == 200
            assert saved.json()["capability_ids"] == [str(first.id)]

            conversation_saved = client.put(
                f"/api/v1/conversations/{conversation_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": [str(first.id)]},
            )
            assert conversation_saved.status_code == 200
            assert conversation_saved.json()["target_type"] == "conversation"
            assert conversation_saved.json()["capability_ids"] == [str(first.id)]

            employee_conversation_rejected = client.put(
                f"/api/v1/conversations/{employee_conversation_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": [str(first.id)]},
            )
            assert_error_response(
                employee_conversation_rejected,
                status=404,
                code="tool_grant_target_not_found",
            )

            dangerous = asyncio.run(_add_capability(source, "dangerous.delete"))
            unchanged = client.get(f"/api/v1/employees/{employee_id}/tool-grants")
            assert unchanged.status_code == 200
            assert unchanged.json()["capability_ids"] == [str(first.id)]
            assert str(dangerous.id) not in unchanged.json()["capability_ids"]

            explicit_resave = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [str(collection_id)], "capability_ids": []},
            )
            assert explicit_resave.status_code == 200
            assert set(explicit_resave.json()["capability_ids"]) == {
                str(first.id),
                str(dangerous.id),
            }

            rejected = client.put(
                f"/api/v1/employees/{employee_id}/tool-grants",
                json={"collection_ids": [], "capability_ids": [str(uuid4())]},
            )
            assert_error_response(
                rejected,
                status=409,
                code="tool_capability_unavailable",
            )
    finally:
        if conversation_id is not None:
            asyncio.run(_delete_conversation(conversation_id))
        if employee_conversation_id is not None:
            asyncio.run(_delete_conversation(UUID(employee_conversation_id)))
        if employee_id is not None:
            asyncio.run(delete_employees_from_database_url(TEST_DATABASE_URL, employee_id))
        if source is not None and collection_id is not None:
            asyncio.run(_cleanup_catalog(source.id, collection_id))
