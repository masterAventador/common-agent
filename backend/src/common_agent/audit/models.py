from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_TRACE_PATTERN = re.compile(r"^[0-9a-f]{32}$")
_ERROR_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")


class AuditAction(StrEnum):
    AUTH_REGISTER = "auth.register"
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_RECOVERY_RESET = "auth.recovery.reset"
    AUTH_MEMBER_PROVISIONED = "auth.member.provisioned"
    TENANT_CREATED = "tenant.created"
    EMPLOYEE_CREATED = "employee.created"
    EMPLOYEE_CONFIGURATION_AND_BINDINGS_UPDATED = "employee.configuration_and_bindings.updated"
    TOOL_GRANTS_UPDATED = "tool.grants.updated"
    MODEL_CONFIGURATION_CREATED = "model.configuration.created"
    MODEL_CONFIGURATION_UPDATED = "model.configuration.updated"
    MODEL_CONFIGURATION_VERIFIED = "model.configuration.verified"
    KNOWLEDGE_BASE_CREATED = "knowledge.base.created"
    KNOWLEDGE_DOCUMENT_UPLOADED = "knowledge.document.uploaded"
    KNOWLEDGE_DOCUMENT_RETRY_STARTED = "knowledge.document.retry_started"
    RESOURCE_DELETED = "resource.deleted"
    CONVERSATION_REPLY_STARTED = "conversation.reply.started"
    WORKFLOW_CONFIGURATION_UPDATED = "workflow.configuration.updated"
    WORKFLOW_RUN_STARTED = "workflow.run.started"
    WORKFLOW_RUN_STOPPED = "workflow.run.stopped"
    SECURITY_PERMISSION_DENIED = "security.permission.denied"
    SECURITY_REQUEST_DENIED = "security.request.denied"


