from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import AuditChainHeadRow, AuditEventRow
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.audit import (
    AuditAction,
    AuditCapacityExceeded,
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditOutcome,
    AuditPage,
    AuditQuery,
    AuditResourceType,
    build_audit_event,
)

_GENESIS_HASH = "0" * 64


class SqlAlchemyAuditStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        for attempt in range(3):
            try:
                return await self._append_once(
                    entry,
                    retention_until=retention_until,
                    max_events_per_scope=max_events_per_scope,
                )
            except IntegrityError:
                if attempt == 2:
                    raise
        raise RuntimeError("审计事件追加重试耗尽")

    async def _append_once(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        scope_key = _scope_key(entry.tenant_id)
        database_now = to_database_datetime(entry.occurred_at)
        async with self._database.session() as session:
            head = await session.scalar(
                select(AuditChainHeadRow)
                .where(AuditChainHeadRow.scope_key == scope_key)
                .with_for_update()
            )
            if head is None:
                head = AuditChainHeadRow(
                    scope_key=scope_key,
                    tenant_id=str(entry.tenant_id) if entry.tenant_id is not None else None,
                    event_count=0,
                    last_hash=_GENESIS_HASH,
                    created_at=database_now,
                    updated_at=database_now,
                )
                session.add(head)
                await session.flush()
            if head.event_count >= max_events_per_scope:
                raise AuditCapacityExceeded(
                    f"audit scope {scope_key} reached its configured capacity"
                )

            event = build_audit_event(
                event_id=uuid4(),
                scope_key=scope_key,
                sequence=head.event_count + 1,
                previous_hash=head.last_hash,
                retention_until=retention_until,
                entry=entry,
            )
            session.add(_to_row(event))
            head.event_count = event.sequence
            head.last_hash = event.event_hash
            head.updated_at = database_now
            await session.commit()
            return event

    async def page(self, query: AuditQuery) -> AuditPage:
        statement: Select[tuple[AuditEventRow]] = select(AuditEventRow)
        if query.tenant_id is None:
            statement = statement.where(AuditEventRow.tenant_id.is_(None))
        else:
            statement = statement.where(AuditEventRow.tenant_id == str(query.tenant_id))
        if query.actor_user_id is not None:
            statement = statement.where(AuditEventRow.actor_user_id == str(query.actor_user_id))
        if query.resource_type is not None:
            statement = statement.where(
                AuditEventRow.resource_type == query.resource_type.value,
                AuditEventRow.resource_id == query.resource_id,
            )
        if query.action is not None:
            statement = statement.where(AuditEventRow.action == query.action.value)
        if query.occurred_from is not None:
            statement = statement.where(
                AuditEventRow.occurred_at >= to_database_datetime(query.occurred_from)
            )
        if query.occurred_to is not None:
            statement = statement.where(
                AuditEventRow.occurred_at <= to_database_datetime(query.occurred_to)
            )
        if query.cursor is not None:
            try:
                before_sequence = int(query.cursor)
            except ValueError as error:
                raise ValueError("invalid audit cursor") from error
            if before_sequence < 1 or str(before_sequence) != query.cursor:
                raise ValueError("invalid audit cursor")
            statement = statement.where(AuditEventRow.sequence < before_sequence)
        statement = statement.order_by(AuditEventRow.sequence.desc()).limit(query.limit + 1)

        async with self._database.session() as session:
            rows = list(await session.scalars(statement))
        has_more = len(rows) > query.limit
        selected = rows[: query.limit]
        return AuditPage(
            items=tuple(_from_row(row) for row in selected),
            next_cursor=(str(selected[-1].sequence) if has_more and selected else None),
        )

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity:
        scope_key = _scope_key(tenant_id)
        async with self._database.session() as session:
            head = await session.get(AuditChainHeadRow, scope_key)
            rows = list(
                await session.scalars(
                    select(AuditEventRow)
                    .where(AuditEventRow.scope_key == scope_key)
                    .order_by(AuditEventRow.sequence)
                )
            )
        previous_hash = _GENESIS_HASH
        broken_sequence: int | None = None
        for expected_sequence, row in enumerate(rows, start=1):
            actual = _from_row(row)
            rebuilt = build_audit_event(
                event_id=actual.event_id,
                scope_key=actual.scope_key,
                sequence=actual.sequence,
                previous_hash=actual.previous_hash,
                retention_until=actual.retention_until,
                entry=actual,
            )
            if (
                actual.sequence != expected_sequence
                or actual.previous_hash != previous_hash
                or actual.event_hash != rebuilt.event_hash
            ):
                broken_sequence = actual.sequence
                break
            previous_hash = actual.event_hash

        head_matches = head is not None and (
            head.event_count == len(rows) and head.last_hash == previous_hash
        )
        if not rows and head is None:
            head_matches = True
        verified = broken_sequence is None and head_matches
        if broken_sequence is None and not head_matches:
            broken_sequence = rows[-1].sequence if rows else 0
        return AuditIntegrity(
            scope_key=scope_key,
            event_count=len(rows),
            first_sequence=rows[0].sequence if rows else None,
            last_sequence=rows[-1].sequence if rows else None,
            last_hash=rows[-1].event_hash if rows else _GENESIS_HASH,
            verified=verified,
            broken_sequence=broken_sequence,
        )


def _scope_key(tenant_id: UUID | None) -> str:
    return f"tenant:{tenant_id}" if tenant_id is not None else "platform"


def _to_row(event: AuditEvent) -> AuditEventRow:
    return AuditEventRow(
        event_id=str(event.event_id),
        scope_key=event.scope_key,
        sequence=event.sequence,
        tenant_id=str(event.tenant_id) if event.tenant_id else None,
        actor_user_id=str(event.actor_user_id) if event.actor_user_id else None,
        action=event.action.value,
        outcome=event.outcome.value,
        request_id=str(event.request_id),
        trace_id=event.trace_id,
        resource_type=event.resource_type.value if event.resource_type else None,
        resource_id=event.resource_id,
        error_code=event.error_code,
        occurred_at=to_database_datetime(event.occurred_at),
        retention_until=to_database_datetime(event.retention_until),
        previous_hash=event.previous_hash,
        event_hash=event.event_hash,
    )


def _from_row(row: AuditEventRow) -> AuditEvent:
    return AuditEvent(
        tenant_id=UUID(row.tenant_id) if row.tenant_id else None,
        actor_user_id=UUID(row.actor_user_id) if row.actor_user_id else None,
        action=AuditAction(row.action),
        outcome=AuditOutcome(row.outcome),
        request_id=UUID(row.request_id),
        trace_id=row.trace_id,
        resource_type=AuditResourceType(row.resource_type) if row.resource_type else None,
        resource_id=row.resource_id,
        error_code=row.error_code,
        occurred_at=from_database_datetime(row.occurred_at),
        event_id=UUID(row.event_id),
        scope_key=row.scope_key,
        sequence=row.sequence,
        previous_hash=row.previous_hash,
        event_hash=row.event_hash,
        retention_until=from_database_datetime(row.retention_until),
    )


__all__ = ["SqlAlchemyAuditStore"]
