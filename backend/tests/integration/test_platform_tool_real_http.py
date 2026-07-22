from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import httpx
import pytest

from common_agent.adapters.persistence.conversations import SqlAlchemyConversationRepository
from common_agent.adapters.persistence.database import Database
from common_agent.api.routers.conversations import ConversationEventResponse
from common_agent.domain.conversation import Conversation
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from common_agent.tools import current_time_capability_id
from tests.support.conversations import delete_conversations
from tests.support.employees import (
    DEFAULT_TEST_MODEL_CONFIGURATION_ID,
    delete_employees_from_database_url,
)
from tests.support.http import authenticated_async_client, running_api
from tests.support.settings import TEST_DATABASE_URL


def test_real_model_worker_and_mcp_close_both_conversation_paths() -> None:
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实百炼 + Worker + 平台 MCP 验收")

    generic_conversation_id = uuid4()
    employee_id: UUID | None = None
    employee_conversation_id: UUID | None = None
    asyncio.run(_create_generic_conversation(generic_conversation_id))
    try:
        with running_api(TEST_DATABASE_URL) as api_url:
            employee_id, employee_conversation_id, first_events = asyncio.run(
                _exercise_both_paths(api_url, generic_conversation_id)
            )

        with running_api(TEST_DATABASE_URL) as restarted_url:
            replayed = asyncio.run(
                _replay_after_restart(
                    restarted_url,
                    (generic_conversation_id, employee_conversation_id),
                )
            )

        assert {
            conversation_id: _safe_event_identity(events)
            for conversation_id, events in replayed.items()
        } == {
            conversation_id: _safe_event_identity(events)
            for conversation_id, events in first_events.items()
        }
    finally:
        conversation_ids = [generic_conversation_id]
        if employee_conversation_id is not None:
            conversation_ids.append(employee_conversation_id)
        asyncio.run(_delete_conversations(*conversation_ids))
        if employee_id is not None:
            asyncio.run(
                delete_employees_from_database_url(TEST_DATABASE_URL, employee_id)
            )


async def _exercise_both_paths(
    api_url: str,
    generic_conversation_id: UUID,
) -> tuple[
    UUID,
    UUID,
    dict[UUID, list[ConversationEventResponse]],
]:
    capability_id = current_time_capability_id(DEFAULT_TENANT_ID)
    async with await authenticated_async_client(base_url=api_url, timeout=90) as client:
        employee = await client.post(
            "/api/v1/employees",
            json={
                "name": f"真实 MCP 员工-{uuid4().hex}",
                "description": "T2-03 真实纵向验收",
                "system_prompt": "必须按用户要求调用当前明确授权的工具,再根据结果回答。",
                "default_model_configuration_id": str(DEFAULT_TEST_MODEL_CONFIGURATION_ID),
                "knowledge_base_id": None,
                "allowed_workflow_ids": [],
            },
        )
        assert employee.status_code == 201
        employee_id = UUID(employee.json()["id"])
        employee_conversation_id = uuid4()
        employee_conversation = await client.post(
            "/api/v1/conversations",
            json={
                "conversation_id": str(employee_conversation_id),
                "employee_id": str(employee_id),
                "title": "真实 MCP 员工会话",
            },
        )
        assert employee_conversation.status_code == 201

        for path in (
            f"/api/v1/employees/{employee_id}/tool-grants",
            f"/api/v1/conversations/{generic_conversation_id}/tool-grants",
        ):
            granted = await client.put(
                path,
                json={"collection_ids": [], "capability_ids": [str(capability_id)]},
            )
            assert granted.status_code == 200
            assert granted.json()["capability_ids"] == [str(capability_id)]

        events: dict[UUID, list[ConversationEventResponse]] = {}
        for conversation_id in (employee_conversation_id, generic_conversation_id):
            accepted = await client.post(
                f"/api/v1/conversations/{conversation_id}/messages",
                json={
                    "message_id": str(uuid4()),
                    "content": (
                        "请务必调用 current_time 工具一次,使用 +08:00,"
                        "然后根据工具返回值告诉我当前时间;不要猜测。"
                    ),
                },
            )
            assert accepted.status_code == 202
            events[conversation_id] = await _consume_until_terminal(client, conversation_id)
            _assert_successful_tool_turn(events[conversation_id], capability_id)

        audit = await client.get(
            "/api/v1/audit-events",
            params={
                "action": "tool.called",
                "resource_type": "tool_capability",
                "resource_id": str(capability_id),
                "limit": 50,
            },
        )
        assert audit.status_code == 200
        entries = audit.json()["items"]
        assert {entry["outcome"] for entry in entries} >= {"started", "succeeded"}
        assert all(entry["resource_id"] == str(capability_id) for entry in entries)
        assert all("arguments" not in entry and "result" not in entry for entry in entries)
        return employee_id, employee_conversation_id, events


async def _replay_after_restart(
    api_url: str,
    conversation_ids: tuple[UUID, ...],
) -> dict[UUID, list[ConversationEventResponse]]:
    async with await authenticated_async_client(base_url=api_url, timeout=30) as client:
        return {
            conversation_id: await _consume_until_terminal(client, conversation_id)
            for conversation_id in conversation_ids
        }


async def _consume_until_terminal(
    client: httpx.AsyncClient,
    conversation_id: UUID,
) -> list[ConversationEventResponse]:
    events: list[ConversationEventResponse] = []
    async with client.stream(
        "GET",
        f"/api/v1/conversations/{conversation_id}/events",
        params={"after_sequence": 0},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = ConversationEventResponse.model_validate_json(line.removeprefix("data: "))
            events.append(event)
            if event.type in {
                "assistant.completed",
                "assistant.failed",
                "assistant.stopped",
            }:
                return events
    raise AssertionError("SSE stream ended without a terminal event")


def _assert_successful_tool_turn(
    events: list[ConversationEventResponse],
    capability_id: UUID,
) -> None:
    assert events[-1].type == "assistant.completed"
    started = [event for event in events if event.type == "assistant.tool.started"]
    completed = [event for event in events if event.type == "assistant.tool.completed"]
    assert started and completed
    assert {event.tool_call.tool_call_id for event in started if event.tool_call is not None} == {
        event.tool_call.tool_call_id for event in completed if event.tool_call is not None
    }
    assert all(
        event.tool_call is not None and event.tool_call.capability_id == capability_id
        for event in (*started, *completed)
    )
    assert events[-1].message.content.strip()


def _safe_event_identity(
    events: list[ConversationEventResponse],
) -> list[tuple[int, object, object]]:
    return [
        (
            event.sequence,
            event.type,
            None if event.tool_call is None else event.tool_call.tool_call_id,
        )
        for event in events
    ]


async def _create_generic_conversation(conversation_id: UUID) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        async with database.session() as session:
            await SqlAlchemyConversationRepository(session).add(
                Conversation.create_generic(
                    title="真实 MCP 通用会话",
                    model_configuration_id=DEFAULT_TEST_MODEL_CONFIGURATION_ID,
                    conversation_id=conversation_id,
                )
            )
            await session.commit()
    finally:
        await database.stop()


async def _delete_conversations(*conversation_ids: UUID) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        await delete_conversations(database, *conversation_ids)
    finally:
        await database.stop()
