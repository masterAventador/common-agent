from __future__ import annotations

from uuid import UUID

from common_agent.domain.conversation import MessageRole
from common_agent.runtimes.base import (
    EmployeeRuntimeRequest,
    RuntimeConversationMessage,
    RuntimeKnowledgeChunk,
)

CONVERSATION_ID = UUID("67c58e55-85fd-4f01-b692-297720626ef5")
EMPLOYEE_ID = UUID("660f0dc2-a0c5-4e6b-86e7-a42dc151e24d")
ASSISTANT_MESSAGE_ID = UUID("fc36932c-e075-4b1e-92ed-bb9117e6db96")
WORKFLOW_ID = UUID("036e014d-2505-41ac-b68a-a41399c702af")
OTHER_WORKFLOW_ID = UUID("5724762b-8ec3-4718-9d25-55130f01f734")


def runtime_request(
    *,
    allowed_workflow_ids: tuple[UUID, ...] = (),
    knowledge_base_id: str | None = "kb-runtime",
    knowledge_context: tuple[RuntimeKnowledgeChunk, ...] | None = None,
    system_instruction: str = "直接回答问题,不使用工具。",
) -> EmployeeRuntimeRequest:
    history = (
        RuntimeConversationMessage(
            message_id=UUID("d62f2183-7cff-4bb3-b7f7-4b33d2752fbf"),
            sequence_number=1,
            role=MessageRole.USER,
            content="上一问",
        ),
        RuntimeConversationMessage(
            message_id=UUID("dc2ea207-36cf-438f-a070-c81350d54b52"),
            sequence_number=2,
            role=MessageRole.ASSISTANT,
            content="上一答",
        ),
        RuntimeConversationMessage(
            message_id=UUID("7760b594-eb9b-48f0-af57-f368964d7ea0"),
            sequence_number=3,
            role=MessageRole.USER,
            content="当前问题",
        ),
    )
    context = (
        RuntimeKnowledgeChunk(
            knowledge_base_id="kb-runtime",
            chunk_id="chunk-runtime",
            document_id="document-runtime",
            document_name="runtime-handbook.md",
            content="运行时验收知识是 COMMON_AGENT_A4_04_OK。",
            score=0.99,
        ),
    )
    return EmployeeRuntimeRequest(
        conversation_id=CONVERSATION_ID,
        employee_id=EMPLOYEE_ID,
        assistant_message_id=ASSISTANT_MESSAGE_ID,
        assistant_sequence_number=4,
        system_instruction=system_instruction,
        history=history,
        knowledge_base_id=knowledge_base_id,
        knowledge_context=context if knowledge_context is None else knowledge_context,
        allowed_workflow_ids=allowed_workflow_ids,
    )
