from __future__ import annotations

from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StringConstraints

from common_agent.api.audit import mark_audit_resource
from common_agent.api.authentication import authenticate_request, require_authenticated
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.tenancy import tenancy_error_to_app_error, tenancy_service
from common_agent.audit import AuditResourceType
from common_agent.auth import (
    AuthenticationError,
    AuthenticationService,
    PasswordPolicyError,
)
from common_agent.tenancy import TenancyError, TenantAccess, TenantRole

router = APIRouter(
    prefix="/api/v1/tenants",
    tags=["tenancy"],
    dependencies=[Depends(require_authenticated)],
    responses={401: {"model": ErrorEnvelope}},
)


class TenantAccessResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    organization_id: UUID
    organization_name: str
    role: TenantRole


class CreateTenantBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    organization_id: UUID
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class CreateTenantMemberBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: Annotated[str, Field(min_length=3, max_length=254)]
    password: Annotated[SecretStr, Field(min_length=15, max_length=128)]
    role: Literal["editor", "viewer"]


class TenantMemberProvisioningResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: UUID
    email: str
    role: TenantRole
    recovery_codes: tuple[str, ...]


@router.get("", response_model=list[TenantAccessResponse])
async def list_tenants(request: Request) -> list[TenantAccessResponse]:
    session = await authenticate_request(request)
    accesses = await tenancy_service(request).list_access(UUID(session.user_id))
    return [_response(access) for access in accesses]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=TenantAccessResponse,
    responses={403: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def create_tenant(body: CreateTenantBody, request: Request) -> TenantAccessResponse:
    session = await authenticate_request(request)
    try:
        created = await tenancy_service(request).create_tenant(
            owner_user_id=UUID(session.user_id),
            organization_id=body.organization_id,
            name=body.name,
        )
    except TenancyError as error:
        raise tenancy_error_to_app_error(error) from error
    mark_audit_resource(
        request,
        AuditResourceType.TENANT,
        created.tenant_id,
        tenant_id=created.tenant_id,
        actor_user_id=UUID(session.user_id),
    )
    return _response(created)


@router.post(
    "/{tenant_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=TenantMemberProvisioningResponse,
    responses={403: {"model": ErrorEnvelope}, 409: {"model": ErrorEnvelope}},
)
async def provision_tenant_member(
    tenant_id: UUID,
    body: CreateTenantMemberBody,
    request: Request,
    response: Response,
) -> TenantMemberProvisioningResponse:
    session = await authenticate_request(request)
    try:
        await tenancy_service(request).resolve(
            UUID(session.user_id),
            tenant_id,
            administer=True,
        )
    except TenancyError as error:
        raise tenancy_error_to_app_error(error) from error

    authentication = getattr(request.app.state, "authentication", None)
    if not isinstance(authentication, AuthenticationService):
        raise AppError("authentication_unavailable", "认证服务暂时不可用", 503, True)
    try:
        provisioned = await authentication.provision_member(
            tenant_id=tenant_id,
            email=body.email,
            password=body.password.get_secret_value(),
            role=TenantRole(body.role),
        )
    except AuthenticationError as error:
        if error.code == "member_conflict":
            raise AppError("member_conflict", "成员账号已存在", 409, False) from error
        raise AppError(error.code, "成员账号创建失败", 422, False) from error
    except PasswordPolicyError as error:
        raise AppError("validation_error", "请求参数不合法", 422, False) from error

    response.headers["Cache-Control"] = "no-store"
    mark_audit_resource(
        request,
        AuditResourceType.USER,
        provisioned.user_id,
        tenant_id=tenant_id,
        actor_user_id=UUID(session.user_id),
    )
    return TenantMemberProvisioningResponse(
        user_id=UUID(provisioned.user_id),
        email=provisioned.email,
        role=provisioned.role,
        recovery_codes=provisioned.recovery_codes,
    )


def _response(access: TenantAccess) -> TenantAccessResponse:
    if access.organization_id is None:
        raise RuntimeError("租户缺少组织归属")
    return TenantAccessResponse(
        id=access.tenant_id,
        name=access.tenant_name,
        organization_id=access.organization_id,
        organization_name=access.organization_name,
        role=access.role,
    )


__all__ = ["TenantAccessResponse", "router"]
