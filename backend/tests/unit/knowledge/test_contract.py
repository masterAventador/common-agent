from __future__ import annotations

from dataclasses import FrozenInstanceError

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
    RetrievedChunk,
)
from common_agent.knowledge.base import (
    KnowledgeBaseNotFound,
    KnowledgeConfigurationMissing,
    KnowledgeDocumentUploadFailed,
    KnowledgeDocumentUploadResultUnknown,
    KnowledgeProviderResponseInvalid,
    KnowledgeService,
    KnowledgeServiceError,
    KnowledgeServiceUnavailable,
)


class _ContractShape:
    @property
    def provider_name(self) -> str:
        return "contract-probe"

    async def status(self) -> KnowledgeServiceStatus:
        raise NotImplementedError

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        raise NotImplementedError

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
        raise NotImplementedError


def test_knowledge_service_protocol_covers_the_complete_platform_surface() -> None:
    service: KnowledgeService = _ContractShape()

    assert isinstance(service, KnowledgeService)
    assert service.provider_name == "contract-probe"


def test_platform_models_are_immutable_and_do_not_expose_document_content() -> None:
    upload = DocumentUpload(
        file_name="employee-guide.md",
        content_type="text/markdown",
        content=b"private knowledge content",
    )
    knowledge_base = KnowledgeBaseSummary(
        id="kb-1",
        name="员工手册",
        description="内部制度",
        document_count=1,
        parsing_count=0,
    )

    assert upload.size_bytes == 25
    assert "private knowledge content" not in repr(upload)
    with pytest.raises(FrozenInstanceError):
        knowledge_base.name = "不可变"  # type: ignore[misc]


def test_status_document_and_retrieval_models_use_stable_platform_semantics() -> None:
    status = KnowledgeServiceStatus(
        provider="ragflow",
        availability=KnowledgeServiceAvailability.AVAILABLE,
        version="v0.25.6",
    )
    document = KnowledgeDocument(
        id="doc-1",
        knowledge_base_id="kb-1",
        name="employee-guide.md",
        size_bytes=25,
        parsing_status=DocumentParsingStatus.COMPLETED,
        error_code=None,
    )
    request = KnowledgeRetrievalRequest(knowledge_base_id="kb-1", query="年假有几天")
    result = KnowledgeRetrievalResult(
        chunks=(
            RetrievedChunk(
                id="chunk-1",
                document_id=document.id,
                document_name=document.name,
                content="每年享有十天年假。",
                score=0.91,
            ),
        )
    )

    assert status.availability.value == "available"
    assert document.parsing_status.value == "completed"
    assert request.top_k == 5
    assert request.similarity_threshold == 0.2
    assert result.chunks[0].document_name == "employee-guide.md"


@pytest.mark.parametrize(
    ("error_type", "code", "message", "retryable"),
    [
        (
            KnowledgeConfigurationMissing,
            "configuration_missing",
            "知识库服务尚未配置",
            False,
        ),
        (
            KnowledgeServiceUnavailable,
            "knowledge_service_unavailable",
            "知识库服务暂时不可用",
            True,
        ),
        (
            KnowledgeBaseNotFound,
            "knowledge_base_not_found",
            "知识库不存在或已失效",
            False,
        ),
        (
            KnowledgeDocumentUploadFailed,
            "document_upload_failed",
            "文档上传失败",
            False,
        ),
        (
            KnowledgeDocumentUploadResultUnknown,
            "document_upload_result_unknown",
            "文档上传结果无法确认。请刷新文档列表后再决定是否重试",
            False,
        ),
        (
            KnowledgeProviderResponseInvalid,
            "knowledge_service_invalid_response",
            "知识库服务返回了无法识别的数据",
            False,
        ),
    ],
)
def test_knowledge_failures_have_safe_stable_semantics(
    error_type: type[KnowledgeServiceError],
    code: str,
    message: str,
    retryable: bool,
) -> None:
    error = error_type()

    assert error.code == code
    assert error.message == message
    assert error.retryable is retryable
    assert str(error) == message
