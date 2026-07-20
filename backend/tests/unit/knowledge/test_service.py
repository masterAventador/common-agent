from __future__ import annotations

import asyncio

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
from common_agent.knowledge.service import (
    MAX_DOCUMENT_SIZE_BYTES,
    DocumentTooLarge,
    EmptyDocument,
    KnowledgeBaseService,
    UnsupportedDocumentType,
)


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

    async def status(self) -> KnowledgeServiceStatus:
        return self.status_result

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        raise NotImplementedError

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        del knowledge_base_id
        raise NotImplementedError

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        del request
        raise NotImplementedError

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        del knowledge_base_id
        raise NotImplementedError

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
