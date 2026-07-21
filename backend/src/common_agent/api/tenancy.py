from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header, Query, Request

from common_agent.api.authentication import authenticate_request
from common_agent.api.errors import AppError
from common_agent.tenancy import TenancyError, TenancyService, TenantAccess, activate_tenant

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


async def require_tenant_access(
    request: Request,
    header_tenant_id: Annotated[UUID | None, Header(alias="X-Tenant-ID")] = None,
    query_tenant_id: Annotated[UUID | None, Query(alias="tenant_id")] = None,
) -> TenantAccess:
    if (
        header_tenant_id is not None
        and query_tenant_id is not None
        and header_tenant_id != query_tenant_id
    ):
        raise AppError("tenant_selection_conflict", "租户选择冲突", 422, False)
    selected_tenant_id = header_tenant_id or query_tenant_id
    session = await authenticate_request(request)
    try:
        access = await tenancy_service(request).resolve(
            UUID(session.user_id),
            selected_tenant_id,
            write=request.method not in _SAFE_METHODS,
        )
    except TenancyError as error:
        raise tenancy_error_to_app_error(error) from error
    request.state.tenant_access = access
    activate_tenant(access)
    return access


def tenancy_service(request: Request) -> TenancyService:
    service = getattr(request.app.state, "tenancy", None)
    if not isinstance(service, TenancyService):
        raise AppError("tenancy_unavailable", "租户服务暂时不可用", 503, True)
    return service


def tenancy_error_to_app_error(error: TenancyError) -> AppError:
    mapping = {
        "tenant_access_denied": ("无权访问该租户", 403),
        "tenant_selection_required": ("请选择要访问的工作区", 409),
        "tenant_write_forbidden": ("当前角色无权修改工作区资源", 403),
        "tenant_admin_forbidden": ("当前角色无权管理工作区", 403),
        "tenant_conflict": ("工作区名称已存在", 409),
    }
    message, status_code = mapping.get(error.code, ("租户请求失败", 403))
    return AppError(error.code, message, status_code, False)


__all__ = ["require_tenant_access", "tenancy_error_to_app_error", "tenancy_service"]
