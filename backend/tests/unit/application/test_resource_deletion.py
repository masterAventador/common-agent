from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from uuid import UUID

import pytest

from common_agent.application.resource_deletion import (
    EmployeeHasConversations,
    KnowledgeBaseHasEmployeeBindings,
    KnowledgeBaseHasWorkflowReferences,
    ResourceDeletionService,
    WorkflowHasActiveRuns,
    WorkflowHasEmployeeBindings,
)
from common_agent.application.resource_locks import ResourceMutationGuard
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceAvailability,
    KnowledgeServiceStatus,
)
from common_agent.knowledge.base import (
    KnowledgeBaseDeleteResultUnknown,
    KnowledgeBaseNotFound,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.resources import (
    KnowledgeBaseReferences,
    LocalDeleteBlock,
    LocalDeleteResult,
    WorkflowReferences,
)

EMPLOYEE_ID = UUID("4af2d374-28a2-4380-aec6-43f8fc6eb489")
WORKFLOW_ID = UUID("87be1a34-b48c-467c-a4e3-4eff5ec1a48c")


class _ResourceStoreProbe:
    def __init__(self) -> None:
        self.employee_result = LocalDeleteResult(deleted=True)
        self.workflow_result = LocalDeleteResult(deleted=True)
        self.knowledge_references = KnowledgeBaseReferences()
        self.workflow_references = WorkflowReferences()
        self.employee_deletes: list[UUID] = []
        self.workflow_deletes: list[UUID] = []

    async def delete_employee(self, employee_id: UUID) -> LocalDeleteResult:
        self.employee_deletes.append(employee_id)
        return self.employee_result

    async def get_knowledge_base_references(
        self, knowledge_base_id: str
    ) -> KnowledgeBaseReferences:
        del knowledge_base_id
        return self.knowledge_references

    async def delete_workflow(self, workflow_id: UUID) -> LocalDeleteResult:
        self.workflow_deletes.append(workflow_id)
        return self.workflow_result

    async def get_workflow_references(self, workflow_id: UUID) -> WorkflowReferences:
        del workflow_id
        return self.workflow_references


class _KnowledgeProbe:
    provider_name = "probe"

    def __init__(self) -> None:
        self.values = {
            "kb-1": KnowledgeBaseSummary(
                id="kb-1",
                name="待删除知识库",
                description="",
                document_count=1,
                parsing_count=0,
            )
        }
        self.delete_calls: list[str] = []
        self.delete_effect: Callable[[str], Awaitable[None]] | None = None

    async def status(self) -> KnowledgeServiceStatus:
        return KnowledgeServiceStatus(
            provider=self.provider_name,
            availability=KnowledgeServiceAvailability.AVAILABLE,
            version="probe-1",
        )

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        try:
            return self.values[knowledge_base_id]
        except KeyError:
            raise KnowledgeBaseNotFound from None

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        self.delete_calls.append(knowledge_base_id)
        if self.delete_effect is not None:
            await self.delete_effect(knowledge_base_id)
            return
        self.values.pop(knowledge_base_id, None)

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        return tuple(self.values.values())

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        del request
        raise NotImplementedError

    async def upload_document(
        self, knowledge_base_id: str, upload: DocumentUpload
    ) -> KnowledgeDocument:
        del knowledge_base_id, upload
        raise NotImplementedError

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        del knowledge_base_id
        raise NotImplementedError

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        del request
        return KnowledgeRetrievalResult(chunks=())


def _service() -> tuple[ResourceDeletionService, _ResourceStoreProbe, _KnowledgeProbe]:
    store = _ResourceStoreProbe()
    knowledge = _KnowledgeProbe()
    service = ResourceDeletionService(
        store,
        KnowledgeBaseService(knowledge),
        guard=ResourceMutationGuard(),
    )
    return service, store, knowledge


def test_employee_delete_is_idempotent_and_refuses_conversation_references() -> None:
    service, store, _ = _service()

    async def exercise() -> None:
        store.employee_result = LocalDeleteResult(
            deleted=False,
            blocked_by=LocalDeleteBlock.EMPLOYEE_CONVERSATIONS,
        )
        with pytest.raises(EmployeeHasConversations):
            await service.delete_employee(EMPLOYEE_ID)

        store.employee_result = LocalDeleteResult(deleted=True)
        assert await service.delete_employee(EMPLOYEE_ID) is True
        store.employee_result = LocalDeleteResult(deleted=False)
        assert await service.delete_employee(EMPLOYEE_ID) is False

    asyncio.run(exercise())
    assert store.employee_deletes == [EMPLOYEE_ID, EMPLOYEE_ID, EMPLOYEE_ID]


@pytest.mark.parametrize(
    ("references", "error_type"),
    [
        (KnowledgeBaseReferences(employee_bindings=2), KnowledgeBaseHasEmployeeBindings),
        (KnowledgeBaseReferences(workflow_nodes=1), KnowledgeBaseHasWorkflowReferences),
    ],
)
def test_knowledge_base_delete_refuses_live_platform_references(
    references: KnowledgeBaseReferences,
    error_type: type[Exception],
) -> None:
    service, store, knowledge = _service()
    store.knowledge_references = references

    async def exercise() -> None:
        with pytest.raises(error_type):
            await service.delete_knowledge_base("kb-1")

    asyncio.run(exercise())
    assert knowledge.delete_calls == []


def test_unknown_knowledge_delete_is_reconciled_by_an_idempotent_retry() -> None:
    service, _, knowledge = _service()

    async def delete_then_lose_response(knowledge_base_id: str) -> None:
        knowledge.values.pop(knowledge_base_id)
        raise KnowledgeBaseDeleteResultUnknown

    knowledge.delete_effect = delete_then_lose_response

    async def exercise() -> None:
        with pytest.raises(KnowledgeBaseDeleteResultUnknown):
            await service.delete_knowledge_base("kb-1")
        assert await service.delete_knowledge_base("kb-1") is False

    asyncio.run(exercise())
    assert knowledge.delete_calls == ["kb-1"]


@pytest.mark.parametrize(
    ("references", "error_type"),
    [
        (WorkflowReferences(employee_bindings=1), WorkflowHasEmployeeBindings),
        (WorkflowReferences(active_runs=1), WorkflowHasActiveRuns),
    ],
)
def test_workflow_delete_refuses_employee_bindings_and_active_runs(
    references: WorkflowReferences,
    error_type: type[Exception],
) -> None:
    service, store, _ = _service()
    store.workflow_references = references

    async def exercise() -> None:
        with pytest.raises(error_type):
            await service.delete_workflow(WORKFLOW_ID)

    asyncio.run(exercise())
    assert store.workflow_deletes == []


def test_workflow_delete_is_idempotent_after_reference_check() -> None:
    service, store, _ = _service()

    async def exercise() -> None:
        assert await service.delete_workflow(WORKFLOW_ID) is True
        store.workflow_result = LocalDeleteResult(deleted=False)
        assert await service.delete_workflow(WORKFLOW_ID) is False

    asyncio.run(exercise())


def test_resource_guard_serializes_equal_keys_but_not_unrelated_resources() -> None:
    guard = ResourceMutationGuard()
    first_entered = asyncio.Event()
    release_first = asyncio.Event()
    second_entered = asyncio.Event()
    unrelated_entered = asyncio.Event()

    async def first() -> None:
        async with guard.hold("knowledge:kb-1"):
            first_entered.set()
            await release_first.wait()

    async def second() -> None:
        await first_entered.wait()
        async with guard.hold("knowledge:kb-1"):
            second_entered.set()

    async def unrelated() -> None:
        await first_entered.wait()
        async with guard.hold("workflow:1"):
            unrelated_entered.set()

    async def exercise() -> None:
        tasks = [asyncio.create_task(operation()) for operation in (first, second, unrelated)]
        await first_entered.wait()
        await asyncio.wait_for(unrelated_entered.wait(), timeout=1)
        assert second_entered.is_set() is False
        release_first.set()
        await asyncio.gather(*tasks)
        assert second_entered.is_set() is True

    asyncio.run(exercise())
