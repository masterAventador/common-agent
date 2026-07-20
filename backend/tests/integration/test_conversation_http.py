from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import httpx
import pytest

from common_agent.api.routers.conversations import ConversationEventResponse
from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from tests.support.conversations import delete_conversations
from tests.support.http import assert_error_response, running_api
from tests.support.settings import TEST_DATABASE_URL


def test_conversation_crud_and_errors_use_formal_uvicorn_mysql_path() -> None:
    conversation_id = uuid4()
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            httpx.Client(base_url=api_url, timeout=10) as client,
        ):
            created = client.post(
                "/api/v1/conversations",
                json={
                    "conversation_id": str(conversation_id),
                    "employee_id": str(DEFAULT_KNOWLEDGE_ASSISTANT_ID),
                    "title": "  正式会话  ",
                },
            )
            listed = client.get("/api/v1/conversations")
            filtered = client.get(
                "/api/v1/conversations",
                params={"employee_id": str(DEFAULT_KNOWLEDGE_ASSISTANT_ID)},
            )
            messages = client.get(f"/api/v1/conversations/{conversation_id}/messages")
            duplicate = client.post(
                "/api/v1/conversations",
                json={
                    "conversation_id": str(conversation_id),
                    "employee_id": str(DEFAULT_KNOWLEDGE_ASSISTANT_ID),
                    "title": "重复会话",
                },
            )
            missing = client.get(f"/api/v1/conversations/{uuid4()}/messages")
            inactive_stop = client.post(f"/api/v1/conversations/{conversation_id}/stop")

        assert created.status_code == 201
        assert created.json()["title"] == "正式会话"
        assert str(conversation_id) in {item["id"] for item in listed.json()["items"]}
        assert str(conversation_id) in {item["id"] for item in filtered.json()["items"]}
        assert messages.status_code == 200
        assert messages.json() == []
        assert_error_response(duplicate, status=409, code="conversation_request_conflict")
        assert_error_response(missing, status=404, code="conversation_not_found")
        assert_error_response(inactive_stop, status=409, code="generation_not_active")
    finally:
        asyncio.run(_delete_conversation(conversation_id))


def test_real_http_sse_send_stop_retry_and_duplicate_submission() -> None:
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实会话 API + SSE + 百炼验收")

    conversation_id = uuid4()
    user_message_id = uuid4()
    try:
        with running_api(TEST_DATABASE_URL) as api_url:
            asyncio.run(
                _exercise_real_chat(
                    api_url,
                    conversation_id=conversation_id,
                    user_message_id=user_message_id,
                )
            )
    finally:
        asyncio.run(_delete_conversation(conversation_id))


async def _exercise_real_chat(
    api_url: str,
    *,
    conversation_id: UUID,
    user_message_id: UUID,
) -> None:
    async with httpx.AsyncClient(base_url=api_url, timeout=90) as client:
        created = await client.post(
            "/api/v1/conversations",
            json={
                "conversation_id": str(conversation_id),
                "employee_id": str(DEFAULT_KNOWLEDGE_ASSISTANT_ID),
                "title": "A4-06 真实 SSE 验收",
            },
        )
        assert created.status_code == 201
        sent = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={
                "message_id": str(user_message_id),
                "content": "请从 1 数到 200,每个数字用逗号分隔,不使用任何工具。",
            },
        )
        assert sent.status_code == 202
        assistant_message_id = sent.json()["assistant_message"]["id"]

        first_events = await _consume_until_terminal(
            client,
            conversation_id,
            stop_after_first_delta=True,
        )
        assert first_events[-1].type == "assistant.stopped"
        first_last_sequence = first_events[-1].sequence

        retried = await client.post(f"/api/v1/messages/{assistant_message_id}/retry")
        assert retried.status_code == 202
        assert retried.json()["assistant_message"]["id"] == assistant_message_id
        assert retried.json()["retry"] is True

        retry_events = await _consume_until_terminal(
            client,
            conversation_id,
            after_sequence=first_last_sequence,
        )
        assert retry_events[0].retry is True
        assert retry_events[-1].type == "assistant.completed"
        assert retry_events[-1].message.content.strip()
        all_sequences = [event.sequence for event in (*first_events, *retry_events)]
        assert all_sequences == list(range(1, len(all_sequences) + 1))

        duplicate = await client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message_id": str(user_message_id), "content": "重复提交"},
        )
        assert_error_response(duplicate, status=409, code="message_request_conflict")

        history = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert history.status_code == 200
        assert len(history.json()) == 2
        assert history.json()[-1]["status"] == "completed"


async def _consume_until_terminal(
    client: httpx.AsyncClient,
    conversation_id: UUID,
    *,
    after_sequence: int = 0,
    stop_after_first_delta: bool = False,
) -> list[ConversationEventResponse]:
    events: list[ConversationEventResponse] = []
    stop_requested = False
    async with client.stream(
        "GET",
        f"/api/v1/conversations/{conversation_id}/events",
        params={"after_sequence": after_sequence},
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = ConversationEventResponse.model_validate_json(line.removeprefix("data: "))
            events.append(event)
            if stop_after_first_delta and event.type == "assistant.delta" and not stop_requested:
                stopped = await client.post(f"/api/v1/conversations/{conversation_id}/stop")
                assert stopped.status_code == 202
                stop_requested = True
            if event.type in {
                "assistant.completed",
                "assistant.failed",
                "assistant.stopped",
            }:
                return events
    raise AssertionError("SSE stream ended without a terminal event")


async def _delete_conversation(conversation_id: UUID) -> None:
    from common_agent.adapters.persistence.database import Database

    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        await delete_conversations(database, conversation_id)
    finally:
        await database.stop()
