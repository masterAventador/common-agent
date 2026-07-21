from __future__ import annotations

import logging
import re
import secrets
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import Request, Response

from common_agent.api.errors import AppError, app_error_handler
from common_agent.audit import (
    AuditAction,
    AuditEntry,
    AuditOutcome,
    AuditResourceType,
    AuditService,
)
from common_agent.auth import AuthenticatedSession
from common_agent.tenancy import TenantAccess

RequestHandler = Callable[[Request], Awaitable[Response]]
_LOGGER = logging.getLogger("common_agent.audit")


async def audit_http_request(request: Request, call_next: RequestHandler) -> Response:
    response = await call_next(request)
    classification = _classify(request, response.status_code)
    if classification is None:
        return response
    service = getattr(request.app.state, "audit", None)
    if not isinstance(service, AuditService):
        return response

    action, resource_type, path_parameter = classification
    marked_type = getattr(request.state, "audit_resource_type", None)
    marked_id = getattr(request.state, "audit_resource_id", None)
    if isinstance(marked_type, AuditResourceType):
        resource_type = marked_type
    resource_id: str | None = str(marked_id) if marked_id is not None else None
    if resource_id is None and path_parameter is not None:
        path_value = request.path_params.get(path_parameter)
        if path_value is not None:
            resource_id = str(path_value)
    if resource_type is None or resource_id is None:
        resource_type = None
        resource_id = None

    outcome = _outcome(response.status_code)
    error_code = getattr(request.state, "error_code", None)
    if outcome is not AuditOutcome.SUCCEEDED and not isinstance(error_code, str):
        error_code = f"http_{response.status_code}"
    if outcome is AuditOutcome.SUCCEEDED:
        error_code = None

    entry = AuditEntry(
        tenant_id=_tenant_id(request),
        actor_user_id=_actor_user_id(request),
        action=action,
        outcome=outcome,
        request_id=_request_id(request),
        trace_id=_trace_id(request),
        resource_type=resource_type,
        resource_id=resource_id,
        error_code=error_code,
        occurred_at=datetime.now(UTC),
    )
    try:
        await service.record(entry)
    except Exception as error:
        _LOGGER.exception(
            "audit.event.append_failed",
            extra={"audit_action": action.value, "exception_type": type(error).__name__},
        )
        if response.status_code < 400:
            return await app_error_handler(
                request,
                AppError(
                    "audit_unavailable",
                    "审计记录不可用, 请稍后重试",
                    503,
                    True,
                ),
            )
    return response


def mark_audit_resource(
    request: Request,
    resource_type: AuditResourceType,
    resource_id: UUID | str,
    *,
    tenant_id: UUID | None = None,
    actor_user_id: UUID | None = None,
) -> None:
    request.state.audit_resource_type = resource_type
    request.state.audit_resource_id = str(resource_id)
    if tenant_id is not None:
        request.state.audit_tenant_id = tenant_id
    if actor_user_id is not None:
        request.state.audit_actor_user_id = actor_user_id


def mark_audit_tenant(request: Request, tenant_id: UUID) -> None:
    request.state.audit_tenant_id = tenant_id


