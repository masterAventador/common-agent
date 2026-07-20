from __future__ import annotations

from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import uuid4

from common_agent.domain.conversation import CITATION_CONTENT_MAX_LENGTH
from common_agent.domain.knowledge import (
    KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH,
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceAvailability,
    KnowledgeServiceStatus,
    RetrievedChunk,
)
from common_agent.knowledge.base import (
    KnowledgeBaseNotFound,
    KnowledgeDocumentUploadFailed,
    KnowledgeRequestRejected,
)
from common_agent.ports.knowledge import (
    DemoKnowledgeBaseAlreadyExists,
    DemoKnowledgeUnitOfWorkFactory,
    DemoKnowledgeWriteConflict,
    PersistedDemoKnowledgeBase,
    PersistedDemoKnowledgeDocument,
)


class DemoKnowledgeService:
    provider_name = "demo"

    def __init__(self, unit_of_work: DemoKnowledgeUnitOfWorkFactory) -> None:
        self._unit_of_work = unit_of_work
        self._closed = False

    async def status(self) -> KnowledgeServiceStatus:
        self._ensure_open()
        return KnowledgeServiceStatus(
            provider=self.provider_name,
            availability=KnowledgeServiceAvailability.AVAILABLE,
            version="demo-1",
        )

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        self._ensure_open()
        async with self._unit_of_work() as unit_of_work:
            values = await unit_of_work.knowledge.list_knowledge_bases()
        return tuple(value.summary for value in values)

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        self._ensure_open()
        async with self._unit_of_work() as unit_of_work:
            value = await unit_of_work.knowledge.get_knowledge_base(knowledge_base_id)
        if value is None:
            raise KnowledgeBaseNotFound()
        return value.summary

    async def create_knowledge_base(
        self,
        request: CreateKnowledgeBaseRequest,
    ) -> KnowledgeBaseSummary:
        self._ensure_open()
        created = PersistedDemoKnowledgeBase(
            summary=KnowledgeBaseSummary(
                id=uuid4().hex,
                name=request.name,
                description=request.description,
                document_count=0,
                parsing_count=0,
            ),
            created_at=datetime.now(UTC),
        )
        try:
            async with self._unit_of_work() as unit_of_work:
                await unit_of_work.knowledge.add_knowledge_base(created)
                await unit_of_work.commit()
        except DemoKnowledgeBaseAlreadyExists:
            raise KnowledgeRequestRejected() from None
        return created.summary

    async def upload_document(
        self,
        knowledge_base_id: str,
        upload: DocumentUpload,
    ) -> KnowledgeDocument:
        self._ensure_open()
        name = PurePosixPath(upload.file_name.replace("\\", "/")).name
        if not name or name in {".", ".."} or len(name) > KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH:
            raise KnowledgeDocumentUploadFailed()
        document = KnowledgeDocument(
            id=uuid4().hex,
            knowledge_base_id=knowledge_base_id,
            name=name,
            size_bytes=upload.size_bytes,
            parsing_status=DocumentParsingStatus.COMPLETED,
            error_code=None,
        )
        persisted = PersistedDemoKnowledgeDocument(
            document=document,
            content=upload.content.decode("utf-8", errors="replace").strip(),
            created_at=datetime.now(UTC),
        )
        try:
            async with self._unit_of_work() as unit_of_work:
                if await unit_of_work.knowledge.get_knowledge_base(knowledge_base_id) is None:
                    raise KnowledgeBaseNotFound()
                await unit_of_work.knowledge.add_document(persisted)
                await unit_of_work.commit()
        except DemoKnowledgeWriteConflict:
            raise KnowledgeDocumentUploadFailed() from None
        return document

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        self._ensure_open()
        async with self._unit_of_work() as unit_of_work:
            if await unit_of_work.knowledge.get_knowledge_base(knowledge_base_id) is None:
                raise KnowledgeBaseNotFound()
            documents = await unit_of_work.knowledge.list_documents(knowledge_base_id)
        return tuple(item.document for item in documents)

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        self._ensure_open()
        async with self._unit_of_work() as unit_of_work:
            if await unit_of_work.knowledge.get_knowledge_base(request.knowledge_base_id) is None:
                raise KnowledgeBaseNotFound()
            documents = await unit_of_work.knowledge.list_documents(request.knowledge_base_id)
        available_documents = (item for item in documents if item.content)
        return KnowledgeRetrievalResult(
            chunks=tuple(
                RetrievedChunk(
                    id=f"demo-{item.document.id}",
                    document_id=item.document.id,
                    document_name=item.document.name,
                    content=item.content[:CITATION_CONTENT_MAX_LENGTH],
                    score=max(request.similarity_threshold, 1.0 - index * 0.05),
                )
                for index, item in enumerate(available_documents)
                if index < request.top_k
            )
        )

    async def aclose(self) -> None:
        self._closed = True

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("demo knowledge service is closed")
