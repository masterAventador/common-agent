from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request

from common_agent.api.audit import mark_audit_resource
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.schemas.tools import (
    ToolCatalogResponse,
    ToolGrantResponse,
    ToolGrantSelectionBody,
    tool_catalog_response,
    tool_grant_response,
    tool_grant_selection,
)
from common_agent.audit import AuditResourceType
from common_agent.tools import (
    ToolCapabilityUnavailable,
    ToolCollectionNotFound,
    ToolGrantTargetNotFound,
    ToolService,
    ToolServiceError,
    ToolValidationError,
)

router = APIRouter(tags=["tools"])


def _service(request: Request) -> ToolService:
    service = getattr(request.app.state, "tools", None)
    if not isinstance(service, ToolService):
        raise AppError("tool_service_unavailable", "工具服务暂时不可用", 503, True)
    return service


def _error(error: Exception) -> AppError:
    if isinstance(error, ToolGrantTargetNotFound):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, (ToolCollectionNotFound, ToolCapabilityUnavailable)):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ToolValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, ToolServiceError):
        return AppError(error.code, error.message, 409, error.retryable)
    raise TypeError("unsupported tool application error")


@router.get(
    "/api/v1/tool-catalog",
    response_model=ToolCatalogResponse,
    responses={503: {"model": ErrorEnvelope}},
)
async def get_tool_catalog(request: Request) -> ToolCatalogResponse:
    return tool_catalog_response(await _service(request).catalog())


@router.get(
    "/api/v1/employees/{employee_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def get_employee_tool_grants(request: Request, employee_id: UUID) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).employee_grants(employee_id)
    except ToolGrantTargetNotFound as error:
        raise _error(error) from error
    return tool_grant_response(snapshot)


@router.put(
    "/api/v1/employees/{employee_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def replace_employee_tool_grants(
    request: Request,
    employee_id: UUID,
    body: ToolGrantSelectionBody,
) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).replace_employee_grants(
            employee_id,
            tool_grant_selection(body),
        )
    except (ToolServiceError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.EMPLOYEE, employee_id)
    return tool_grant_response(snapshot)


@router.get(
    "/api/v1/conversations/{conversation_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={404: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def get_conversation_tool_grants(
    request: Request,
    conversation_id: UUID,
) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).conversation_grants(conversation_id)
    except ToolGrantTargetNotFound as error:
        raise _error(error) from error
    return tool_grant_response(snapshot)


@router.put(
    "/api/v1/conversations/{conversation_id}/tool-grants",
    response_model=ToolGrantResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def replace_conversation_tool_grants(
    request: Request,
    conversation_id: UUID,
    body: ToolGrantSelectionBody,
) -> ToolGrantResponse:
    try:
        snapshot = await _service(request).replace_conversation_grants(
            conversation_id,
            tool_grant_selection(body),
        )
    except (ToolServiceError, ToolValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.CONVERSATION, conversation_id)
    return tool_grant_response(snapshot)


__all__ = ["router"]
