from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime
from pathlib import PurePosixPath
from uuid import UUID

from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceAvailability,
)
from common_agent.knowledge.base import (
    KnowledgeBaseNotFound,
    KnowledgeConfigurationMissing,
    KnowledgeDocumentNotFound,
    KnowledgeDocumentRetryRejected,
    KnowledgeService,
    KnowledgeServiceUnavailable,
    KnowledgeServiceVersionMismatch,
    PageableKnowledgeService,
    RetryableKnowledgeService,
)
from common_agent.pagination import (
    CursorPage,
    ListPageRequest,
    decode_offset_cursor,
    encode_offset_cursor,
)
from common_agent.ports.knowledge_ownership import KnowledgeOwnershipStore
from common_agent.tenancy.constants import DEFAULT_TENANT_ID

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
    def __init__(
        self,
        knowledge: KnowledgeService,
        *,
        ownership: KnowledgeOwnershipStore | None = None,
        tenant_id_provider: Callable[[], UUID] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._knowledge = knowledge
        self._ownership = ownership
        self._tenant_id_provider = tenant_id_provider or (lambda: DEFAULT_TENANT_ID)
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        await self._ensure_available()
        ownership = self._ownership
        if ownership is None:
            return await self._knowledge.list_knowledge_bases()
        tenant_id = self._tenant_id_provider()
        collected: list[KnowledgeBaseSummary] = []
        async for values in self._provider_pages(search=""):
            collected.extend(values)
            await self._claim_legacy(tenant_id, values)
        allowed = await ownership.list_ids(tenant_id)
        return tuple(value for value in collected if value.id in allowed)

    async def page_knowledge_bases(
        self,
        page: ListPageRequest,
    ) -> CursorPage[KnowledgeBaseSummary]:
        await self._ensure_available()
        ownership = self._ownership
        if ownership is not None:
            tenant_id = self._tenant_id_provider()
            scope = f"knowledge-bases-{tenant_id}"
            offset = (
                0
                if page.cursor is None
                else decode_offset_cursor(
                    page.cursor,
                    scope=scope,
                    search=page.search,
                    limit=page.limit,
                )
            )
            allowed = await ownership.list_ids(tenant_id)
            matched = 0
            collected: list[KnowledgeBaseSummary] = []
            async for values in self._provider_pages(search=page.search):
                await self._claim_legacy(tenant_id, values)
                if tenant_id == DEFAULT_TENANT_ID:
                    allowed = await ownership.list_ids(tenant_id)
                for value in values:
                    if value.id not in allowed:
                        continue
                    if matched >= offset:
                        collected.append(value)
                        if len(collected) > page.limit:
                            break
                    matched += 1
                if len(collected) > page.limit:
                    break
            items = tuple(collected[: page.limit])
            next_offset = offset + len(items)
            return CursorPage(
                items=items,
                next_cursor=(
                    encode_offset_cursor(
                        scope=scope,
                        search=page.search,
                        limit=page.limit,
                        offset=next_offset,
                    )
                    if len(collected) > page.limit
                    else None
                ),
            )
        if not isinstance(self._knowledge, PageableKnowledgeService):
            raise KnowledgeServiceUnavailable()
        return await self._knowledge.page_knowledge_bases(page)

    async def _provider_pages(
        self,
        *,
        search: str,
    ) -> AsyncIterator[tuple[KnowledgeBaseSummary, ...]]:
        if not isinstance(self._knowledge, PageableKnowledgeService):
            values = await self._knowledge.list_knowledge_bases()
            if search:
                normalized = search.casefold()
                values = tuple(value for value in values if normalized in value.name.casefold())
            yield values
            return

        cursor: str | None = None
        seen_cursors: set[str] = set()
        while True:
            provider_page = await self._knowledge.page_knowledge_bases(
                ListPageRequest(limit=100, search=search, cursor=cursor)
            )
            next_cursor = provider_page.next_cursor
            if next_cursor is not None and (
                not provider_page.items or next_cursor == cursor or next_cursor in seen_cursors
            ):
                raise KnowledgeServiceUnavailable()
            if next_cursor is not None:
                seen_cursors.add(next_cursor)
            yield provider_page.items
            cursor = next_cursor
            if cursor is None:
                return

    async def _claim_legacy(
        self,
        tenant_id: UUID,
        values: tuple[KnowledgeBaseSummary, ...],
    ) -> None:
        if self._ownership is None or tenant_id != DEFAULT_TENANT_ID or not values:
            return
        await self._ownership.claim_legacy(
            tenant_id,
            tuple(value.id for value in values),
            now=self._clock(),
        )

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        await self._ensure_available()
        await self._ensure_owned(knowledge_base_id)
        return await self._knowledge.get_knowledge_base(knowledge_base_id)

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        await self._ensure_available()
        created = await self._knowledge.create_knowledge_base(request)
        ownership = self._ownership
        if ownership is not None and not await ownership.claim(
            self._tenant_id_provider(),
            created.id,
            now=self._clock(),
        ):
            await self._knowledge.delete_knowledge_base(created.id)
            raise KnowledgeBaseNotFound()
        return created

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        await self._ensure_available()
        await self._ensure_owned(knowledge_base_id)
        await self._knowledge.delete_knowledge_base(knowledge_base_id)
        if self._ownership is not None:
            await self._ownership.release(self._tenant_id_provider(), knowledge_base_id)

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        await self._ensure_available()
        await self._ensure_owned(knowledge_base_id)
        return await self._knowledge.list_documents(knowledge_base_id)

    async def upload_document(
        self,
        knowledge_base_id: str,
        upload: DocumentUpload,
    ) -> KnowledgeDocument:
        self._validate_upload(upload)
        await self._ensure_available()
        await self._ensure_owned(knowledge_base_id)
        return await self._knowledge.upload_document(knowledge_base_id, upload)

    async def retry_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> KnowledgeDocument:
        await self._ensure_available()
        await self._ensure_owned(knowledge_base_id)
        if not isinstance(self._knowledge, RetryableKnowledgeService):
            raise KnowledgeServiceUnavailable()
        document = await self._knowledge.get_document(knowledge_base_id, document_id)
        if document is None:
            raise KnowledgeDocumentNotFound()
        if document.parsing_status is not DocumentParsingStatus.FAILED:
            raise KnowledgeDocumentRetryRejected()
        return await self._knowledge.retry_document(knowledge_base_id, document)

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        await self._ensure_available()
        await self._ensure_owned(request.knowledge_base_id)
        return await self._knowledge.retrieve(request)

    async def _ensure_owned(self, knowledge_base_id: str) -> None:
        ownership = self._ownership
        if ownership is not None and not await ownership.owns(
            self._tenant_id_provider(), knowledge_base_id
        ):
            raise KnowledgeBaseNotFound()

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
