from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DatabaseError

from common_agent.adapters.persistence.audit import SqlAlchemyAuditStore
from common_agent.adapters.persistence.database import Database
from common_agent.audit import (
    AuditAction,
    AuditCapacityExceeded,
    AuditEntry,
    AuditOutcome,
    AuditQuery,
    AuditResourceType,
)
from tests.support.settings import TEST_DATABASE_URL


def test_audit_repository_is_append_only_queryable_and_hash_chained() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        tenant_id = uuid4()
        actor_id = uuid4()
        request_id = uuid4()
        now = datetime.now(UTC).replace(microsecond=123456)
        store = SqlAlchemyAuditStore(database)
        try:
            first = await store.append(
                _entry(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    request_id=request_id,
                    now=now,
                    action=AuditAction.EMPLOYEE_CONFIGURATION_AND_BINDINGS_UPDATED,
                    resource_type=AuditResourceType.EMPLOYEE,
                    resource_id="employee-1",
                ),
                retention_until=now + timedelta(days=365),
                max_events_per_scope=100,
            )
            second = await store.append(
                _entry(
                    tenant_id=tenant_id,
                    actor_id=actor_id,
                    request_id=uuid4(),
                    now=now + timedelta(seconds=1),
                    action=AuditAction.SECURITY_PERMISSION_DENIED,
                    outcome=AuditOutcome.DENIED,
                    resource_type=AuditResourceType.EMPLOYEE,
                    resource_id="employee-1",
                    error_code="tenant_write_forbidden",
                ),
                retention_until=now + timedelta(days=365, seconds=1),
                max_events_per_scope=100,
            )

            assert first.sequence == 1
            assert second.sequence == 2
            assert second.previous_hash == first.event_hash

            page = await store.page(
                AuditQuery(
                    tenant_id=tenant_id,
                    actor_user_id=actor_id,
                    resource_type=AuditResourceType.EMPLOYEE,
                    resource_id="employee-1",
                    occurred_from=now - timedelta(seconds=1),
                    occurred_to=now + timedelta(seconds=2),
                    limit=1,
                )
            )
            assert [event.sequence for event in page.items] == [2]
            assert page.next_cursor == "2"
            older = await store.page(
                AuditQuery(tenant_id=tenant_id, limit=10, cursor=page.next_cursor)
            )
            assert [event.sequence for event in older.items] == [1]

            integrity = await store.verify(tenant_id)
            assert integrity.verified is True
            assert integrity.event_count == 2
            assert integrity.first_sequence == 1
            assert integrity.last_sequence == 2
            assert integrity.last_hash == second.event_hash

            async with database.session() as session:
                with pytest.raises(DatabaseError):
                    await session.execute(
                        text("UPDATE audit_events SET action = 'auth.login' WHERE event_id = :id"),
                        {"id": str(first.event_id)},
                    )
                    await session.commit()
            async with database.session() as session:
                with pytest.raises(DatabaseError):
                    await session.execute(
                        text("DELETE FROM audit_events WHERE event_id = :id"),
                        {"id": str(first.event_id)},
                    )
                    await session.commit()
        finally:
            await database.stop()

    asyncio.run(scenario())


def test_audit_repository_fails_closed_at_scope_capacity() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        tenant_id = uuid4()
        now = datetime.now(UTC)
        store = SqlAlchemyAuditStore(database)
        try:
            for index in range(2):
                await store.append(
                    _entry(
                        tenant_id=tenant_id,
                        actor_id=None,
                        request_id=uuid4(),
                        now=now + timedelta(seconds=index),
                        action=AuditAction.AUTH_LOGIN,
                        resource_type=AuditResourceType.SESSION,
                        resource_id=f"session-{index}",
                    ),
                    retention_until=now + timedelta(days=365, seconds=index),
                    max_events_per_scope=2,
                )
            with pytest.raises(AuditCapacityExceeded):
                await store.append(
                    _entry(
                        tenant_id=tenant_id,
                        actor_id=None,
                        request_id=uuid4(),
                        now=now + timedelta(seconds=2),
                        action=AuditAction.AUTH_LOGIN,
                        resource_type=AuditResourceType.SESSION,
                        resource_id="session-2",
                    ),
                    retention_until=now + timedelta(days=365, seconds=2),
                    max_events_per_scope=2,
                )
        finally:
            await database.stop()

    asyncio.run(scenario())


def test_audit_repository_queries_the_platform_security_scope() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        now = datetime.now(UTC)
        store = SqlAlchemyAuditStore(database)
        try:
            recorded = await store.append(
                AuditEntry(
                    tenant_id=None,
                    actor_user_id=None,
                    action=AuditAction.AUTH_RECOVERY_RESET,
                    outcome=AuditOutcome.DENIED,
                    request_id=uuid4(),
                    trace_id="1234567890abcdef1234567890abcdef",
                    resource_type=None,
                    resource_id=None,
                    error_code="invalid_recovery_credentials",
                    occurred_at=now,
                ),
                retention_until=now + timedelta(days=365),
                max_events_per_scope=10_000_000,
            )

            page = await store.page(
                AuditQuery(
                    tenant_id=None,
                    action=AuditAction.AUTH_RECOVERY_RESET,
                    occurred_from=now,
                    limit=10,
                )
            )

            assert page.items == (recorded,)
            assert (await store.verify(None)).verified is True
        finally:
            await database.stop()

    asyncio.run(scenario())


def _entry(
    *,
    tenant_id: UUID,
    actor_id: UUID | None,
    request_id: UUID,
    now: datetime,
    action: AuditAction,
    resource_type: AuditResourceType,
    resource_id: str,
    outcome: AuditOutcome = AuditOutcome.SUCCEEDED,
    error_code: str | None = None,
) -> AuditEntry:
    return AuditEntry(
        tenant_id=tenant_id,
        actor_user_id=actor_id,
        action=action,
        outcome=outcome,
        request_id=request_id,
        trace_id="1234567890abcdef1234567890abcdef",
        resource_type=resource_type,
        resource_id=resource_id,
        error_code=error_code,
        occurred_at=now,
    )
