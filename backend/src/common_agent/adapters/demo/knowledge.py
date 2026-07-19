from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import uuid4

from common_agent.domain.conversation import CITATION_CONTENT_MAX_LENGTH
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
    RetrievedChunk,
)
from common_agent.knowledge.base import (
    KnowledgeBaseNotFound,
    KnowledgeDocumentUploadFailed,
    KnowledgeRequestRejected,
)


@dataclass(frozen=True, slots=True)
class _DemoDocument:
    value: KnowledgeDocument
    text: str


class DemoKnowledgeService:
    provider_name = "demo"

    def __init__(self) -> None:
        self._bases: dict[str, CreateKnowledgeBaseRequest] = {}
        self._documents: dict[str, list[_DemoDocument]] = {}
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
        return tuple(
            self._summary(knowledge_base_id) for knowledge_base_id in reversed(self._bases)
        )

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        self._ensure_open()
        self._require_base(knowledge_base_id)
        return self._summary(knowledge_base_id)

    async def create_knowledge_base(
        self,
        request: CreateKnowledgeBaseRequest,
    ) -> KnowledgeBaseSummary:
        self._ensure_open()
        if any(item.name == request.name for item in self._bases.values()):
            raise KnowledgeRequestRejected()
        knowledge_base_id = uuid4().hex
        self._bases[knowledge_base_id] = request
        self._documents[knowledge_base_id] = []
        return self._summary(knowledge_base_id)

    async def upload_document(
        self,
        knowledge_base_id: str,
        upload: DocumentUpload,
    ) -> KnowledgeDocument:
        self._ensure_open()
        self._require_base(knowledge_base_id)
        name = PurePosixPath(upload.file_name.replace("\\", "/")).name
        if not name or name in {".", ".."}:
            raise KnowledgeDocumentUploadFailed()
        document = KnowledgeDocument(
            id=uuid4().hex,
            knowledge_base_id=knowledge_base_id,
            name=name,
            size_bytes=upload.size_bytes,
            parsing_status=DocumentParsingStatus.COMPLETED,
            error_code=None,
        )
        text = upload.content.decode("utf-8", errors="replace").strip()
        self._documents[knowledge_base_id].insert(0, _DemoDocument(document, text))
        return document

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        self._ensure_open()
        self._require_base(knowledge_base_id)
        return tuple(item.value for item in self._documents[knowledge_base_id])

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        self._ensure_open()
        self._require_base(request.knowledge_base_id)
        documents = (item for item in self._documents[request.knowledge_base_id] if item.text)
        return KnowledgeRetrievalResult(
            chunks=tuple(
                RetrievedChunk(
                    id=f"demo-{item.value.id}",
                    document_id=item.value.id,
                    document_name=item.value.name,
                    content=item.text[:CITATION_CONTENT_MAX_LENGTH],
                    score=max(request.similarity_threshold, 1.0 - index * 0.05),
                )
                for index, item in enumerate(documents)
                if index < request.top_k
            )
        )

    async def aclose(self) -> None:
        self._closed = True
        self._bases.clear()
        self._documents.clear()

    def _summary(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        request = self._bases[knowledge_base_id]
        documents = self._documents[knowledge_base_id]
        return KnowledgeBaseSummary(
            id=knowledge_base_id,
            name=request.name,
            description=request.description,
            document_count=len(documents),
            parsing_count=0,
        )

    def _require_base(self, knowledge_base_id: str) -> None:
        if knowledge_base_id not in self._bases:
            raise KnowledgeBaseNotFound()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("demo knowledge service is closed")
