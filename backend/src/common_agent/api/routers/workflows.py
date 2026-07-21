from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from common_agent.api.audit import mark_audit_resource
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.knowledge import knowledge_error_to_app_error
from common_agent.api.routers.resource_deletion import (
    resource_deletion_error,
    resource_deletion_service,
)
from common_agent.api.routers.services import workflow_service
from common_agent.api.schemas.pagination import CursorPageResponse
from common_agent.api.schemas.workflows import (
    WorkflowConfigurationBody,
    WorkflowResponse,
    WorkflowValidationResponse,
    workflow_configuration,
    workflow_response,
    workflow_validation_response,
)
from common_agent.application.resource_deletion import ResourceDeletionError
from common_agent.application.workflow_service import WorkflowNotFound
from common_agent.audit import AuditResourceType
from common_agent.domain.workflow import WorkflowValidationError
from common_agent.knowledge.base import KnowledgeServiceError
from common_agent.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_CURSOR_LENGTH,
    MAX_PAGE_LIMIT,
    MAX_PAGE_SEARCH_LENGTH,
    InvalidPageCursor,
    ListPageRequest,
)
from common_agent.ports.workflows import WorkflowAlreadyExists
from common_agent.workflows.validator import WorkflowGraphInvalid

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])


def workflow_error(error: Exception) -> AppError:
    if isinstance(error, KnowledgeServiceError):
        return knowledge_error_to_app_error(error)
    if isinstance(error, WorkflowNotFound):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, WorkflowAlreadyExists):
        return AppError("workflow_conflict", "工作流已存在", 409, False)
    if isinstance(error, WorkflowGraphInvalid):
        return AppError("workflow_invalid", "工作流图校验失败", 422, False)
    if isinstance(error, WorkflowValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, InvalidPageCursor):
        return AppError(error.code, error.message, 422, error.retryable)
    raise TypeError("unsupported workflow application error")


@router.get(
    "",
    response_model=CursorPageResponse[WorkflowResponse],
    responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def list_workflows(
    request: Request,
    search: Annotated[str, Query(max_length=MAX_PAGE_SEARCH_LENGTH)] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_PAGE_CURSOR_LENGTH)] = None,
) -> CursorPageResponse[WorkflowResponse]:
    try:
        page = await workflow_service(request).page(
            ListPageRequest(limit=limit, search=search, cursor=cursor)
        )
    except InvalidPageCursor as error:
        raise workflow_error(error) from error
    return CursorPageResponse(
        items=[workflow_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.delete(
    "/{workflow_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def delete_workflow(request: Request, workflow_id: UUID) -> None:
    try:
        await resource_deletion_service(request).delete_workflow(workflow_id)
    except ResourceDeletionError as error:
        raise resource_deletion_error(error) from error
    mark_audit_resource(request, AuditResourceType.WORKFLOW, workflow_id)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkflowResponse,
    responses={
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def create_workflow(
    request: Request,
    body: WorkflowConfigurationBody,
) -> WorkflowResponse:
    try:
        workflow = await workflow_service(request).create(workflow_configuration(body))
    except (
        KnowledgeServiceError,
        WorkflowAlreadyExists,
        WorkflowGraphInvalid,
        WorkflowValidationError,
    ) as error:
        raise workflow_error(error) from error
    mark_audit_resource(request, AuditResourceType.WORKFLOW, workflow.id)
    return workflow_response(workflow)


@router.post(
    "/validate",
    response_model=WorkflowValidationResponse,
    responses={
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def validate_workflow(
    request: Request,
    body: WorkflowConfigurationBody,
) -> WorkflowValidationResponse:
    try:
        issues = await workflow_service(request).validate(workflow_configuration(body))
    except (KnowledgeServiceError, WorkflowValidationError) as error:
        raise workflow_error(error) from error
    return workflow_validation_response(issues)


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def get_workflow(request: Request, workflow_id: UUID) -> WorkflowResponse:
    try:
        workflow = await workflow_service(request).get(workflow_id)
    except WorkflowNotFound as error:
        raise workflow_error(error) from error
    return workflow_response(workflow)


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def update_workflow(
    request: Request,
    workflow_id: UUID,
    body: WorkflowConfigurationBody,
) -> WorkflowResponse:
    try:
        workflow = await workflow_service(request).update(
            workflow_id,
            workflow_configuration(body),
        )
    except (
        KnowledgeServiceError,
        WorkflowGraphInvalid,
        WorkflowNotFound,
        WorkflowValidationError,
    ) as error:
        raise workflow_error(error) from error
    mark_audit_resource(request, AuditResourceType.WORKFLOW, workflow.id)
    return workflow_response(workflow)


__all__ = ["WorkflowConfigurationBody", "WorkflowResponse", "router"]
