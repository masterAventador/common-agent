from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.knowledge import knowledge_error_to_app_error
from common_agent.api.routers.services import workflow_service
from common_agent.api.schemas.workflows import (
    WorkflowConfigurationBody,
    WorkflowResponse,
    WorkflowValidationResponse,
    workflow_configuration,
    workflow_response,
    workflow_validation_response,
)
from common_agent.application.workflow_service import WorkflowNotFound
from common_agent.domain.workflow import WorkflowValidationError
from common_agent.knowledge.base import KnowledgeServiceError
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
    raise TypeError("unsupported workflow application error")


@router.get(
    "",
    response_model=list[WorkflowResponse],
    responses={503: {"model": ErrorEnvelope}},
)
async def list_workflows(request: Request) -> list[WorkflowResponse]:
    return [workflow_response(workflow) for workflow in await workflow_service(request).list()]


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
    return workflow_response(workflow)


__all__ = ["WorkflowConfigurationBody", "WorkflowResponse", "router"]
