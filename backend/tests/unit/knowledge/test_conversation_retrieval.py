from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import UUID

import pytest

from common_agent.domain.conversation import Message
from common_agent.domain.employee import Employee
from common_agent.domain.knowledge import (
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceAvailability,
    KnowledgeServiceStatus,
    RetrievedChunk,
)
from common_agent.knowledge.base import (
    KnowledgeBaseNotFound,
    KnowledgeConfigurationMissing,
    KnowledgeProviderResponseInvalid,
    KnowledgeRequestRejected,
    KnowledgeServiceError,
    KnowledgeServiceUnavailable,
    KnowledgeServiceVersionMismatch,
)
from common_agent.knowledge.retrieval import (
    ConversationKnowledgeRequestInvalid,
    ConversationKnowledgeResolver,
    ResolvedKnowledgeContext,
)
from common_agent.knowledge.service import KnowledgeBaseService
from tests.support.employees import default_employee_model_fields

EMPLOYEE_ID = UUID("ddbdad78-1128-4334-ad02-d28833357529")
CONVERSATION_ID = UUID("40b8bf77-fd8b-46ca-a103-5bebc29e185e")
MESSAGE_ID = UUID("3b2257d7-86fe-4abe-86c8-75388da202ae")
NOW = datetime(2026, 7, 20, tzinfo=UTC)
KNOWLEDGE_MARKER = "A4-05-sensitive-knowledge-marker"


class _KnowledgeProbe:
    provider_name = "probe"

    def __init__(
        self,
        results: Sequence[KnowledgeRetrievalResult] = (),
        *,
        failure: Exception | None = None,
        status: KnowledgeServiceStatus | None = None,
    ) -> None:
        self.results = list(results)
        self.failure = failure
        self.requests: list[KnowledgeRetrievalRequest] = []
        self.status_result = status or KnowledgeServiceStatus(
            provider=self.provider_name,
            availability=KnowledgeServiceAvailability.AVAILABLE,
            version="v0.26.4",
        )
        self.status_calls = 0

    async def status(self) -> KnowledgeServiceStatus:
        self.status_calls += 1
        return self.status_result

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        self.requests.append(request)
        if self.failure is not None:
            raise self.failure
        if not self.results:
            raise AssertionError("测试未配置检索结果")
        return self.results.pop(0)


def _employee(*, knowledge_base_id: str | None) -> Employee:
    return Employee.create(
        employee_id=EMPLOYEE_ID,
        name="知识助理",
        system_prompt="根据知识库回答。",
        **default_employee_model_fields(),
        knowledge_base_id=knowledge_base_id,
        now=NOW,
    )


def _user_message(*, content: str = "当前问题") -> Message:
    return Message.create_user(
        message_id=MESSAGE_ID,
        conversation_id=CONVERSATION_ID,
        sequence_number=1,
        content=content,
        now=NOW,
    )


def _result(*chunks: RetrievedChunk) -> KnowledgeRetrievalResult:
    return KnowledgeRetrievalResult(chunks=chunks)


def test_unbound_employee_skips_retrieval_and_preserves_unbound_semantics() -> None:
    knowledge = _KnowledgeProbe()
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]

    resolved = asyncio.run(resolver.resolve(_employee(knowledge_base_id=None), _user_message()))

    assert knowledge.requests == []
    assert knowledge.status_calls == 0
    assert resolved.knowledge_base_id is None
    assert resolved.runtime_chunks == ()
    assert resolved.citations == ()


