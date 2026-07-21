from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from common_agent.audit.models import (
    AuditAction,
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditOutcome,
    AuditPage,
    AuditPolicy,
    AuditQuery,
    AuditResourceType,
    build_audit_event,
)
from common_agent.audit.service import AuditService

TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
ACTOR_ID = UUID("20000000-0000-0000-0000-000000000001")
REQUEST_ID = UUID("30000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 21, 5, 30, tzinfo=UTC)


class RecordingAuditStore:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []
        self.append_limits: list[int] = []
        self.queries: list[AuditQuery] = []

    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        self.append_limits.append(max_events_per_scope)
        previous = self.events[-1].event_hash if self.events else "0" * 64
        event = build_audit_event(
            event_id=uuid4(),
            scope_key=f"tenant:{entry.tenant_id}" if entry.tenant_id else "platform",
            sequence=len(self.events) + 1,
            previous_hash=previous,
            retention_until=retention_until,
            entry=entry,
        )
        self.events.append(event)
        return event

    async def page(self, query: AuditQuery) -> AuditPage:
        self.queries.append(query)
        return AuditPage(items=tuple(reversed(self.events)), next_cursor=None)

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity:
        return AuditIntegrity(
            scope_key=f"tenant:{tenant_id}" if tenant_id else "platform",
            event_count=len(self.events),
            first_sequence=1 if self.events else None,
            last_sequence=len(self.events) or None,
            last_hash=self.events[-1].event_hash if self.events else "0" * 64,
            verified=True,
        )


def _entry() -> AuditEntry:
    return AuditEntry(
        tenant_id=TENANT_ID,
        actor_user_id=ACTOR_ID,
        action=AuditAction.WORKFLOW_RUN_STARTED,
        outcome=AuditOutcome.SUCCEEDED,
        request_id=REQUEST_ID,
        trace_id="1234567890abcdef1234567890abcdef",
        resource_type=AuditResourceType.WORKFLOW_RUN,
        resource_id="50000000-0000-0000-0000-000000000001",
        error_code=None,
        occurred_at=NOW,
    )


def test_service_applies_retention_and_capacity_policy() -> None:
    async def scenario() -> None:
        store = RecordingAuditStore()
        service = AuditService(
            store,
            AuditPolicy(retention_days=365, max_events_per_scope=10_000),
        )

        event = await service.record(_entry())

        assert event.retention_until == NOW + timedelta(days=365)
        assert store.append_limits == [10_000]
        assert service.policy.retention_days == 365
        assert service.policy.automatic_deletion is False

    asyncio.run(scenario())


def test_service_queries_by_tenant_actor_resource_and_time() -> None:
    async def scenario() -> None:
        store = RecordingAuditStore()
        service = AuditService(
            store,
            AuditPolicy(retention_days=365, max_events_per_scope=10_000),
        )
        await service.record(_entry())
        query = AuditQuery(
            tenant_id=TENANT_ID,
            actor_user_id=ACTOR_ID,
            resource_type=AuditResourceType.WORKFLOW_RUN,
            resource_id="50000000-0000-0000-0000-000000000001",
            occurred_from=NOW - timedelta(minutes=1),
            occurred_to=NOW + timedelta(minutes=1),
            limit=20,
            cursor=None,
        )

        page = await service.page(query)
        integrity = await service.verify(TENANT_ID)

        assert page.items[0].tenant_id == TENANT_ID
        assert store.queries == [query]
        assert integrity.verified is True
        assert integrity.event_count == 1

    asyncio.run(scenario())


@pytest.mark.parametrize(
    "values",
    [
        {"retention_days": 0, "max_events_per_scope": 10_000},
        {"retention_days": 3651, "max_events_per_scope": 10_000},
        {"retention_days": 365, "max_events_per_scope": 1},
        {"retention_days": 365, "max_events_per_scope": 10_000_001},
    ],
)
def test_audit_policy_rejects_unsafe_limits(values: dict[str, int]) -> None:
    with pytest.raises(ValueError):
        AuditPolicy(
            retention_days=values["retention_days"],
            max_events_per_scope=values["max_events_per_scope"],
        )