class AuditOutcome(StrEnum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    DENIED = "denied"
    FAILED = "failed"


class AuditResourceType(StrEnum):
    USER = "user"
    SESSION = "session"
    TENANT = "tenant"
    EMPLOYEE = "employee"
    MODEL_CONFIGURATION = "model_configuration"
    KNOWLEDGE_BASE = "knowledge_base"
    KNOWLEDGE_DOCUMENT = "knowledge_document"
    CONVERSATION = "conversation"
    WORKFLOW = "workflow"
    WORKFLOW_RUN = "workflow_run"


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """Metadata-only audit input. Request bodies and arbitrary metadata are impossible by type."""

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

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() != UTC.utcoffset(None):
            raise ValueError("occurred_at must use UTC")
        if not _TRACE_PATTERN.fullmatch(self.trace_id):
            raise ValueError("trace_id must contain 32 lowercase hexadecimal characters")
        if (self.resource_type is None) != (self.resource_id is None):
            raise ValueError("resource_type and resource_id must be provided together")
        if self.resource_id is not None and (
            self.resource_id != self.resource_id.strip()
            or not 1 <= len(self.resource_id) <= 128
            or any(character in self.resource_id for character in "\r\n\0")
        ):
            raise ValueError("resource_id must be a safe trimmed identifier")
        if self.outcome in {AuditOutcome.STARTED, AuditOutcome.SUCCEEDED}:
            if self.error_code is not None:
                raise ValueError("started or successful audit entries cannot have an error_code")
        elif self.error_code is None or not _ERROR_PATTERN.fullmatch(self.error_code):
            raise ValueError("denied or failed audit entries require a normalized error_code")


@dataclass(frozen=True, slots=True)
class AuditEvent(AuditEntry):
    event_id: UUID
    scope_key: str
    sequence: int
    previous_hash: str
    event_hash: str
    retention_until: datetime

    def canonical_payload(self) -> str:
        return _canonical_payload(
            event_id=self.event_id,
            scope_key=self.scope_key,
            sequence=self.sequence,
            previous_hash=self.previous_hash,
            retention_until=self.retention_until,
            entry=self,
        )


@dataclass(frozen=True, slots=True)
class AuditPolicy:
    retention_days: int = 365
    max_events_per_scope: int = 1_000_000
    automatic_deletion: bool = False

    def __post_init__(self) -> None:
        if not 30 <= self.retention_days <= 3650:
            raise ValueError("retention_days must be between 30 and 3650")
        if not 100 <= self.max_events_per_scope <= 10_000_000:
            raise ValueError("max_events_per_scope must be between 100 and 10000000")
        if self.automatic_deletion:
            raise ValueError("automatic audit deletion is forbidden")


@dataclass(frozen=True, slots=True)
class AuditQuery:
    tenant_id: UUID | None
    actor_user_id: UUID | None = None
    resource_type: AuditResourceType | None = None
    resource_id: str | None = None
    action: AuditAction | None = None
    occurred_from: datetime | None = None
    occurred_to: datetime | None = None
    limit: int = 50
    cursor: str | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.limit <= 200:
            raise ValueError("limit must be between 1 and 200")
        if (self.resource_type is None) != (self.resource_id is None):
            raise ValueError("resource filters must be provided together")
        for value in (self.occurred_from, self.occurred_to):
            if value is not None and (
                value.tzinfo is None or value.utcoffset() != UTC.utcoffset(None)
            ):
                raise ValueError("audit query times must use UTC")
        if (
            self.occurred_from is not None
            and self.occurred_to is not None
            and self.occurred_from > self.occurred_to
        ):
            raise ValueError("occurred_from must not be after occurred_to")


@dataclass(frozen=True, slots=True)
class AuditPage:
    items: tuple[AuditEvent, ...] = field(default_factory=tuple)
    next_cursor: str | None = None


@dataclass(frozen=True, slots=True)
class AuditIntegrity:
    scope_key: str
    event_count: int
    first_sequence: int | None
    last_sequence: int | None
    last_hash: str
    verified: bool
    broken_sequence: int | None = None


def build_audit_event(
    *,
    event_id: UUID,
    scope_key: str,
    sequence: int,
    previous_hash: str,
    retention_until: datetime,
    entry: AuditEntry,
) -> AuditEvent:
    expected_scope = f"tenant:{entry.tenant_id}" if entry.tenant_id is not None else "platform"
    if scope_key != expected_scope:
        raise ValueError("scope_key does not match the audit tenant")
    if sequence < 1:
        raise ValueError("sequence must be positive")
    if not _HASH_PATTERN.fullmatch(previous_hash):
        raise ValueError("previous_hash must be a SHA-256 digest")
    if retention_until.tzinfo is None or retention_until.utcoffset() != UTC.utcoffset(None):
        raise ValueError("retention_until must use UTC")
    if retention_until <= entry.occurred_at:
        raise ValueError("retention_until must be after occurred_at")
    canonical = _canonical_payload(
        event_id=event_id,
        scope_key=scope_key,
        sequence=sequence,
        previous_hash=previous_hash,
        retention_until=retention_until,
        entry=entry,
    )
    event_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return AuditEvent(
        tenant_id=entry.tenant_id,
        actor_user_id=entry.actor_user_id,
        action=entry.action,
        outcome=entry.outcome,
        request_id=entry.request_id,
        trace_id=entry.trace_id,
        resource_type=entry.resource_type,
        resource_id=entry.resource_id,
        error_code=entry.error_code,
        occurred_at=entry.occurred_at,
        event_id=event_id,
        scope_key=scope_key,
        sequence=sequence,
        previous_hash=previous_hash,
        event_hash=event_hash,
        retention_until=retention_until,
    )


def _canonical_payload(
    *,
    event_id: UUID,
    scope_key: str,
    sequence: int,
    previous_hash: str,
    retention_until: datetime,
    entry: AuditEntry,
) -> str:
    payload = {
        "action": entry.action.value,
        "actor_user_id": str(entry.actor_user_id) if entry.actor_user_id else None,
        "error_code": entry.error_code,
        "event_id": str(event_id),
        "occurred_at": entry.occurred_at.isoformat(),
        "outcome": entry.outcome.value,
        "previous_hash": previous_hash,
        "request_id": str(entry.request_id),
        "resource_id": entry.resource_id,
        "resource_type": entry.resource_type.value if entry.resource_type else None,
        "retention_until": retention_until.isoformat(),
        "scope_key": scope_key,
        "sequence": sequence,
        "tenant_id": str(entry.tenant_id) if entry.tenant_id else None,
        "trace_id": entry.trace_id,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
