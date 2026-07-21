from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.audit import (
    AuditAction,
    AuditEvent,
    AuditOutcome,
    AuditQuery,
    AuditResourceType,
    AuditService,
)
from common_agent.tenancy import TenantAccess, TenantRole

router = APIRouter(
    prefix="/api/v1/audit-events",
    tags=["audit"],
    responses={403: {"model": ErrorEnvelope}, 422: {"model": ErrorEnvelope}},
)


class AuditEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sequence: int
    event_id: UUID
    tenant_id: UUID | None
    actor_user_id: UUID | None
    action: AuditAction
    outcome: AuditOutcome
    request_id: UUID
    trace_id: str
    resource_type: AuditResourceType | None
    resource_id: str | None
    error_code: str | None
    occurred_at: datetime
    retention_until: datetime
    previous_hash: str
    event_hash: str


class AuditPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[AuditEventResponse]
    next_cursor: str | None


class AuditIntegrityResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_count: int
    first_sequence: int | None
    last_sequence: int | None
    last_hash: str
    verified: bool
    broken_sequence: int | None


class AuditPolicyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    retention_days: int
    max_events_per_scope: int
    automatic_deletion: bool


@router.get("", response_model=AuditPageResponse)
async def list_audit_events(
    request: Request,
    scope: Literal["tenant", "platform"] = "tenant",
    actor_user_id: UUID | None = None,
    resource_type: AuditResourceType | None = None,
    resource_id: Annotated[str | None, Query(min_length=1, max_length=128)] = None,
    action: AuditAction | None = None,
    occurred_from: datetime | None = None,
    occurred_to: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    cursor: Annotated[str | None, Query(min_length=1, max_length=20)] = None,
) -> AuditPageResponse:
    access = _owner_access(request)
    try:
        query = AuditQuery(
            tenant_id=access.tenant_id if scope == "tenant" else None,
            actor_user_id=actor_user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            action=action,
            occurred_from=_utc(occurred_from),
            occurred_to=_utc(occurred_to),
            limit=limit,
            cursor=cursor,
        )
        page = await _service(request).page(query)
    except ValueError as error:
        raise AppError("invalid_audit_query", "审计查询参数不合法", 422, False) from error
    return AuditPageResponse(
        items=[_event_response(event) for event in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/integrity", response_model=AuditIntegrityResponse)
async def verify_audit_integrity(
    request: Request,
    scope: Literal["tenant", "platform"] = "tenant",
) -> AuditIntegrityResponse:
    access = _owner_access(request)
    tenant_id = access.tenant_id if scope == "tenant" else None
    integrity = await _service(request).verify(tenant_id)
    return AuditIntegrityResponse(
        event_count=integrity.event_count,
        first_sequence=integrity.first_sequence,
        last_sequence=integrity.last_sequence,
        last_hash=integrity.last_hash,
        verified=integrity.verified,
        broken_sequence=integrity.broken_sequence,
    )


@router.get("/policy", response_model=AuditPolicyResponse)
async def audit_policy(request: Request) -> AuditPolicyResponse:
    _owner_access(request)
    policy = _service(request).policy
    return AuditPolicyResponse(
        retention_days=policy.retention_days,
        max_events_per_scope=policy.max_events_per_scope,
        automatic_deletion=policy.automatic_deletion,
    )


def _service(request: Request) -> AuditService:
    service = getattr(request.app.state, "audit", None)
    if not isinstance(service, AuditService):
        raise AppError("audit_unavailable", "审计服务暂时不可用", 503, True)
    return service


def _owner_access(request: Request) -> TenantAccess:
    access = getattr(request.state, "tenant_access", None)
    if not isinstance(access, TenantAccess):
        raise AppError("tenant_access_denied", "无权访问该租户", 403, False)
    if access.role is not TenantRole.OWNER:
        raise AppError("tenant_admin_forbidden", "当前角色无权管理工作区", 403, False)
    return access


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        raise ValueError("audit time must include a timezone")
    return value.astimezone(UTC)


def _event_response(event: AuditEvent) -> AuditEventResponse:
    return AuditEventResponse(
        sequence=event.sequence,
        event_id=event.event_id,
        tenant_id=event.tenant_id,
        actor_user_id=event.actor_user_id,
        action=event.action,
        outcome=event.outcome,
        request_id=event.request_id,
        trace_id=event.trace_id,
        resource_type=event.resource_type,
        resource_id=event.resource_id,
        error_code=event.error_code,
        occurred_at=event.occurred_at,
        retention_until=event.retention_until,
        previous_hash=event.previous_hash,
        event_hash=event.event_hash,
    )


__all__ = ["AuditEventResponse", "router"]
