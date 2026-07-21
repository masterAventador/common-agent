from __future__ import annotations

from dataclasses import fields
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from common_agent.audit.models import (
    AuditAction,
    AuditEntry,
    AuditEvent,
    AuditOutcome,
    AuditResourceType,
    build_audit_event,
)

TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
ACTOR_ID = UUID("20000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("30000000-0000-0000-0000-000000000001")
EVENT_ID = UUID("40000000-0000-0000-0000-000000000001")
OCCURRED_AT = datetime(2026, 7, 21, 5, 0, tzinfo=UTC)
TRACE_ID = "1234567890abcdef1234567890abcdef"
GENESIS_HASH = "0" * 64


def _entry(**overrides: object) -> AuditEntry:
    values: dict[str, object] = {
        "tenant_id": TENANT_ID,
        "actor_user_id": ACTOR_ID,
        "action": AuditAction.EMPLOYEE_CONFIGURATION_AND_BINDINGS_UPDATED,
        "outcome": AuditOutcome.SUCCEEDED,
        "request_id": REQUEST_ID,
        "trace_id": TRACE_ID,
        "resource_type": AuditResourceType.EMPLOYEE,
        "resource_id": "50000000-0000-0000-0000-000000000001",
        "error_code": None,
        "occurred_at": OCCURRED_AT,
    }
    values.update(overrides)
    return AuditEntry(**values)  # type: ignore[arg-type]


def test_audit_contract_has_fixed_actions_and_no_payload_fields() -> None:
    assert AuditAction.AUTH_LOGIN.value == "auth.login"
    assert AuditAction.KNOWLEDGE_DOCUMENT_UPLOADED.value == "knowledge.document.uploaded"
    assert AuditAction.SECURITY_PERMISSION_DENIED.value == "security.permission.denied"
    assert AuditOutcome.DENIED.value == "denied"

    entry_fields = {field.name for field in fields(AuditEntry)}
    assert entry_fields == {
        "tenant_id",
        "actor_user_id",
        "action",
        "outcome",
        "request_id",
        "trace_id",
        "resource_type",
        "resource_id",
        "error_code",
        "occurred_at",
    }
    assert not entry_fields.intersection(
        {"body", "content", "details", "metadata", "password", "token", "credential"}
    )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"occurred_at": datetime(2026, 7, 21, 5, 0)}, "UTC"),
        ({"trace_id": "not-a-trace"}, "trace"),
        ({"resource_type": None}, "resource"),
        ({"resource_id": None}, "resource"),
        ({"resource_id": " secret\nvalue "}, "resource"),
        ({"outcome": AuditOutcome.FAILED, "error_code": None}, "error"),
        (
            {"outcome": AuditOutcome.DENIED, "error_code": "contains secret text"},
            "error",
        ),
        ({"outcome": AuditOutcome.SUCCEEDED, "error_code": "unexpected"}, "error"),
    ],
)
def test_audit_entry_rejects_unsafe_or_ambiguous_values(
    overrides: dict[str, object],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _entry(**overrides)


def test_audit_event_hash_is_deterministic_and_links_to_previous_event() -> None:
    retention_until = OCCURRED_AT + timedelta(days=365)
    first = build_audit_event(
        event_id=EVENT_ID,
        scope_key=f"tenant:{TENANT_ID}",
        sequence=1,
        previous_hash=GENESIS_HASH,
        retention_until=retention_until,
        entry=_entry(),
    )
    repeated = build_audit_event(
        event_id=EVENT_ID,
        scope_key=f"tenant:{TENANT_ID}",
        sequence=1,
        previous_hash=GENESIS_HASH,
        retention_until=retention_until,
        entry=_entry(),
    )
    second = build_audit_event(
        event_id=UUID("40000000-0000-0000-0000-000000000002"),
        scope_key=f"tenant:{TENANT_ID}",
        sequence=2,
        previous_hash=first.event_hash,
        retention_until=retention_until,
        entry=_entry(request_id=UUID("30000000-0000-0000-0000-000000000002")),
    )

    assert isinstance(first, AuditEvent)
    assert first.event_hash == repeated.event_hash
    assert len(first.event_hash) == 64
    assert second.previous_hash == first.event_hash
    assert second.event_hash != first.event_hash
    assert "content" not in first.canonical_payload()
    assert "password" not in first.canonical_payload()


def test_platform_security_event_uses_platform_scope_without_actor_or_resource() -> None:
    entry = _entry(
        tenant_id=None,
        actor_user_id=None,
        action=AuditAction.SECURITY_REQUEST_DENIED,
        outcome=AuditOutcome.DENIED,
        resource_type=None,
        resource_id=None,
        error_code="origin_validation_failed",
    )
    event = build_audit_event(
        event_id=EVENT_ID,
        scope_key="platform",
        sequence=1,
        previous_hash=GENESIS_HASH,
        retention_until=OCCURRED_AT + timedelta(days=365),
        entry=entry,
    )

    assert event.tenant_id is None
    assert event.actor_user_id is None
    assert event.scope_key == "platform"
