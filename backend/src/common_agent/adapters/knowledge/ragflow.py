from __future__ import annotations

import json
from dataclasses import replace
from pathlib import PurePosixPath
from typing import Any, Literal, cast

import httpx
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, TypeAdapter, ValidationError

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
    KnowledgeBaseDeleteResultUnknown,
    KnowledgeBaseNotFound,
    KnowledgeConfigurationMissing,
    KnowledgeDocumentRetryResultUnknown,
    KnowledgeDocumentUploadFailed,
    KnowledgeDocumentUploadResultUnknown,
    KnowledgeProviderResponseInvalid,
    KnowledgeRequestRejected,
    KnowledgeServiceError,
    KnowledgeServiceUnavailable,
)
from common_agent.observability import outbound_trace_headers
from common_agent.pagination import (
    CursorPage,
    InvalidPageCursor,
    ListPageRequest,
    decode_offset_cursor,
    encode_offset_cursor,
)


class _RagFlowEnvelope(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    code: int
    data: Any = None
    total_datasets: int | None = Field(default=None, ge=0)


class _RagFlowDataset(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str = ""
    document_count: int = Field(default=0, ge=0)


class _RagFlowDocument(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(min_length=1)
    dataset_id: str | None = None
    name: str = Field(min_length=1)
    run: str = Field(min_length=1)
    size: int = Field(default=0, ge=0)


class _RagFlowDocumentList(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    total: int = Field(ge=0)
    docs: list[_RagFlowDocument]


class _RagFlowChunk(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    id: str = Field(min_length=1)
    document_id: str = Field(min_length=1)
    document_keyword: str = Field(min_length=1)
    content: str
    similarity: FiniteFloat = Field(ge=0, le=1)


class _RagFlowRetrieval(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)

    total: int = Field(ge=0)
    chunks: list[_RagFlowChunk]


_ENVELOPE_ADAPTER = TypeAdapter(_RagFlowEnvelope)
_DATASET_ADAPTER = TypeAdapter(_RagFlowDataset)
_DATASET_LIST_ADAPTER = TypeAdapter(list[_RagFlowDataset])
_DOCUMENT_LIST_ADAPTER = TypeAdapter(_RagFlowDocumentList)
_UPLOADED_DOCUMENTS_ADAPTER = TypeAdapter(list[_RagFlowDocument])
_RETRIEVAL_ADAPTER = TypeAdapter(_RagFlowRetrieval)
_VERSION_ADAPTER = TypeAdapter(str)


def _validate[Result](adapter: TypeAdapter[Result], value: Any) -> Result:
    try:
        return adapter.validate_python(value, strict=True)
    except (OverflowError, TypeError, ValueError, ValidationError) as error:
        raise KnowledgeProviderResponseInvalid() from error


def _safe_file_name(value: str) -> str:
    normalized = value.replace("\\", "/")
    name = PurePosixPath(normalized).name
    if not name or name in {".", ".."}:
        raise KnowledgeDocumentUploadFailed()
    return name


class RagFlowKnowledgeService:
    provider_name = "ragflow"

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        expected_version: str,
        embedding_model: str = ("text-embedding-v4@common-agent-embedding@OpenAI-API-Compatible"),
        rerank_model: str = ("qwen3-rerank@common-agent-rerank@OpenAI-API-Compatible"),
        timeout_seconds: float = 60.0,
        ca_bundle_path: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key.strip()
        self._expected_version = expected_version
        self._embedding_model = embedding_model
        self._rerank_model = rerank_model
        self._owned_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=httpx.Timeout(timeout_seconds),
            verify=ca_bundle_path or True,
            trust_env=False,
        )
        self._headers = {"Authorization": f"Bearer {self._api_key}"}

    async def aclose(self) -> None:
        if self._owned_client:
            await self._client.aclose()

    async def status(self) -> KnowledgeServiceStatus:
        if not self._api_key:
            return KnowledgeServiceStatus(
                provider=self.provider_name,
                availability=KnowledgeServiceAvailability.NOT_CONFIGURED,
                version=None,
                error_code=KnowledgeConfigurationMissing.code,
            )
        try:
            data = await self._request("GET", "/api/v1/system/version")
            version = _validate(_VERSION_ADAPTER, data)
        except KnowledgeServiceError as error:
            return KnowledgeServiceStatus(
                provider=self.provider_name,
                availability=KnowledgeServiceAvailability.UNAVAILABLE,
                version=None,
                error_code=error.code,
            )
        if version != self._expected_version:
            return KnowledgeServiceStatus(
                provider=self.provider_name,
                availability=KnowledgeServiceAvailability.UNAVAILABLE,
                version=version,
                error_code="knowledge_service_version_mismatch",
            )
        return KnowledgeServiceStatus(
            provider=self.provider_name,
            availability=KnowledgeServiceAvailability.AVAILABLE,
            version=version,
        )

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        data = await self._request(
            "GET",
            "/api/v1/datasets",
            params={"page": 1, "page_size": 100, "orderby": "create_time", "desc": "true"},
        )
        payload = _validate(_DATASET_LIST_ADAPTER, data)
        return tuple(self._knowledge_base(item) for item in payload)

    async def page_knowledge_bases(
        self,
        page: ListPageRequest,
    ) -> CursorPage[KnowledgeBaseSummary]:
        scope = "knowledge-bases"
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
        if offset % page.limit != 0:
            raise InvalidPageCursor
        params: dict[str, str | int] = {
            "page": offset // page.limit + 1,
            "page_size": page.limit,
            "orderby": "create_time",
            "desc": "true",
        }
        if page.search:
            params["ext"] = json.dumps(
                {"keywords": page.search},
                ensure_ascii=True,
                separators=(",", ":"),
            )
        response = cast(
            tuple[Any, int | None],
            await self._request(
                "GET",
                "/api/v1/datasets",
                params=params,
                include_total=True,
            ),
        )
        data, total = response
        payload = _validate(_DATASET_LIST_ADAPTER, data)
        has_more = (
            offset + len(payload) < total if total is not None else len(payload) == page.limit
        )
        next_cursor = (
            encode_offset_cursor(
                scope=scope,
                search=page.search,
                limit=page.limit,
                offset=offset + len(payload),
            )
            if has_more
            else None
        )
        return CursorPage(
            items=tuple(self._knowledge_base(item) for item in payload),
            next_cursor=next_cursor,
        )

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        data = await self._request(
            "GET",
            f"/api/v1/datasets/{knowledge_base_id}",
            dataset_scoped=True,
        )
        return self._knowledge_base(_validate(_DATASET_ADAPTER, data))

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        data = await self._request(
            "POST",
            "/api/v1/datasets",
            json={
                "name": request.name,
                "description": request.description,
                "permission": "me",
                "chunk_method": "naive",
                "embedding_model": self._embedding_model,
            },
        )
        return self._knowledge_base(_validate(_DATASET_ADAPTER, data))

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        await self._request(
            "DELETE",
            "/api/v1/datasets",
            failure_mode="delete",
            json={"ids": [knowledge_base_id]},
        )

    async def upload_document(
        self, knowledge_base_id: str, upload: DocumentUpload
    ) -> KnowledgeDocument:
        try:
            data = await self._request(
                "POST",
                f"/api/v1/datasets/{knowledge_base_id}/documents",
                dataset_scoped=True,
                failure_mode="upload",
                files={
                    "file": (
                        _safe_file_name(upload.file_name),
                        upload.content,
                        upload.content_type,
                    )
                },
            )
            uploaded = _validate(_UPLOADED_DOCUMENTS_ADAPTER, data)
        except KnowledgeProviderResponseInvalid as error:
            raise KnowledgeDocumentUploadResultUnknown() from error
        if not uploaded:
            raise KnowledgeDocumentUploadResultUnknown()

        document = self._document(uploaded[0], knowledge_base_id)
        await self._request(
            "POST",
            f"/api/v1/datasets/{knowledge_base_id}/chunks",
            dataset_scoped=True,
            failure_mode="post_upload",
            json={"document_ids": [document.id]},
        )
        return KnowledgeDocument(
            id=document.id,
            knowledge_base_id=document.knowledge_base_id,
            name=document.name,
            size_bytes=document.size_bytes,
            parsing_status=DocumentParsingStatus.PARSING,
            error_code=None,
        )

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        page = 1
        expected_total: int | None = None
        collected: list[_RagFlowDocument] = []
        document_ids: set[str] = set()
        while expected_total is None or len(collected) < expected_total:
            data = await self._request(
                "GET",
                f"/api/v1/datasets/{knowledge_base_id}/documents",
                dataset_scoped=True,
                params={
                    "page": page,
                    "page_size": 100,
                    "orderby": "create_time",
                    "desc": "true",
                },
            )
            payload = _validate(_DOCUMENT_LIST_ADAPTER, data)
            if expected_total is None:
                expected_total = payload.total
            if payload.total != expected_total:
                raise KnowledgeProviderResponseInvalid()
            for item in payload.docs:
                if item.id in document_ids:
                    raise KnowledgeProviderResponseInvalid()
                document_ids.add(item.id)
                collected.append(item)
            if len(collected) > expected_total:
                raise KnowledgeProviderResponseInvalid()
            if len(collected) == expected_total:
                break
            if len(payload.docs) < 100:
                raise KnowledgeProviderResponseInvalid()
            page += 1
        return tuple(self._document(item, knowledge_base_id) for item in collected)

    async def get_document(
        self,
        knowledge_base_id: str,
        document_id: str,
    ) -> KnowledgeDocument | None:
        data = await self._request(
            "GET",
            f"/api/v1/datasets/{knowledge_base_id}/documents",
            dataset_scoped=True,
            params={"ids": document_id, "page": 1, "page_size": 1},
        )
        payload = _validate(_DOCUMENT_LIST_ADAPTER, data)
        matched = next((item for item in payload.docs if item.id == document_id), None)
        return None if matched is None else self._document(matched, knowledge_base_id)

    async def retry_document(
        self,
        knowledge_base_id: str,
        document: KnowledgeDocument,
    ) -> KnowledgeDocument:
        await self._request(
            "POST",
            f"/api/v1/datasets/{knowledge_base_id}/chunks",
            dataset_scoped=True,
            failure_mode="retry",
            json={"document_ids": [document.id]},
        )
        return replace(
            document,
            parsing_status=DocumentParsingStatus.PARSING,
            error_code=None,
        )

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        data = await self._request(
            "POST",
            "/api/v1/retrieval",
            dataset_scoped=True,
            json={
                "question": request.query,
                "dataset_ids": [request.knowledge_base_id],
                "page": 1,
                "page_size": request.top_k,
                "top_k": request.top_k,
                "similarity_threshold": request.similarity_threshold,
                "vector_similarity_weight": 0.3,
                "rerank_id": self._rerank_model,
                "include_metadata": True,
            },
        )
        payload = _validate(_RETRIEVAL_ADAPTER, data)
        accepted = tuple(
            item
            for item in payload.chunks
            if float(item.similarity) >= request.similarity_threshold
        )[: request.top_k]
        return KnowledgeRetrievalResult(
            chunks=tuple(
                RetrievedChunk(
                    id=item.id,
                    document_id=item.document_id,
                    document_name=item.document_keyword,
                    content=item.content,
                    score=float(item.similarity),
                )
                for item in accepted
            )
        )

    async def _request(
        self,
        method: str,
        path: str,
        *,
        dataset_scoped: bool = False,
        failure_mode: Literal["standard", "upload", "post_upload", "retry", "delete"] = "standard",
        include_total: bool = False,
        **kwargs: Any,
    ) -> Any:
        self._require_configured()
        try:
            response = await self._client.request(
                method,
                path,
                headers={**self._headers, **outbound_trace_headers()},
                **kwargs,
            )
        except httpx.HTTPError as error:
            if failure_mode == "retry":
                raise KnowledgeDocumentRetryResultUnknown() from error
            if failure_mode in {"upload", "post_upload"}:
                raise KnowledgeDocumentUploadResultUnknown() from error
            if failure_mode == "delete":
                raise KnowledgeBaseDeleteResultUnknown() from error
            raise KnowledgeServiceUnavailable() from error

        if response.status_code >= 500:
            if failure_mode == "retry":
                raise KnowledgeDocumentRetryResultUnknown()
            if failure_mode in {"upload", "post_upload"}:
                raise KnowledgeDocumentUploadResultUnknown()
            if failure_mode == "delete":
                raise KnowledgeBaseDeleteResultUnknown()
            raise KnowledgeServiceUnavailable()
        if response.status_code >= 400:
            if failure_mode == "delete" and response.status_code == 404:
                return None
            if failure_mode == "post_upload":
                raise KnowledgeDocumentUploadResultUnknown()
            if failure_mode == "retry":
                raise KnowledgeDocumentRetryResultUnknown()
            if failure_mode == "upload":
                raise KnowledgeDocumentUploadFailed()
            if dataset_scoped and response.status_code == 404:
                raise KnowledgeBaseNotFound()
            raise KnowledgeRequestRejected()

        try:
            raw = response.json()
        except (OverflowError, ValueError) as error:
            if failure_mode == "retry":
                raise KnowledgeDocumentRetryResultUnknown() from error
            if failure_mode in {"upload", "post_upload"}:
                raise KnowledgeDocumentUploadResultUnknown() from error
            if failure_mode == "delete":
                raise KnowledgeBaseDeleteResultUnknown() from error
            raise KnowledgeProviderResponseInvalid() from error
        try:
            envelope = _validate(_ENVELOPE_ADAPTER, raw)
        except KnowledgeProviderResponseInvalid as error:
            if failure_mode == "delete":
                raise KnowledgeBaseDeleteResultUnknown() from error
            if failure_mode == "retry":
                raise KnowledgeDocumentRetryResultUnknown() from error
            raise
        if envelope.code != 0:
            if failure_mode == "delete" and envelope.code == 102:
                return None
            if failure_mode == "post_upload":
                raise KnowledgeDocumentUploadResultUnknown()
            if failure_mode == "retry":
                raise KnowledgeDocumentRetryResultUnknown()
            if failure_mode == "upload":
                raise KnowledgeDocumentUploadFailed()
            if dataset_scoped and envelope.code == 102:
                raise KnowledgeBaseNotFound()
            raise KnowledgeRequestRejected()
        if include_total:
            return envelope.data, envelope.total_datasets
        return envelope.data

    def _require_configured(self) -> None:
        if not self._api_key:
            raise KnowledgeConfigurationMissing()

    @staticmethod
    def _knowledge_base(payload: _RagFlowDataset) -> KnowledgeBaseSummary:
        return KnowledgeBaseSummary(
            id=payload.id,
            name=payload.name,
            description=payload.description,
            document_count=payload.document_count,
            parsing_count=0,
        )

    @staticmethod
    def _document(payload: _RagFlowDocument, knowledge_base_id: str) -> KnowledgeDocument:
        if payload.dataset_id is not None and payload.dataset_id != knowledge_base_id:
            raise KnowledgeProviderResponseInvalid()
        parsing_status = _parsing_status(payload.run)
        return KnowledgeDocument(
            id=payload.id,
            knowledge_base_id=knowledge_base_id,
            name=payload.name,
            size_bytes=payload.size,
            parsing_status=parsing_status,
            error_code="document_parsing_failed"
            if parsing_status is DocumentParsingStatus.FAILED
            else None,
        )


def _parsing_status(value: str) -> DocumentParsingStatus:
    normalized = value.upper()
    if normalized in {"0", "UNSTART"}:
        return DocumentParsingStatus.UPLOADED
    if normalized in {"1", "RUNNING"}:
        return DocumentParsingStatus.PARSING
    if normalized in {"3", "DONE"}:
        return DocumentParsingStatus.COMPLETED
    if normalized in {"2", "CANCEL", "4", "FAIL"}:
        return DocumentParsingStatus.FAILED
    raise KnowledgeProviderResponseInvalid()
