from __future__ import annotations

import asyncio
from datetime import datetime
from uuid import UUID

import pytest

from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceAvailability,
    KnowledgeServiceStatus,
)
from common_agent.knowledge.base import (
    DocumentChunk,
    KnowledgeBaseNotFound,
    KnowledgeDocumentNotFound,
    KnowledgeDocumentRetryRejected,
    UpdateKnowledgeBaseRequest,
)
from common_agent.knowledge.service import (
    MAX_DOCUMENT_SIZE_BYTES,
    DocumentTooLarge,
    EmptyDocument,
    KnowledgeBaseService,
    UnsupportedDocumentType,
)
from common_agent.pagination import CursorPage, ListPageRequest
from common_agent.tenancy.constants import DEFAULT_TENANT_ID


class _KnowledgeProbe:
    provider_name = "probe"

    def __init__(self) -> None:
        self.status_result = KnowledgeServiceStatus(
            provider=self.provider_name,
            availability=KnowledgeServiceAvailability.AVAILABLE,
            version="v0.26.4",
        )
        self.uploads: list[DocumentUpload] = []
        self.retrieval_requests: list[KnowledgeRetrievalRequest] = []
        self.retrieval_result = KnowledgeRetrievalResult(chunks=())
        self.knowledge_bases: list[KnowledgeBaseSummary] = []
        self.get_calls: list[str] = []
        self.deleted: list[str] = []
        self.updated: list[tuple[str, UpdateKnowledgeBaseRequest]] = []
        self.chunks: list[DocumentChunk] = []
        self.chunk_calls: list[tuple[str, str, ListPageRequest]] = []
        self.page_calls: list[ListPageRequest] = []

    async def status(self) -> KnowledgeServiceStatus:
        return self.status_result

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        return tuple(self.knowledge_bases)

    async def page_knowledge_bases(
        self,
        page: ListPageRequest,
    ) -> CursorPage[KnowledgeBaseSummary]:
        self.page_calls.append(page)
        offset = int(page.cursor or "0")
        values = tuple(
            value
            for value in self.knowledge_bases
            if not page.search or page.search.casefold() in value.name.casefold()
        )
        items = values[offset : offset + page.limit]
        next_offset = offset + len(items)
        return CursorPage(
            items=items,
            next_cursor=str(next_offset) if next_offset < len(values) else None,
        )

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

    async def update_knowledge_base(
        self, knowledge_base_id: str, request: UpdateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        self.updated.append((knowledge_base_id, request))
        for index, value in enumerate(self.knowledge_bases):
            if value.id != knowledge_base_id:
                continue
            renamed = KnowledgeBaseSummary(
                id=value.id,
                name=request.name,
                description=request.description,
                document_count=value.document_count,
                parsing_count=value.parsing_count,
            )
            self.knowledge_bases[index] = renamed
            return renamed
        raise AssertionError("知识库不存在")

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        self.deleted.append(knowledge_base_id)

    async def list_document_chunks(
        self, knowledge_base_id: str, document_id: str, page: ListPageRequest
    ) -> CursorPage[DocumentChunk]:
        self.chunk_calls.append((knowledge_base_id, document_id, page))
        return CursorPage(items=tuple(self.chunks), next_cursor=None)

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


class _RetryKnowledgeProbe(_KnowledgeProbe):
    def __init__(self) -> None:
        super().__init__()
        self.documents: tuple[KnowledgeDocument, ...] = (
            KnowledgeDocument(
                id="doc-failed",
                knowledge_base_id="kb-1",
                name="failed.pdf",
                size_bytes=128,
                parsing_status=DocumentParsingStatus.FAILED,
                error_code="document_parsing_failed",
            ),
        )
        self.retried: list[tuple[str, KnowledgeDocument]] = []
        self.document_lookups: list[tuple[str, str]] = []

    async def get_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> KnowledgeDocument | None:
        self.document_lookups.append((knowledge_base_id, document_id))
        return next((document for document in self.documents if document.id == document_id), None)

    async def retry_document(
        self,
        knowledge_base_id: str,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        self.retried.append((knowledge_base_id, document))
        return KnowledgeDocument(
            id=document.id,
            knowledge_base_id=knowledge_base_id,
            name="failed.pdf",
            size_bytes=128,
            parsing_status=DocumentParsingStatus.PARSING,
            error_code=None,
        )


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


def test_retry_document_requires_owned_failed_document_before_calling_provider() -> None:
    tenant_id = UUID("10000000-0000-4000-8000-000000000099")
    probe = _RetryKnowledgeProbe()
    ownership = _OwnershipProbe()
    ownership.values = {tenant_id: {"kb-1"}}
    service = KnowledgeBaseService(
        probe,
        ownership=ownership,
        tenant_id_provider=lambda: tenant_id,
    )

    retried = asyncio.run(service.retry_document("kb-1", "doc-failed"))

    assert retried.parsing_status is DocumentParsingStatus.PARSING
    assert probe.document_lookups == [("kb-1", "doc-failed")]
    assert [(knowledge_base_id, document.id) for knowledge_base_id, document in probe.retried] == [
        ("kb-1", "doc-failed")
    ]


@pytest.mark.parametrize(
    ("documents", "error_type"),
    [
        ((), KnowledgeDocumentNotFound),
        (
            (
                KnowledgeDocument(
                    id="doc-failed",
                    knowledge_base_id="kb-1",
                    name="completed.pdf",
                    size_bytes=128,
                    parsing_status=DocumentParsingStatus.COMPLETED,
                    error_code=None,
                ),
            ),
            KnowledgeDocumentRetryRejected,
        ),
    ],
)
def test_retry_document_rejects_missing_or_non_failed_document(
    documents: tuple[KnowledgeDocument, ...],
    error_type: type[Exception],
) -> None:
    probe = _RetryKnowledgeProbe()
    probe.documents = documents
    service = KnowledgeBaseService(probe)

    with pytest.raises(error_type):
        asyncio.run(service.retry_document("kb-1", "doc-failed"))

    assert probe.retried == []


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


def test_tenant_pagination_walks_provider_pages_beyond_the_first_hundred() -> None:
    class FirstPageOnlyProbe(_KnowledgeProbe):
        async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
            return tuple(self.knowledge_bases[:100])

    tenant_id = UUID("10000000-0000-4000-8000-000000000005")
    probe = FirstPageOnlyProbe()
    probe.knowledge_bases = [
        KnowledgeBaseSummary(f"kb-{index:03d}", f"制度-{index:03d}", "", 0, 0)
        for index in range(150)
    ]
    ownership = _OwnershipProbe()
    ownership.values = {tenant_id: {value.id for value in probe.knowledge_bases}}
    service = KnowledgeBaseService(
        probe,
        ownership=ownership,
        tenant_id_provider=lambda: tenant_id,
    )

    async def exercise() -> list[str]:
        cursor: str | None = None
        collected: list[str] = []
        while True:
            page = await service.page_knowledge_bases(ListPageRequest(limit=20, cursor=cursor))
            collected.extend(value.id for value in page.items)
            cursor = page.next_cursor
            if cursor is None:
                return collected

    assert asyncio.run(exercise()) == [f"kb-{index:03d}" for index in range(150)]
    assert len(probe.page_calls) >= 2


def test_knowledge_base_rename_is_blocked_across_tenants() -> None:
    tenant_a = UUID("10000000-0000-4000-8000-000000000005")
    tenant_b = UUID("10000000-0000-4000-8000-000000000006")
    selected = tenant_a
    probe = _KnowledgeProbe()
    probe.knowledge_bases = [
        KnowledgeBaseSummary("kb-a", "旧名称", "旧描述", 2, 0),
        KnowledgeBaseSummary("kb-b", "他人知识库", "", 0, 0),
    ]
    ownership = _OwnershipProbe()
    ownership.values = {tenant_a: {"kb-a"}, tenant_b: {"kb-b"}}
    service = KnowledgeBaseService(
        probe,
        ownership=ownership,
        tenant_id_provider=lambda: selected,
    )

    async def exercise() -> None:
        updated = await service.update_knowledge_base(
            "kb-a", UpdateKnowledgeBaseRequest(name="新名称", description="新描述")
        )
        assert updated.name == "新名称"
        assert updated.description == "新描述"
        # 文档统计不能因为改名归零
        assert updated.document_count == 2

        with pytest.raises(KnowledgeBaseNotFound):
            await service.update_knowledge_base(
                "kb-b", UpdateKnowledgeBaseRequest(name="越权改名", description="")
            )

    asyncio.run(exercise())
    assert [call[0] for call in probe.updated] == ["kb-a"]


def test_document_chunks_are_scoped_to_the_owning_tenant() -> None:
    tenant_a = UUID("10000000-0000-4000-8000-000000000007")
    tenant_b = UUID("10000000-0000-4000-8000-000000000008")
    selected = tenant_a
    probe = _KnowledgeProbe()
    probe.knowledge_bases = [
        KnowledgeBaseSummary("kb-a", "我的知识库", "", 1, 0),
        KnowledgeBaseSummary("kb-b", "他人知识库", "", 1, 0),
    ]
    probe.chunks = [
        DocumentChunk(id="chunk-1", document_id="doc-1", content="第一段正文", position=1),
        DocumentChunk(id="chunk-2", document_id="doc-1", content="第二段正文", position=2),
    ]
    ownership = _OwnershipProbe()
    ownership.values = {tenant_a: {"kb-a"}, tenant_b: {"kb-b"}}
    service = KnowledgeBaseService(
        probe,
        ownership=ownership,
        tenant_id_provider=lambda: selected,
    )

    async def exercise() -> None:
        page = await service.list_document_chunks(
            "kb-a", "doc-1", ListPageRequest(limit=20)
        )
        assert [chunk.content for chunk in page.items] == ["第一段正文", "第二段正文"]

        # 不能借别的工作区的知识库读切片
        with pytest.raises(KnowledgeBaseNotFound):
            await service.list_document_chunks("kb-b", "doc-1", ListPageRequest(limit=20))

    asyncio.run(exercise())
    assert [call[0] for call in probe.chunk_calls] == ["kb-a"]