def test_bound_employee_retrieves_every_message_and_maps_runtime_context_and_citations() -> None:
    first = RetrievedChunk(
        id="chunk-1",
        document_id="document-1",
        document_name="员工手册.md",
        content=f"第一段 {KNOWLEDGE_MARKER}",
        score=0.93,
    )
    second = RetrievedChunk(
        id="chunk-2",
        document_id="document-2",
        document_name="补充说明.md",
        content="第二段",
        score=0.81,
    )
    knowledge = _KnowledgeProbe([_result(first, second), _result(second)])
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]
    employee = _employee(knowledge_base_id="kb-bound")

    async def exercise() -> tuple[ResolvedKnowledgeContext, ResolvedKnowledgeContext]:
        return (
            await resolver.resolve(employee, _user_message(content="第一问")),
            await resolver.resolve(employee, _user_message(content="第二问")),
        )

    first_resolved, second_resolved = asyncio.run(exercise())

    assert [(request.knowledge_base_id, request.query) for request in knowledge.requests] == [
        ("kb-bound", "第一问"),
        ("kb-bound", "第二问"),
    ]
    assert knowledge.status_calls == 2
    assert all(request.top_k == 5 for request in knowledge.requests)
    assert all(request.similarity_threshold == 0.2 for request in knowledge.requests)
    assert first_resolved.knowledge_base_id == "kb-bound"
    assert [chunk.chunk_id for chunk in first_resolved.runtime_chunks] == ["chunk-1", "chunk-2"]
    assert [citation.position for citation in first_resolved.citations] == [1, 2]
    assert [citation.chunk_id for citation in first_resolved.citations] == ["chunk-1", "chunk-2"]
    assert first_resolved.runtime_chunks[0].content == first_resolved.citations[0].content
    assert second_resolved.runtime_chunks[0].chunk_id == "chunk-2"
    assert KNOWLEDGE_MARKER not in repr(first_resolved)
    assert KNOWLEDGE_MARKER not in repr(first_resolved.citations[0])


def test_runtime_rechecks_knowledge_ownership_before_every_employee_retrieval() -> None:
    class DenyingOwnership:
        async def owns(self, tenant_id: UUID, knowledge_base_id: str) -> bool:
            del tenant_id, knowledge_base_id
            return False

        async def list_ids(self, tenant_id: UUID) -> frozenset[str]:
            del tenant_id
            return frozenset()

        async def claim_legacy(
            self,
            tenant_id: UUID,
            knowledge_base_ids: tuple[str, ...],
            *,
            now: datetime,
        ) -> None:
            del tenant_id, knowledge_base_ids, now

        async def assign(self, tenant_id: UUID, knowledge_base_id: str, *, now: datetime) -> None:
            del tenant_id, knowledge_base_id, now

        async def release(self, tenant_id: UUID, knowledge_base_id: str) -> None:
            del tenant_id, knowledge_base_id

    knowledge = _KnowledgeProbe([_result()])
    guarded = KnowledgeBaseService(
        knowledge,  # type: ignore[arg-type]
        ownership=DenyingOwnership(),
        tenant_id_provider=lambda: UUID("10000000-0000-4000-8000-000000000002"),
    )
    resolver = ConversationKnowledgeResolver(guarded)

    with pytest.raises(KnowledgeBaseNotFound):
        asyncio.run(resolver.resolve(_employee(knowledge_base_id="foreign-kb"), _user_message()))

    assert knowledge.requests == []


def test_empty_retrieval_keeps_bound_knowledge_base_semantics() -> None:
    knowledge = _KnowledgeProbe([_result()])
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]

    resolved = asyncio.run(
        resolver.resolve(_employee(knowledge_base_id="kb-empty"), _user_message())
    )

    assert len(knowledge.requests) == 1
    assert knowledge.status_calls == 1
    assert resolved.knowledge_base_id == "kb-empty"
    assert resolved.runtime_chunks == ()
    assert resolved.citations == ()


def test_each_turn_uses_the_employee_current_knowledge_binding_without_stale_cache() -> None:
    first = RetrievedChunk("chunk-a", "doc-a", "A.md", "A 库内容", 0.9)
    second = RetrievedChunk("chunk-b", "doc-b", "B.md", "B 库内容", 0.9)
    knowledge = _KnowledgeProbe([_result(first), _result(second)])
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]

    async def exercise() -> tuple[ResolvedKnowledgeContext, ResolvedKnowledgeContext]:
        return (
            await resolver.resolve(_employee(knowledge_base_id="kb-a"), _user_message()),
            await resolver.resolve(_employee(knowledge_base_id="kb-b"), _user_message()),
        )

    first_resolved, second_resolved = asyncio.run(exercise())

    assert [request.knowledge_base_id for request in knowledge.requests] == ["kb-a", "kb-b"]
    assert first_resolved.knowledge_base_id == "kb-a"
    assert second_resolved.knowledge_base_id == "kb-b"
    assert first_resolved.citations[0].chunk_id == "chunk-a"
    assert second_resolved.citations[0].chunk_id == "chunk-b"


@pytest.mark.parametrize(
    "failure",
    [
        KnowledgeConfigurationMissing(),
        KnowledgeServiceUnavailable(),
        KnowledgeServiceVersionMismatch(),
        KnowledgeBaseNotFound(),
        KnowledgeRequestRejected(),
        KnowledgeProviderResponseInvalid(),
    ],
)
def test_known_knowledge_failure_is_propagated_without_silent_fallback(
    failure: KnowledgeServiceError,
) -> None:
    knowledge = _KnowledgeProbe(failure=failure)
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]

    with pytest.raises(type(failure)) as captured:
        asyncio.run(resolver.resolve(_employee(knowledge_base_id="kb-failure"), _user_message()))

    assert captured.value is failure
    assert len(knowledge.requests) == 1


