from __future__ import annotations

import asyncio
from uuid import UUID

import pytest

from common_agent.adapters.demo import DemoEmployeeRuntime, DemoKnowledgeService
from common_agent.domain.conversation import MessageRole
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeRetrievalRequest,
    KnowledgeServiceAvailability,
)
from common_agent.knowledge.base import KnowledgeRequestRejected
from common_agent.runtimes.base import (
    EmployeeRuntimeRequest,
    RuntimeConversationMessage,
    RuntimeEvent,
    RuntimeEventKind,
    RuntimeKnowledgeChunk,
    RuntimeStopToken,
)
from tests.support.knowledge import MemoryDemoKnowledgeUnitOfWorkFactory

CONVERSATION_ID = UUID("40b8bf77-fd8b-46ca-a103-5bebc29e185e")
EMPLOYEE_ID = UUID("ddbdad78-1128-4334-ad02-d28833357529")
USER_MESSAGE_ID = UUID("3b2257d7-86fe-4abe-86c8-75388da202ae")
ASSISTANT_MESSAGE_ID = UUID("0aa6e182-e4a2-4abd-bad6-8bd59ea86d03")


def _request(
    content: str,
    *,
    assistant_message_id: UUID = ASSISTANT_MESSAGE_ID,
    previous_turn: bool = False,
) -> EmployeeRuntimeRequest:
    history = (
        (
            RuntimeConversationMessage(
                message_id=UUID("c7473399-e1b7-4503-8ea4-799e8586833e"),
                sequence_number=1,
                role=MessageRole.USER,
                content="第一轮问题",
            ),
            RuntimeConversationMessage(
                message_id=UUID("dd0feebe-b9e5-467f-a90b-fb735031a8fb"),
                sequence_number=2,
                role=MessageRole.ASSISTANT,
                content="第一轮回答",
            ),
        )
        if previous_turn
        else ()
    )
    current_sequence = len(history) + 1
    return EmployeeRuntimeRequest(
        conversation_id=CONVERSATION_ID,
        employee_id=EMPLOYEE_ID,
        assistant_message_id=assistant_message_id,
        assistant_sequence_number=current_sequence + 1,
        system_instruction="演示模式系统指令",
        history=(
            *history,
            RuntimeConversationMessage(
                message_id=USER_MESSAGE_ID,
                sequence_number=current_sequence,
                role=MessageRole.USER,
                content=content,
            ),
        ),
        knowledge_base_id="demo-kb",
        knowledge_context=(
            RuntimeKnowledgeChunk(
                knowledge_base_id="demo-kb",
                chunk_id="demo-chunk",
                document_id="demo-document",
                document_name="demo-guide.txt",
                content="Common Agent 是通用 Agent 中台。",
                score=1.0,
            ),
        ),
        allowed_workflow_ids=(),
    )


async def _events(
    runtime: DemoEmployeeRuntime,
    request: EmployeeRuntimeRequest,
    *,
    stop: RuntimeStopToken | None = None,
) -> tuple[RuntimeEvent, ...]:
    return tuple(
        [event async for event in runtime.stream(request, stop=stop or RuntimeStopToken())]
    )


def test_demo_knowledge_adapter_supports_formal_crud_upload_and_retrieval() -> None:
    async def exercise() -> None:
        unit_of_work = MemoryDemoKnowledgeUnitOfWorkFactory()
        knowledge = DemoKnowledgeService(unit_of_work)
        status = await knowledge.status()
        created = await knowledge.create_knowledge_base(
            CreateKnowledgeBaseRequest(name="演示知识库", description="固定知识")
        )
        uploaded = await knowledge.upload_document(
            created.id,
            DocumentUpload(
                file_name="demo-guide.txt",
                content_type="text/plain",
                content="Common Agent 是通用 Agent 中台。".encode(),
            ),
        )
        retrieved = await knowledge.retrieve(
            KnowledgeRetrievalRequest(knowledge_base_id=created.id, query="Common Agent 是什么?")
        )

        assert status.provider == "demo"
        assert status.availability is KnowledgeServiceAvailability.AVAILABLE
        assert (await knowledge.list_knowledge_bases())[0].document_count == 1
        assert (await knowledge.list_documents(created.id)) == (uploaded,)
        assert uploaded.parsing_status is DocumentParsingStatus.COMPLETED
        assert retrieved.chunks[0].document_name == "demo-guide.txt"
        assert retrieved.chunks[0].content == "Common Agent 是通用 Agent 中台。"
        with pytest.raises(KnowledgeRequestRejected):
            await knowledge.create_knowledge_base(
                CreateKnowledgeBaseRequest(name="演示知识库", description="重复名称")
            )
        await knowledge.aclose()

        reopened = DemoKnowledgeService(unit_of_work)
        assert (await reopened.get_knowledge_base(created.id)).document_count == 1
        assert (await reopened.list_documents(created.id)) == (uploaded,)
        assert (
            await reopened.retrieve(
                KnowledgeRetrievalRequest(
                    knowledge_base_id=created.id,
                    query="重启后还能检索吗?",
                )
            )
        ).chunks[0].content == "Common Agent 是通用 Agent 中台。"
        await reopened.aclose()

    asyncio.run(exercise())


def test_demo_runtime_is_deterministic_across_two_turns_and_interrupts_once() -> None:
    async def exercise() -> None:
        runtime = DemoEmployeeRuntime()
        first = await _events(runtime, _request("第一轮问题"))
        second = await _events(
            runtime,
            _request(
                "第二轮问题",
                assistant_message_id=UUID("e56c78e8-ee14-462e-8f66-ac7c1890ba1c"),
                previous_turn=True,
            ),
        )
        interrupted_request = _request(
            "请演示一次断流后恢复",
            assistant_message_id=UUID("ddc20b59-c12b-4e29-9836-b9cd8f89842d"),
        )
        interrupted = await _events(runtime, interrupted_request)
        retried = await _events(runtime, interrupted_request)
        stopped_token = RuntimeStopToken()
        stopped_token.request_stop()
        stopped = await _events(
            runtime,
            _request(
                "停止演示",
                assistant_message_id=UUID("681b6b25-fc4c-43b2-9e09-3a55bcae8b28"),
            ),
            stop=stopped_token,
        )

        assert first[-1].kind is RuntimeEventKind.COMPLETED
        assert "第 1 轮" in "".join(event.delta or "" for event in first)
        assert second[-1].kind is RuntimeEventKind.COMPLETED
        assert "上一轮" in "".join(event.delta or "" for event in second)
        assert [event.kind for event in interrupted] == [RuntimeEventKind.DELTA]
        assert retried[-1].kind is RuntimeEventKind.COMPLETED
        assert stopped[-1].kind is RuntimeEventKind.STOPPED
        await runtime.aclose()

    asyncio.run(exercise())
