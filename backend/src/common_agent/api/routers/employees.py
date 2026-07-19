from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, StringConstraints

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.knowledge import knowledge_error_to_app_error
from common_agent.domain.employee import (
    EMPLOYEE_DESCRIPTION_MAX_LENGTH,
    EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    EMPLOYEE_NAME_MAX_LENGTH,
    EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH,
    Employee,
    EmployeeConfiguration,
    EmployeeValidationError,
)
from common_agent.employees.service import EmployeeNotFound, EmployeeService
from common_agent.knowledge.base import KnowledgeServiceError
from common_agent.ports.employees import EmployeeAlreadyExists

router = APIRouter(prefix="/api/v1/employees", tags=["employees"])

EmployeeName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=EMPLOYEE_NAME_MAX_LENGTH),
]
EmployeeDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=EMPLOYEE_DESCRIPTION_MAX_LENGTH),
]
EmployeeSystemPrompt = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH,
    ),
]
EmployeeKnowledgeBaseId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    ),
]


class EmployeeConfigurationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: EmployeeName
    description: EmployeeDescription = ""
    system_prompt: EmployeeSystemPrompt
    knowledge_base_id: EmployeeKnowledgeBaseId | None = None


class EmployeeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    name: str
    description: str
    system_prompt: str
    knowledge_base_id: str | None
    allowed_workflow_ids: list[UUID]
    created_at: datetime
    updated_at: datetime


def _application(request: Request) -> EmployeeService:
    application = getattr(request.app.state, "employees", None)
    if not isinstance(application, EmployeeService):
        raise AppError(
            code="employee_service_unavailable",
            message="数字员工服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def _configuration(body: EmployeeConfigurationBody) -> EmployeeConfiguration:
    return EmployeeConfiguration(
        name=body.name,
        description=body.description,
        system_prompt=body.system_prompt,
        knowledge_base_id=body.knowledge_base_id,
    )


def _response(employee: Employee) -> EmployeeResponse:
    return EmployeeResponse.model_validate(employee)


def _employee_error_to_app_error(error: Exception) -> AppError:
    if isinstance(error, KnowledgeServiceError):
        return knowledge_error_to_app_error(error)
    if isinstance(error, EmployeeNotFound):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, EmployeeAlreadyExists):
        return AppError("employee_conflict", "数字员工已存在", 409, False)
    if isinstance(error, EmployeeValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    raise TypeError("unsupported employee application error")


@router.get(
    "",
    response_model=list[EmployeeResponse],
    responses={503: {"model": ErrorEnvelope}},
)
async def list_employees(request: Request) -> list[EmployeeResponse]:
    return [_response(employee) for employee in await _application(request).list()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=EmployeeResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def create_employee(
    request: Request,
    body: EmployeeConfigurationBody,
) -> EmployeeResponse:
    try:
        employee = await _application(request).create(_configuration(body))
    except (EmployeeAlreadyExists, EmployeeValidationError, KnowledgeServiceError) as error:
        raise _employee_error_to_app_error(error) from error
    return _response(employee)


@router.get(
    "/{employee_id}",
    response_model=EmployeeResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def get_employee(request: Request, employee_id: UUID) -> EmployeeResponse:
    try:
        employee = await _application(request).get(employee_id)
    except EmployeeNotFound as error:
        raise _employee_error_to_app_error(error) from error
    return _response(employee)


@router.put(
    "/{employee_id}",
    response_model=EmployeeResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def update_employee(
    request: Request,
    employee_id: UUID,
    body: EmployeeConfigurationBody,
) -> EmployeeResponse:
    try:
        employee = await _application(request).update(employee_id, _configuration(body))
    except (EmployeeNotFound, EmployeeValidationError, KnowledgeServiceError) as error:
        raise _employee_error_to_app_error(error) from error
    return _response(employee)
