from __future__ import annotations

from typing import ClassVar, Protocol, runtime_checkable

from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceStatus,
)


class KnowledgeServiceError(Exception):
    code: ClassVar[str]
    message: ClassVar[str]
    retryable: ClassVar[bool]

    def __init__(self) -> None:
        super().__init__(self.message)


class KnowledgeConfigurationMissing(KnowledgeServiceError):
    code = "configuration_missing"
    message = "知识库服务尚未配置"
    retryable = False


class KnowledgeServiceUnavailable(KnowledgeServiceError):
    code = "knowledge_service_unavailable"
    message = "知识库服务暂时不可用"
    retryable = True


class KnowledgeServiceVersionMismatch(KnowledgeServiceError):
    code = "knowledge_service_version_mismatch"
    message = "知识库服务版本与平台要求不一致"
    retryable = False


class KnowledgeBaseNotFound(KnowledgeServiceError):
    code = "knowledge_base_not_found"
    message = "知识库不存在或已失效"
    retryable = False


class KnowledgeRequestRejected(KnowledgeServiceError):
    code = "knowledge_request_rejected"
    message = "知识库服务拒绝了请求"
    retryable = False


class KnowledgeDocumentUploadFailed(KnowledgeServiceError):
    code = "document_upload_failed"
    message = "文档上传失败"
    retryable = False


class KnowledgeDocumentUploadResultUnknown(KnowledgeServiceError):
    code = "document_upload_result_unknown"
    message = "文档上传结果无法确认。请刷新文档列表后再决定是否重试"
    retryable = False


class KnowledgeProviderResponseInvalid(KnowledgeServiceError):
    code = "knowledge_service_invalid_response"
    message = "知识库服务返回了无法识别的数据"
    retryable = False


@runtime_checkable
class KnowledgeService(Protocol):
    @property
    def provider_name(self) -> str: ...

    async def status(self) -> KnowledgeServiceStatus: ...

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]: ...

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary: ...

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary: ...

    async def upload_document(
        self, knowledge_base_id: str, upload: DocumentUpload
    ) -> KnowledgeDocument: ...

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]: ...

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult: ...
