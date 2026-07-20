from __future__ import annotations

from pathlib import PurePosixPath

from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceAvailability,
)
from common_agent.knowledge.base import (
    KnowledgeConfigurationMissing,
    KnowledgeService,
    KnowledgeServiceUnavailable,
    KnowledgeServiceVersionMismatch,
    PageableKnowledgeService,
)
from common_agent.pagination import CursorPage, ListPageRequest

MAX_DOCUMENT_SIZE_BYTES = 20 * 1024 * 1024

_SUPPORTED_DOCUMENT_TYPES: dict[str, frozenset[str]] = {
    ".docx": frozenset({"application/vnd.openxmlformats-officedocument.wordprocessingml.document"}),
    ".markdown": frozenset({"text/markdown", "text/plain"}),
    ".md": frozenset({"text/markdown", "text/plain"}),
    ".pdf": frozenset({"application/pdf"}),
    ".txt": frozenset({"text/plain"}),
}


class KnowledgeInputError(Exception):
    code: str
    message: str
    status_code: int

    def __init__(self) -> None:
        super().__init__(self.message)


class EmptyDocument(KnowledgeInputError):
    code = "empty_document"
    message = "文档内容不能为空"
    status_code = 422


class UnsupportedDocumentType(KnowledgeInputError):
    code = "unsupported_document_type"
    message = "仅支持 TXT、Markdown、PDF 和 DOCX 文档"
    status_code = 415


class DocumentTooLarge(KnowledgeInputError):
    code = "document_too_large"
    message = "文档大小不能超过 20 MiB"
    status_code = 413


class KnowledgeBaseService:
    def __init__(self, knowledge: KnowledgeService) -> None:
        self._knowledge = knowledge

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        await self._ensure_available()
        return await self._knowledge.list_knowledge_bases()

    async def page_knowledge_bases(
        self,
        page: ListPageRequest,
    ) -> CursorPage[KnowledgeBaseSummary]:
        await self._ensure_available()
        if not isinstance(self._knowledge, PageableKnowledgeService):
            raise KnowledgeServiceUnavailable()
        return await self._knowledge.page_knowledge_bases(page)

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        await self._ensure_available()
        return await self._knowledge.get_knowledge_base(knowledge_base_id)

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        await self._ensure_available()
        return await self._knowledge.create_knowledge_base(request)

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        await self._ensure_available()
        await self._knowledge.delete_knowledge_base(knowledge_base_id)

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        await self._ensure_available()
        return await self._knowledge.list_documents(knowledge_base_id)

    async def upload_document(
        self,
        knowledge_base_id: str,
        upload: DocumentUpload,
    ) -> KnowledgeDocument:
        self._validate_upload(upload)
        await self._ensure_available()
        return await self._knowledge.upload_document(knowledge_base_id, upload)

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        await self._ensure_available()
        return await self._knowledge.retrieve(request)

    async def _ensure_available(self) -> None:
        status = await self._knowledge.status()
        if status.availability is KnowledgeServiceAvailability.AVAILABLE:
            return
        if status.availability is KnowledgeServiceAvailability.NOT_CONFIGURED:
            raise KnowledgeConfigurationMissing()
        if status.error_code == KnowledgeServiceVersionMismatch.code:
            raise KnowledgeServiceVersionMismatch()
        raise KnowledgeServiceUnavailable()

    @staticmethod
    def _validate_upload(upload: DocumentUpload) -> None:
        normalized_name = upload.file_name.replace("\\", "/")
        extension = PurePosixPath(normalized_name).suffix.lower()
        accepted_content_types = _SUPPORTED_DOCUMENT_TYPES.get(extension)
        if (
            accepted_content_types is None
            or upload.content_type.lower() not in accepted_content_types
        ):
            raise UnsupportedDocumentType()
        if upload.size_bytes == 0:
            raise EmptyDocument()
        if upload.size_bytes > MAX_DOCUMENT_SIZE_BYTES:
            raise DocumentTooLarge()
