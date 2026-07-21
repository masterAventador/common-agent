from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

import pytest

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
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.knowledge.service import (
    MAX_DOCUMENT_SIZE_BYTES,
    DocumentTooLarge,
    EmptyDocument,
    KnowledgeBaseService,
    UnsupportedDocumentType,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID


class _KnowledgeProbe:
    provider_name = "probe"

    def __init__(self) -> None:
        self.status_result = KnowledgeServiceStatus(
            provider=self.provider_name,
            availability=KnowledgeServiceAvailability.AVAILABLE,
            version="v0.25.6",
        )
        self.uploads: list[DocumentUpload] = []
        self.retrieval_requests: list[KnowledgeRetrievalRequest] = []
        self.retrieval_result = KnowledgeRetrievalResult(chunks=())
        self.knowledge_bases: list[KnowledgeBaseSummary] = []
        self.get_calls: list[str] = []
        self.deleted: list[str] = []

    async def status(self) -> KnowledgeServiceStatus:
        return self.status_result

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        return tuple(self.knowledge_bases)

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        self.get_calls.append(knowledge_base_id)
        return next(value for value in self.knowledge_bases if value.id == knowledge_base_id)

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        created = KnowledgeBaseSummary(
            id=f"created-{len(self.knowledge_bases) + 1}",
            name=request.name,
            description=request.description,
            document_count=0,
            parsing_count=0,
        )
        self.knowledge_bases.append(created)
        return created

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        self.deleted.append(knowledge_base_id)

    async def upload_document(
        self, knowledge_base_id: str, upload: DocumentUpload
    ) -> KnowledgeDocument:
        del knowledge_base_id
        self.uploads.append(upload)
        raise NotImplementedError

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        del knowledge_base_id
        raise NotImplementedError

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        self.retrieval_requests.append(request)
        return self.retrieval_result


class _OwnershipProbe:
    def __init__(self) -> None:
        self.values: dict[UUID, set[str]] = {}
        self.legacy_claims: list[tuple[UUID, tuple[str, ...]]] = []

    async def list_ids(self, tenant_id: UUID) -> frozenset[str]:
        return frozenset(self.values.get(tenant_id, set()))

    async def owns(self, tenant_id: UUID, knowledge_base_id: str) -> bool:
        return knowledge_base_id in self.values.get(tenant_id, set())

    async def claim(
        self,
        tenant_id: UUID,
        knowledge_base_id: str,
        *,
        now: datetime,
    ) -> bool:
        del now
        if any(knowledge_base_id in values for values in self.values.values()):
            return False
        self.values.setdefault(tenant_id, set()).add(knowledge_base_id)
        return True

    async def release(self, tenant_id: UUID, knowledge_base_id: str) -> None:
        self.values.setdefault(tenant_id, set()).discard(knowledge_base_id)

    async def claim_legacy(
        self,
        tenant_id: UUID,
        knowledge_base_ids: tuple[str, ...],
        *,
        now: datetime,
    ) -> None:
        del now
        self.legacy_claims.append((tenant_id, knowledge_base_ids))
        claimed = {value for values in self.values.values() for value in values}
        self.values.setdefault(tenant_id, set()).update(
            value for value in knowledge_base_ids if value not in claimed
        )


@pytest.mark.parametrize(
    ("upload", "error_type"),
    [
        (DocumentUpload("empty.md", "text/markdown", b""), EmptyDocument),
        (
            DocumentUpload(
                "large.txt",
                "text/plain",
                b"x" * (MAX_DOCUMENT_SIZE_BYTES + 1),
            ),
            DocumentTooLarge,
        ),
        (
            DocumentUpload("payload.exe", "application/octet-stream", b"binary"),
            UnsupportedDocumentType,
        ),
        (
            DocumentUpload("policy.pdf", "text/plain", b"not a pdf"),
            UnsupportedDocumentType,
        ),
    ],
)
def test_invalid_upload_is_rejected_before_calling_provider(
    upload: DocumentUpload,
    error_type: type[Exception],
) -> None:
    probe = _KnowledgeProbe()
    service = KnowledgeBaseService(probe)

    async def exercise() -> None:
        with pytest.raises(error_type):
            await service.upload_document("kb-1", upload)

    asyncio.run(exercise())
    assert probe.uploads == []


def test_retrieve_checks_service_availability_before_calling_provider() -> None:
    probe = _KnowledgeProbe()
    service = KnowledgeBaseService(probe)
    request = KnowledgeRetrievalRequest(knowledge_base_id="kb-1", query="年假有几天")

    result = asyncio.run(service.retrieve(request))

    assert result is probe.retrieval_result
    assert probe.retrieval_requests == [request]


def test_real_knowledge_ids_are_filtered_and_cross_tenant_get_fails_before_provider() -> None:
    tenant_a = UUID("10000000-0000-4000-8000-000000000001")
    tenant_b = UUID("10000000-0000-4000-8000-000000000002")
    selected = tenant_a
    probe = _KnowledgeProbe()
    probe.knowledge_bases = [
        KnowledgeBaseSummary("kb-a", "租户 A", "", 0, 0),
        KnowledgeBaseSummary("kb-b", "租户 B", "", 0, 0),
    ]
    ownership = _OwnershipProbe()
    ownership.values = {tenant_a: {"kb-a"}, tenant_b: {"kb-b"}}
    service = KnowledgeBaseService(
        probe,
        ownership=ownership,
        tenant_id_provider=lambda: selected,
    )

    async def exercise() -> None:
        assert [value.id for value in await service.list_knowledge_bases()] == ["kb-a"]
        with pytest.raises(KnowledgeBaseNotFound):
            await service.get_knowledge_base("kb-b")

    asyncio.run(exercise())
    assert probe.get_calls == []


def test_created_knowledge_base_is_claimed_by_current_tenant() -> None:
    tenant_id = UUID("10000000-0000-4000-8000-000000000003")
    probe = _KnowledgeProbe()
    ownership = _OwnershipProbe()
    service = KnowledgeBaseService(
        probe,
        ownership=ownership,
        tenant_id_provider=lambda: tenant_id,
    )

    created = asyncio.run(
        service.create_knowledge_base(
            CreateKnowledgeBaseRequest(name="新知识库", description="租户隔离")
        )
    )

    assert ownership.values == {tenant_id: {created.id}}
    assert probe.deleted == []


def test_only_default_tenant_adopts_unclaimed_legacy_ragflow_data() -> None:
    other_tenant = UUID("10000000-0000-4000-8000-000000000004")
    selected = other_tenant
    probe = _KnowledgeProbe()
    probe.knowledge_bases = [KnowledgeBaseSummary("legacy", "历史知识库", "", 0, 0)]
    ownership = _OwnershipProbe()
    service = KnowledgeBaseService(
        probe,
        ownership=ownership,
        tenant_id_provider=lambda: selected,
    )

    async def exercise() -> None:
        assert await service.list_knowledge_bases() == ()
        nonlocal selected
        selected = DEFAULT_TENANT_ID
        assert [value.id for value in await service.list_knowledge_bases()] == ["legacy"]

    asyncio.run(exercise())
    assert ownership.legacy_claims == [(DEFAULT_TENANT_ID, ("legacy",))]
