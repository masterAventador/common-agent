from __future__ import annotations

import asyncio
import os
from uuid import UUID, uuid4

import httpx
import pytest

from common_agent.api.routers.conversations import ConversationEventResponse
from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from common_agent.model_configurations.defaults import platform_default_model_configuration_id
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.conversations import delete_conversations
from tests.support.http import (
    assert_error_response,
    authenticated_async_client,
    authenticated_client,
    running_api,
)
from tests.support.model_configuration_e2e_state import (
    delete_model_configurations_named_from_database_url,
)
from tests.support.settings import TEST_DATABASE_URL


def test_conversation_crud_and_errors_use_formal_uvicorn_mysql_path() -> None:
    conversation_id = uuid4()
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=10) as client,
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


def test_first_generic_turn_atomically_creates_conversation_messages_and_task() -> None:
    conversation_id = uuid4()
    message_id = uuid4()
    model_configuration_id = platform_default_model_configuration_id(DEFAULT_TENANT_ID)
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=10) as client,
        ):
            accepted = client.post(
                "/api/v1/conversation-turns",
                json={
                    "conversation_id": str(conversation_id),
                    "message_id": str(message_id),
                    "employee_id": None,
                    "model_configuration_id": str(model_configuration_id),
                    "content": "请介绍一下你自己",
                },
            )
            history = client.get(f"/api/v1/conversations/{conversation_id}/messages")
            duplicate = client.post(
                "/api/v1/conversation-turns",
                json={
                    "conversation_id": str(conversation_id),
                    "message_id": str(message_id),
                    "employee_id": None,
                    "model_configuration_id": str(model_configuration_id),
                    "content": "重复首轮",
                },
            )

        assert accepted.status_code == 202
        payload = accepted.json()
        assert payload["conversation"]["id"] == str(conversation_id)
        assert payload["conversation"]["source"] == "generic"
        assert payload["conversation"]["employee_id"] is None
        assert payload["conversation"]["model_configuration_id"] == str(model_configuration_id)
        assert payload["turn"]["user_message"]["id"] == str(message_id)
        assert payload["turn"]["assistant_message"]["model_configuration_id"] == str(
            model_configuration_id
        )
        assert payload["turn"]["assistant_message"]["model_identifier"] == "qwen-plus"
        assert history.status_code == 200
        assert [item["role"] for item in history.json()] == ["user", "assistant"]
        assert_error_response(duplicate, status=409, code="conversation_request_conflict")
    finally:
        asyncio.run(_delete_conversation(conversation_id))


def test_first_turn_rejects_unknown_model_without_leaving_partial_conversation() -> None:
    conversation_id = uuid4()
    with (
        running_api(TEST_DATABASE_URL) as api_url,
        authenticated_client(base_url=api_url, timeout=10) as client,
    ):
        rejected = client.post(
            "/api/v1/conversation-turns",
            json={
                "conversation_id": str(conversation_id),
                "message_id": str(uuid4()),
                "employee_id": None,
                "model_configuration_id": str(uuid4()),
                "content": "不能留下半成品",
            },
        )
        missing = client.get(f"/api/v1/conversations/{conversation_id}/messages")

    assert_error_response(rejected, status=404, code="model_configuration_not_found")
    assert_error_response(missing, status=404, code="conversation_not_found")


def test_employee_first_turn_uses_selected_model_without_mutating_employee_default() -> None:
    conversation_id = uuid4()
    model_name = f"S10-07G 临时模型 {str(uuid4())[:8]}"
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=10) as client,
        ):
            created_model = client.post(
                "/api/v1/model-configurations",
                json={
                    "display_name": model_name,
                    "model_identifier": "qwen-turbo",
                    "enabled": True,
                },
            )
            assert created_model.status_code == 201
            selected_model_id = created_model.json()["id"]
            accepted = client.post(
                "/api/v1/conversation-turns",
                json={
                    "conversation_id": str(conversation_id),
                    "message_id": str(uuid4()),
                    "employee_id": str(DEFAULT_KNOWLEDGE_ASSISTANT_ID),
                    "model_configuration_id": selected_model_id,
                    "content": "本轮使用临时模型",
                },
            )
            employee = client.get(f"/api/v1/employees/{DEFAULT_KNOWLEDGE_ASSISTANT_ID}")

        assert accepted.status_code == 202
        assert accepted.json()["conversation"]["source"] == "employee"
        assert accepted.json()["turn"]["assistant_message"]["model_configuration_id"] == (
            selected_model_id
        )
        assert accepted.json()["turn"]["assistant_message"]["model_identifier"] == "qwen-turbo"
        assert employee.status_code == 200
        assert employee.json()["default_model_identifier"] == "qwen-plus"
        assert employee.json()["default_model_configuration_id"] != selected_model_id
    finally:
        asyncio.run(_delete_conversation(conversation_id))
        asyncio.run(
            delete_model_configurations_named_from_database_url(
                TEST_DATABASE_URL,
                model_name,
            )
        )


def test_history_uses_updated_order_employee_attribution_and_stable_cursor() -> None:
    older_id = uuid4()
    newer_id = uuid4()
    try:
        with (
            running_api(TEST_DATABASE_URL) as api_url,
            authenticated_client(base_url=api_url, timeout=10) as client,
        ):
            for conversation_id, title in (
                (older_id, "较早但刚继续的会话"),
                (newer_id, "较新的会话"),
            ):
                created = client.post(
                    "/api/v1/conversations",
                    json={
                        "conversation_id": str(conversation_id),
                        "employee_id": str(DEFAULT_KNOWLEDGE_ASSISTANT_ID),
                        "title": title,
                    },
                )
                assert created.status_code == 201

            continued = client.post(
                f"/api/v1/conversations/{older_id}/messages",
                json={
                    "message_id": str(uuid4()),
                    "model_configuration_id": str(
                        platform_default_model_configuration_id(DEFAULT_TENANT_ID)
                    ),
                    "content": "把这条会话移动到历史顶部",
                },
            )
            first_page = client.get("/api/v1/conversations", params={"limit": 1})
            detail = client.get(f"/api/v1/conversations/{older_id}")
            second_page = client.get(
                "/api/v1/conversations",
                params={"limit": 1, "cursor": first_page.json()["next_cursor"]},
            )

        assert continued.status_code == 202
        assert first_page.status_code == 200
        assert len(first_page.json()["items"]) == 1
        assert first_page.json()["items"][0]["id"] == str(older_id)
        assert first_page.json()["items"][0]["employee_name"] == "知识助理"
        assert first_page.json()["next_cursor"] is not None
        assert detail.status_code == 200
        assert detail.json()["id"] == str(older_id)
        assert detail.json()["employee_name"] == "知识助理"
        assert second_page.status_code == 200
        assert second_page.json()["items"][0]["id"] == str(newer_id)
    finally:
        asyncio.run(_delete_conversation(older_id))
        asyncio.run(_delete_conversation(newer_id))


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
    async with await authenticated_async_client(base_url=api_url, timeout=90) as client:
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