def _classify(
    request: Request,
    status_code: int,
) -> tuple[AuditAction, AuditResourceType | None, str | None] | None:
    path = request.url.path
    method = request.method
    error_code = getattr(request.state, "error_code", None)
    if status_code in {401, 403, 429}:
        if isinstance(error_code, str) and (
            error_code.startswith("tenant_") or error_code == "authentication_required"
        ):
            return AuditAction.SECURITY_PERMISSION_DENIED, None, None
        return AuditAction.SECURITY_REQUEST_DENIED, None, None

    exact: dict[tuple[str, str], tuple[AuditAction, AuditResourceType | None, str | None]] = {
        ("POST", "/api/v1/auth/register"): (
            AuditAction.AUTH_REGISTER,
            AuditResourceType.USER,
            None,
        ),
        ("POST", "/api/v1/auth/login"): (
            AuditAction.AUTH_LOGIN,
            AuditResourceType.USER,
            None,
        ),
        ("POST", "/api/v1/auth/logout"): (
            AuditAction.AUTH_LOGOUT,
            AuditResourceType.USER,
            None,
        ),
        ("POST", "/api/v1/auth/recovery/reset"): (
            AuditAction.AUTH_RECOVERY_RESET,
            None,
            None,
        ),
        ("POST", "/api/v1/tenants"): (AuditAction.TENANT_CREATED, AuditResourceType.TENANT, None),
        ("POST", "/api/v1/employees"): (
            AuditAction.EMPLOYEE_CREATED,
            AuditResourceType.EMPLOYEE,
            None,
        ),
        ("POST", "/api/v1/knowledge-bases"): (
            AuditAction.KNOWLEDGE_BASE_CREATED,
            AuditResourceType.KNOWLEDGE_BASE,
            None,
        ),
        ("POST", "/api/v1/workflows"): (
            AuditAction.WORKFLOW_CONFIGURATION_UPDATED,
            AuditResourceType.WORKFLOW,
            None,
        ),
    }
    matched = exact.get((method, path))
    if matched is not None:
        return matched
    patterns = (
        (
            "POST",
            r"/api/v1/tenants/[^/]+/members",
            AuditAction.AUTH_MEMBER_PROVISIONED,
            AuditResourceType.USER,
            None,
        ),
        (
            "PUT",
            r"/api/v1/employees/[^/]+",
            AuditAction.EMPLOYEE_CONFIGURATION_AND_BINDINGS_UPDATED,
            AuditResourceType.EMPLOYEE,
            "employee_id",
        ),
        (
            "DELETE",
            r"/api/v1/employees/[^/]+",
            AuditAction.RESOURCE_DELETED,
            AuditResourceType.EMPLOYEE,
            "employee_id",
        ),
        (
            "DELETE",
            r"/api/v1/knowledge-bases/[^/]+",
            AuditAction.RESOURCE_DELETED,
            AuditResourceType.KNOWLEDGE_BASE,
            "knowledge_base_id",
        ),
        (
            "POST",
            r"/api/v1/knowledge-bases/[^/]+/documents",
            AuditAction.KNOWLEDGE_DOCUMENT_UPLOADED,
            AuditResourceType.KNOWLEDGE_DOCUMENT,
            None,
        ),
        (
            "PUT",
            r"/api/v1/workflows/[^/]+",
            AuditAction.WORKFLOW_CONFIGURATION_UPDATED,
            AuditResourceType.WORKFLOW,
            "workflow_id",
        ),
        (
            "DELETE",
            r"/api/v1/workflows/[^/]+",
            AuditAction.RESOURCE_DELETED,
            AuditResourceType.WORKFLOW,
            "workflow_id",
        ),
        (
            "POST",
            r"/api/v1/workflows/[^/]+/runs",
            AuditAction.WORKFLOW_RUN_STARTED,
            AuditResourceType.WORKFLOW_RUN,
            None,
        ),
        (
            "POST",
            r"/api/v1/workflow-runs/[^/]+/stop",
            AuditAction.WORKFLOW_RUN_STOPPED,
            AuditResourceType.WORKFLOW_RUN,
            "run_id",
        ),
        (
            "POST",
            r"/api/v1/conversations/[^/]+/messages",
            AuditAction.CONVERSATION_REPLY_STARTED,
            AuditResourceType.CONVERSATION,
            "conversation_id",
        ),
        (
            "DELETE",
            r"/api/v1/conversations/[^/]+",
            AuditAction.RESOURCE_DELETED,
            AuditResourceType.CONVERSATION,
            "conversation_id",
        ),
    )
    for expected_method, pattern, action, resource_type, parameter in patterns:
        if method == expected_method and re.fullmatch(pattern, path):
            return action, resource_type, parameter
    return None


def _outcome(status_code: int) -> AuditOutcome:
    if status_code < 400:
        return AuditOutcome.SUCCEEDED
    if status_code in {401, 403, 429}:
        return AuditOutcome.DENIED
    return AuditOutcome.FAILED


def _tenant_id(request: Request) -> UUID | None:
    access = getattr(request.state, "tenant_access", None)
    if isinstance(access, TenantAccess):
        return access.tenant_id
    marked = getattr(request.state, "audit_tenant_id", None)
    return marked if isinstance(marked, UUID) else None


def _actor_user_id(request: Request) -> UUID | None:
    session = getattr(request.state, "authenticated_session", None)
    if isinstance(session, AuthenticatedSession):
        return UUID(session.user_id)
    marked = getattr(request.state, "audit_actor_user_id", None)
    return marked if isinstance(marked, UUID) else None


def _request_id(request: Request) -> UUID:
    raw = getattr(request.state, "request_id", None)
    try:
        return UUID(raw) if isinstance(raw, str) else uuid4()
    except ValueError:
        return uuid4()


def _trace_id(request: Request) -> str:
    raw = getattr(request.state, "trace_id", None)
    if isinstance(raw, str) and re.fullmatch(r"[0-9a-f]{32}", raw):
        return raw
    return secrets.token_hex(16)


__all__ = ["audit_http_request", "mark_audit_resource", "mark_audit_tenant"]
