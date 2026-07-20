from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, UploadFile, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.resource_deletion import (
    resource_deletion_error,
    resource_deletion_service,
)
from common_agent.application.resource_deletion import ResourceDeletionError
from common_agent.domain.knowledge import (
    KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH,
    KNOWLEDGE_BASE_NAME_MAX_LENGTH,
    CreateKnowledgeBaseRequest,
    DocumentParsingStatus,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
)
from common_agent.knowledge.base import (
    KnowledgeBaseDeleteResultUnknown,
    KnowledgeBaseNotFound,
    KnowledgeConfigurationMissing,
    KnowledgeDocumentUploadFailed,
    KnowledgeDocumentUploadResultUnknown,
    KnowledgeProviderResponseInvalid,
    KnowledgeRequestRejected,
    KnowledgeServiceError,
    KnowledgeServiceUnavailable,
    KnowledgeServiceVersionMismatch,
)
from common_agent.knowledge.service import (
    MAX_DOCUMENT_SIZE_BYTES,
    KnowledgeBaseService,
    KnowledgeInputError,
)

router = APIRouter(prefix="/api/v1/knowledge-bases", tags=["knowledge-bases"])

KnowledgeBaseName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=KNOWLEDGE_BASE_NAME_MAX_LENGTH,
    ),
]
KnowledgeBaseDescription = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        max_length=KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH,
    ),
]


class CreateKnowledgeBaseBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: KnowledgeBaseName
    description: KnowledgeBaseDescription = ""


class KnowledgeBaseResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    name: str
    description: str
    document_count: int
    parsing_count: int


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: str
    knowledge_base_id: str
    name: str
    size_bytes: int
    parsing_status: DocumentParsingStatus
    error_code: str | None


def _application(request: Request) -> KnowledgeBaseService:
    application = getattr(request.app.state, "knowledge_bases", None)
    if not isinstance(application, KnowledgeBaseService):
        raise AppError(
            code="knowledge_service_unavailable",
            message="知识库服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def knowledge_error_to_app_error(error: KnowledgeServiceError | KnowledgeInputError) -> AppError:
    if isinstance(error, KnowledgeInputError):
        return AppError(
            code=error.code,
            message=error.message,
            status_code=error.status_code,
            retryable=False,
        )

    status_code = 502
    if isinstance(error, KnowledgeBaseNotFound):
        status_code = 404
    elif isinstance(
        error,
        (
            KnowledgeConfigurationMissing,
            KnowledgeServiceUnavailable,
            KnowledgeServiceVersionMismatch,
        ),
    ):
        status_code = 503
    elif isinstance(error, KnowledgeDocumentUploadFailed):
        status_code = 422
    elif isinstance(
        error,
        (
            KnowledgeBaseDeleteResultUnknown,
            KnowledgeDocumentUploadResultUnknown,
            KnowledgeProviderResponseInvalid,
            KnowledgeRequestRejected,
        ),
    ):
        status_code = 502
    return AppError(
        code=error.code,
        message=error.message,
        status_code=status_code,
        retryable=error.retryable,
    )


def _knowledge_base_response(value: KnowledgeBaseSummary) -> KnowledgeBaseResponse:
    return KnowledgeBaseResponse.model_validate(value)


def _document_response(value: KnowledgeDocument) -> KnowledgeDocumentResponse:
    return KnowledgeDocumentResponse.model_validate(value)


async def _read_upload(file: UploadFile) -> bytes:
    content = bytearray()
    try:
        while len(content) <= MAX_DOCUMENT_SIZE_BYTES:
            chunk = await file.read(min(1024 * 1024, MAX_DOCUMENT_SIZE_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
    finally:
        await file.close()
    return bytes(content)


@router.get(
    "",
    response_model=list[KnowledgeBaseResponse],
    responses={503: {"model": ErrorEnvelope}, 502: {"model": ErrorEnvelope}},
)
async def list_knowledge_bases(request: Request) -> list[KnowledgeBaseResponse]:
    try:
        items = await _application(request).list_knowledge_bases()
    except KnowledgeServiceError as error:
        raise knowledge_error_to_app_error(error) from error
    return [_knowledge_base_response(item) for item in items]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=KnowledgeBaseResponse,
    responses={
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def create_knowledge_base(
    request: Request,
    body: CreateKnowledgeBaseBody,
) -> KnowledgeBaseResponse:
    try:
        created = await _application(request).create_knowledge_base(
            CreateKnowledgeBaseRequest(name=body.name, description=body.description)
        )
    except KnowledgeServiceError as error:
        raise knowledge_error_to_app_error(error) from error
    return _knowledge_base_response(created)


@router.delete(
    "/{knowledge_base_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def delete_knowledge_base(request: Request, knowledge_base_id: str) -> None:
    try:
        await resource_deletion_service(request).delete_knowledge_base(knowledge_base_id)
    except ResourceDeletionError as error:
        raise resource_deletion_error(error) from error
    except KnowledgeServiceError as error:
        raise knowledge_error_to_app_error(error) from error


@router.get(
    "/{knowledge_base_id}/documents",
    response_model=list[KnowledgeDocumentResponse],
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
    },
)
async def list_documents(
    request: Request,
    knowledge_base_id: str,
) -> list[KnowledgeDocumentResponse]:
    try:
        documents = await _application(request).list_documents(knowledge_base_id)
    except KnowledgeServiceError as error:
        raise knowledge_error_to_app_error(error) from error
    return [_document_response(document) for document in documents]


@router.post(
    "/{knowledge_base_id}/documents",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=KnowledgeDocumentResponse,
    responses={
        404: {"model": ErrorEnvelope},
        413: {"model": ErrorEnvelope},
        415: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def upload_document(
    request: Request,
    knowledge_base_id: str,
    file: Annotated[UploadFile, File(description="TXT、Markdown、PDF 或 DOCX, 最大 20 MiB")],
) -> KnowledgeDocumentResponse:
    upload = DocumentUpload(
        file_name=file.filename or "",
        content_type=file.content_type or "application/octet-stream",
        content=await _read_upload(file),
    )
    try:
        document = await _application(request).upload_document(knowledge_base_id, upload)
    except (KnowledgeServiceError, KnowledgeInputError) as error:
        raise knowledge_error_to_app_error(error) from error
    return _document_response(document)
