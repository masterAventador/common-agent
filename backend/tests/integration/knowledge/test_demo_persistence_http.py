from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

import httpx

from common_agent.adapters.persistence.database import Database
from common_agent.api.routers.conversations import ConversationEventResponse
from tests.support.conversations import delete_conversations
from tests.support.demo_knowledge import delete_demo_knowledge_bases
from tests.support.employees import delete_employees
from tests.support.http import running_api
from tests.support.settings import TEST_DATABASE_URL

_DEMO_ENV = {"COMMON_AGENT_INTEGRATION_MODE": "demo"}


def test_demo_knowledge_employee_and_citations_survive_api_restart() -> None:
    suffix = uuid4().hex
    conversation_id = uuid4()
    employee_id: UUID | None = None
    knowledge_base_id = ""
    try:
        with running_api(TEST_DATABASE_URL, env_overrides=_DEMO_ENV) as first_api_url:
            knowledge_base_id, employee_id = asyncio.run(
                _create_demo_state_and_first_turn(
                    first_api_url,
                    suffix=suffix,
                    conversation_id=conversation_id,
                )
            )

        with running_api(TEST_DATABASE_URL, env_overrides=_DEMO_ENV) as restarted_api_url:
            asyncio.run(
                _assert_state_and_second_turn_after_restart(
                    restarted_api_url,
                    knowledge_base_id=knowledge_base_id,
                    employee_id=employee_id,
                    conversation_id=conversation_id,
                )
            )
    finally:
        asyncio.run(_cleanup(conversation_id, employee_id, knowledge_base_id))


async def _create_demo_state_and_first_turn(
    api_url: str,
    *,
    suffix: str,
    conversation_id: UUID,
) -> tuple[str, UUID]:
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        created_knowledge = await client.post(
            "/api/v1/knowledge-bases",
            json={"name": f"D8-02 重启知识库 {suffix}", "description": "持久语义验收"},
        )
        assert created_knowledge.status_code == 201
        knowledge_base_id = str(created_knowledge.json()["id"])

        uploaded = await client.post(
            f"/api/v1/knowledge-bases/{knowledge_base_id}/documents",
            files={
                "file": (
                    "d8-02-restart.txt",
                    "D8-02 持久知识标记: 重启后仍可检索。".encode(),
                    "text/plain",
                )
            },
        )
        assert uploaded.status_code == 202
        assert uploaded.json()["parsing_status"] == "completed"

        created_employee = await client.post(
            "/api/v1/employees",
            json={
                "name": f"D8-02 重启员工 {suffix}",
                "description": "持久语义验收",
                "system_prompt": "使用绑定知识回答。",
                "knowledge_base_id": knowledge_base_id,
                "allowed_workflow_ids": [],
            },
        )
        assert created_employee.status_code == 201
        employee_id = UUID(created_employee.json()["id"])

        created_conversation = await client.post(
            "/api/v1/conversations",
            json={
                "conversation_id": str(conversation_id),
                "employee_id": str(employee_id),
                "title": "D8-02 重启会话",
            },
        )
        assert created_conversation.status_code == 201
        first = await _send_and_wait(
            client,
            conversation_id,
            content="第一轮: 持久知识标记是什么?",
        )
        assert first.message.citations[0].knowledge_base_id == knowledge_base_id
        assert first.message.citations[0].document_name == "d8-02-restart.txt"
        return knowledge_base_id, employee_id


async def _assert_state_and_second_turn_after_restart(
    api_url: str,
    *,
    knowledge_base_id: str,
    employee_id: UUID,
    conversation_id: UUID,
) -> None:
    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        knowledge_bases = await client.get("/api/v1/knowledge-bases")
        assert knowledge_bases.status_code == 200
        assert knowledge_base_id in {str(item["id"]) for item in knowledge_bases.json()["items"]}

        documents = await client.get(f"/api/v1/knowledge-bases/{knowledge_base_id}/documents")
        assert documents.status_code == 200
        assert documents.json()[0]["name"] == "d8-02-restart.txt"
        assert documents.json()[0]["parsing_status"] == "completed"

        employee = await client.get(f"/api/v1/employees/{employee_id}")
        assert employee.status_code == 200
        assert employee.json()["knowledge_base_id"] == knowledge_base_id

        history = await client.get(f"/api/v1/conversations/{conversation_id}/messages")
        assert history.status_code == 200
        assert history.json()[-1]["citations"][0]["knowledge_base_id"] == knowledge_base_id

        second = await _send_and_wait(
            client,
            conversation_id,
            content="第二轮: 重启后还能检索吗?",
        )
        assert "第 2 轮" in second.message.content
        assert second.message.citations[0].knowledge_base_id == knowledge_base_id
        assert second.message.citations[0].document_name == "d8-02-restart.txt"


async def _send_and_wait(
    client: httpx.AsyncClient,
    conversation_id: UUID,
    *,
    content: str,
) -> ConversationEventResponse:
    sent = await client.post(
        f"/api/v1/conversations/{conversation_id}/messages",
        json={"message_id": str(uuid4()), "content": content},
    )
    assert sent.status_code == 202

    async with client.stream(
        "GET",
        f"/api/v1/conversations/{conversation_id}/events",
    ) as response:
        assert response.status_code == 200
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            event = ConversationEventResponse.model_validate_json(line.removeprefix("data: "))
            if event.type == "assistant.completed":
                return event
            if event.type in {"assistant.failed", "assistant.stopped"}:
                raise AssertionError(f"Demo turn ended unexpectedly: {event.type}")
    raise AssertionError("Demo SSE stream ended without a terminal event")


async def _cleanup(
    conversation_id: UUID,
    employee_id: UUID | None,
    knowledge_base_id: str,
) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        await delete_conversations(database, conversation_id)
        if employee_id is not None:
            await delete_employees(database, employee_id)
        if knowledge_base_id:
            await delete_demo_knowledge_bases(database, knowledge_base_id)
    finally:
        await database.stop()
