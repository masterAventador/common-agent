from __future__ import annotations

from dataclasses import dataclass, field

from common_agent.domain.conversation import Citation, Message, MessageRole
from common_agent.domain.employee import Employee
from common_agent.domain.knowledge import (
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    RetrievedChunk,
)
from common_agent.knowledge.base import (
    KnowledgeProviderResponseInvalid,
    KnowledgeService,
    KnowledgeServiceError,
    KnowledgeServiceUnavailable,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.runtimes.base import RuntimeKnowledgeChunk

CHAT_KNOWLEDGE_TOP_K = 5
CHAT_KNOWLEDGE_SIMILARITY_THRESHOLD = 0.2


class ConversationKnowledgeRequestInvalid(ValueError):
    code = "conversation_knowledge_request_invalid"
    retryable = False

    def __init__(self) -> None:
        super().__init__("会话知识检索只接受已完成的用户消息")


@dataclass(frozen=True, slots=True)
class ResolvedKnowledgeContext:
    knowledge_base_id: str | None
    runtime_chunks: tuple[RuntimeKnowledgeChunk, ...] = field(repr=False)
    citations: tuple[Citation, ...] = field(repr=False)


class ConversationKnowledgeResolver:
    def __init__(self, knowledge: KnowledgeService) -> None:
        self._knowledge = KnowledgeBaseService(knowledge)

    async def resolve(
        self,
        employee: Employee,
        user_message: Message,
    ) -> ResolvedKnowledgeContext:
        if user_message.role is not MessageRole.USER:
            raise ConversationKnowledgeRequestInvalid()
        if employee.knowledge_base_id is None:
            return ResolvedKnowledgeContext(
                knowledge_base_id=None,
                runtime_chunks=(),
                citations=(),
            )

        try:
            result = await self._knowledge.retrieve(
                KnowledgeRetrievalRequest(
                    knowledge_base_id=employee.knowledge_base_id,
                    query=user_message.content,
                    top_k=CHAT_KNOWLEDGE_TOP_K,
                    similarity_threshold=CHAT_KNOWLEDGE_SIMILARITY_THRESHOLD,
                )
            )
        except KnowledgeServiceError:
            raise
        except Exception:
            raise KnowledgeServiceUnavailable() from None

        runtime_chunks, citations = _map_chunks(employee.knowledge_base_id, result)
        return ResolvedKnowledgeContext(
            knowledge_base_id=employee.knowledge_base_id,
            runtime_chunks=runtime_chunks,
            citations=citations,
        )


def _map_chunks(
    knowledge_base_id: str,
    result: KnowledgeRetrievalResult,
) -> tuple[tuple[RuntimeKnowledgeChunk, ...], tuple[Citation, ...]]:
    if not isinstance(result, KnowledgeRetrievalResult):
        raise KnowledgeProviderResponseInvalid()
    if len(result.chunks) > CHAT_KNOWLEDGE_TOP_K:
        raise KnowledgeProviderResponseInvalid()
    if any(not isinstance(chunk, RetrievedChunk) for chunk in result.chunks):
        raise KnowledgeProviderResponseInvalid()

    chunk_ids = tuple(chunk.id for chunk in result.chunks)
    if len(set(chunk_ids)) != len(chunk_ids):
        raise KnowledgeProviderResponseInvalid()

    try:
        runtime_chunks = tuple(
            RuntimeKnowledgeChunk(
                knowledge_base_id=knowledge_base_id,
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                content=chunk.content,
                score=chunk.score,
            )
            for chunk in result.chunks
        )
        citations = tuple(
            Citation(
                position=position,
                knowledge_base_id=knowledge_base_id,
                chunk_id=chunk.id,
                document_id=chunk.document_id,
                document_name=chunk.document_name,
                content=chunk.content,
                score=chunk.score,
            )
            for position, chunk in enumerate(result.chunks, start=1)
        )
    except (AttributeError, TypeError, ValueError):
        raise KnowledgeProviderResponseInvalid() from None
    return runtime_chunks, citations