@pytest.mark.parametrize(
    ("status", "error_type"),
    [
        (
            KnowledgeServiceStatus(
                provider="probe",
                availability=KnowledgeServiceAvailability.NOT_CONFIGURED,
                version=None,
                error_code="configuration_missing",
            ),
            KnowledgeConfigurationMissing,
        ),
        (
            KnowledgeServiceStatus(
                provider="probe",
                availability=KnowledgeServiceAvailability.UNAVAILABLE,
                version="v0.24.0",
                error_code="knowledge_service_version_mismatch",
            ),
            KnowledgeServiceVersionMismatch,
        ),
        (
            KnowledgeServiceStatus(
                provider="probe",
                availability=KnowledgeServiceAvailability.UNAVAILABLE,
                version=None,
                error_code="knowledge_service_unavailable",
            ),
            KnowledgeServiceUnavailable,
        ),
    ],
)
def test_unavailable_or_incompatible_service_fails_before_retrieval(
    status: KnowledgeServiceStatus,
    error_type: type[KnowledgeServiceError],
) -> None:
    knowledge = _KnowledgeProbe(status=status)
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]

    with pytest.raises(error_type):
        asyncio.run(resolver.resolve(_employee(knowledge_base_id="kb-bound"), _user_message()))

    assert knowledge.status_calls == 1
    assert knowledge.requests == []


def test_unknown_retrieval_failure_becomes_safe_unavailable_error() -> None:
    knowledge = _KnowledgeProbe(failure=RuntimeError("provider detail must not leak"))
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]

    with pytest.raises(KnowledgeServiceUnavailable) as captured:
        asyncio.run(resolver.resolve(_employee(knowledge_base_id="kb-failure"), _user_message()))

    assert "provider detail" not in repr(captured.value)
    assert captured.value.__suppress_context__ is True


@pytest.mark.parametrize(
    "chunks",
    [
        (
            RetrievedChunk("duplicate", "doc-1", "a.md", "内容一", 0.9),
            RetrievedChunk("duplicate", "doc-2", "b.md", "内容二", 0.8),
        ),
        (RetrievedChunk("bad-score", "doc-1", "a.md", "内容", 1.1),),
        (RetrievedChunk("oversized", "doc-1", "a.md", "内容" * 7_000, 0.9),),
        tuple(RetrievedChunk(f"chunk-{index}", "doc-1", "a.md", "内容", 0.9) for index in range(6)),
    ],
)
def test_invalid_provider_chunks_fail_closed(chunks: tuple[RetrievedChunk, ...]) -> None:
    knowledge = _KnowledgeProbe([KnowledgeRetrievalResult(chunks=chunks)])
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]

    with pytest.raises(KnowledgeProviderResponseInvalid):
        asyncio.run(resolver.resolve(_employee(knowledge_base_id="kb-invalid"), _user_message()))


def test_non_user_message_is_rejected_before_retrieval() -> None:
    knowledge = _KnowledgeProbe()
    resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]
    assistant = Message.create_assistant(
        message_id=MESSAGE_ID,
        conversation_id=CONVERSATION_ID,
        sequence_number=1,
        now=NOW,
    )

    with pytest.raises(ConversationKnowledgeRequestInvalid):
        asyncio.run(resolver.resolve(_employee(knowledge_base_id="kb-bound"), assistant))

    assert knowledge.requests == []


def test_parent_cancellation_is_not_converted_to_a_knowledge_failure() -> None:
    class BlockingKnowledge(_KnowledgeProbe):
        def __init__(self) -> None:
            super().__init__()
            self.started = asyncio.Event()

        async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
            self.requests.append(request)
            self.started.set()
            await asyncio.Event().wait()
            raise AssertionError("不可到达")

    async def exercise() -> None:
        knowledge = BlockingKnowledge()
        resolver = ConversationKnowledgeResolver(knowledge)  # type: ignore[arg-type]
        task = asyncio.create_task(
            resolver.resolve(_employee(knowledge_base_id="kb-bound"), _user_message())
        )
        await asyncio.wait_for(knowledge.started.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(exercise())
