from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from common_agent.api.audit import mark_audit_resource
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.schemas.pagination import CursorPageResponse
from common_agent.audit import AuditResourceType
from common_agent.domain.model_configuration import (
    MODEL_DISPLAY_NAME_MAX_LENGTH,
    MODEL_IDENTIFIER_MAX_LENGTH,
    ModelConfiguration,
    ModelConfigurationInput,
    ModelConfigurationValidationError,
)
from common_agent.model_configurations import ModelConfigurationService
from common_agent.model_configurations.service import (
    ModelConfigurationInUse,
    ModelConfigurationNotFound,
    ModelConfigurationServiceError,
)
from common_agent.models.base import ModelServiceError
from common_agent.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_CURSOR_LENGTH,
    MAX_PAGE_LIMIT,
    MAX_PAGE_SEARCH_LENGTH,
    InvalidPageCursor,
    ListPageRequest,
)
from common_agent.ports.model_configurations import ModelConfigurationAlreadyExists

router = APIRouter(prefix="/api/v1/model-configurations", tags=["model-configurations"])

DisplayName = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MODEL_DISPLAY_NAME_MAX_LENGTH,
    ),
]
ModelIdentifier = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=MODEL_IDENTIFIER_MAX_LENGTH,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$",
    ),
]


class ModelConfigurationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: DisplayName
    model_identifier: ModelIdentifier
    enabled: bool = True


class ModelConfigurationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    display_name: str
    provider: Literal["bailian"]
    model_identifier: str
    enabled: bool
    streaming_breaks_tool_calls: bool
    thinking_can_be_disabled: bool
    created_at: datetime
    updated_at: datetime


class ModelConfigurationVerificationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    status: Literal["available"]
    model_identifier: str
    response_preview: str


def _application(request: Request) -> ModelConfigurationService:
    application = getattr(request.app.state, "model_configurations", None)
    if not isinstance(application, ModelConfigurationService):
        raise AppError(
            code="model_configuration_service_unavailable",
            message="模型配置服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def _input(body: ModelConfigurationBody) -> ModelConfigurationInput:
    return ModelConfigurationInput(
        display_name=body.display_name,
        model_identifier=body.model_identifier,
        enabled=body.enabled,
    )


def _response(value: ModelConfiguration) -> ModelConfigurationResponse:
    return ModelConfigurationResponse.model_validate(value)


def _error(error: Exception) -> AppError:
    if isinstance(error, ModelConfigurationNotFound):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, ModelConfigurationInUse):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ModelConfigurationAlreadyExists):
        return AppError(
            "model_configuration_conflict",
            "模型显示名称或百炼模型标识已存在",
            409,
            False,
        )
    if isinstance(error, ModelConfigurationValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, InvalidPageCursor):
        return AppError(error.code, error.message, 422, error.retryable)
    if isinstance(error, ModelServiceError):
        return AppError(
            error.code,
            error.message,
            503 if error.retryable else 502,
            error.retryable,
        )
    if isinstance(error, ModelConfigurationServiceError):
        return AppError(error.code, error.message, 409, error.retryable)
    raise TypeError("unsupported model configuration application error")


@router.get(
    "",
    response_model=CursorPageResponse[ModelConfigurationResponse],
    responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def list_model_configurations(
    request: Request,
    search: Annotated[str, Query(max_length=MAX_PAGE_SEARCH_LENGTH)] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_PAGE_CURSOR_LENGTH)] = None,
    enabled_only: bool = False,
) -> CursorPageResponse[ModelConfigurationResponse]:
    try:
        page = await _application(request).page(
            ListPageRequest(limit=limit, search=search, cursor=cursor),
            enabled_only=enabled_only,
        )
    except InvalidPageCursor as error:
        raise _error(error) from error
    return CursorPageResponse(
        items=[_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=ModelConfigurationResponse,
    responses={409: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)
async def create_model_configuration(
    request: Request,
    body: ModelConfigurationBody,
) -> ModelConfigurationResponse:
    try:
        created = await _application(request).create(_input(body))
    except (ModelConfigurationAlreadyExists, ModelConfigurationValidationError) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MODEL_CONFIGURATION, created.id)
    return _response(created)


@router.get(
    "/{model_configuration_id}",
    response_model=ModelConfigurationResponse,
    responses={404: {"model": ErrorEnvelope}},
)
async def get_model_configuration(
    request: Request,
    model_configuration_id: UUID,
) -> ModelConfigurationResponse:
    try:
        return _response(await _application(request).get(model_configuration_id))
    except ModelConfigurationNotFound as error:
        raise _error(error) from error


@router.put(
    "/{model_configuration_id}",
    response_model=ModelConfigurationResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
    },
)
async def update_model_configuration(
    request: Request,
    model_configuration_id: UUID,
    body: ModelConfigurationBody,
) -> ModelConfigurationResponse:
    try:
        updated = await _application(request).update(model_configuration_id, _input(body))
    except (
        ModelConfigurationAlreadyExists,
        ModelConfigurationNotFound,
        ModelConfigurationValidationError,
    ) as error:
        raise _error(error) from error
    mark_audit_resource(request, AuditResourceType.MODEL_CONFIGURATION, updated.id)
    return _response(updated)


@router.delete(
    "/{model_configuration_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={404: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def delete_model_configuration(
    request: Request,
    model_configuration_id: UUID,
) -> None:
    try:
        await _application(request).delete(model_configuration_id)
    except (ModelConfigurationNotFound, ModelConfigurationInUse) as error:
        raise _error(error) from error
    mark_audit_resource(
        request,
        AuditResourceType.MODEL_CONFIGURATION,
        model_configuration_id,
    )


@router.post(
    "/{model_configuration_id}/verify",
    response_model=ModelConfigurationVerificationResponse,
    responses={
        404: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def verify_model_configuration(
    request: Request,
    model_configuration_id: UUID,
) -> ModelConfigurationVerificationResponse:
    try:
        result = await _application(request).verify(model_configuration_id)
    except (ModelConfigurationNotFound, ModelServiceError) as error:
        raise _error(error) from error
    mark_audit_resource(
        request,
        AuditResourceType.MODEL_CONFIGURATION,
        model_configuration_id,
    )
    return ModelConfigurationVerificationResponse.model_validate(result)
