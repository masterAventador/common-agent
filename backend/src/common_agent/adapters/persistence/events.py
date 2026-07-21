from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select
from sqlalchemy.sql.elements import ColumnElement

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import DurableEventRow, DurableEventStreamRow
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.events import (
    DurableEvent,
    EventAppendRequest,
    EventCapacityExceeded,
    EventIdempotencyConflict,
    EventStreamKind,
)


class SqlAlchemyEventJournal:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def append(
        self,
        request: EventAppendRequest,
        *,
        retention_until: datetime,
        maximum_events_per_stream: int,
    ) -> DurableEvent:
        if not 1 <= maximum_events_per_stream <= 1_000_000:
            raise ValueError("maximum_events_per_stream must be between 1 and 1000000")
        durable = DurableEvent(
            request=request,
            sequence=1,
            retention_until=retention_until,
        )
        database_now = to_database_datetime(request.occurred_at)
        cleanup_now = to_database_datetime(datetime.now(UTC))
        scope = _scope(request.tenant_id, request.stream_kind, request.stream_id)
        async with self._database.session() as session:
            await session.execute(
                insert(DurableEventStreamRow)
                .prefix_with("IGNORE")
                .values(
                    **scope,
                    next_sequence=1,
                    event_count=0,
                    created_at=database_now,
                    updated_at=database_now,
                )
            )
            stream = await session.scalar(
                select(DurableEventStreamRow).where(*_scope_filters(scope)).with_for_update()
            )
            if stream is None:
                raise RuntimeError("event stream creation failed")

            await session.execute(
                delete(DurableEventRow).where(
                    *_event_scope_filters(scope),
                    DurableEventRow.retention_until <= cleanup_now,
                )
            )
            existing = await session.scalar(
                select(DurableEventRow).where(
                    *_event_scope_filters(scope),
                    DurableEventRow.event_key == request.event_key,
                )
            )
            if existing is not None:
                result = _from_row(existing)
                if not _same_event_identity(result.request, request):
                    raise EventIdempotencyConflict(request.event_key)
                await session.commit()
                return result

            remaining = await session.scalar(
                select(func.count())
                .select_from(DurableEventRow)
                .where(*_event_scope_filters(scope))
            )
            stream.event_count = int(remaining or 0)
            if stream.event_count >= maximum_events_per_stream:
                raise EventCapacityExceeded(request.event_key)

            event = DurableEventRow(
                event_id=str(request.event_id),
                **scope,
                sequence=stream.next_sequence,
                event_key=request.event_key,
                event_type=request.event_type,
                payload=request.payload,
                occurred_at=database_now,
                retention_until=to_database_datetime(durable.retention_until),
            )
            session.add(event)
            stream.next_sequence += 1
            stream.event_count += 1
            stream.updated_at = database_now
            await session.commit()
            return _from_row(event)

    async def read(
        self,
        *,
        tenant_id: UUID,
        stream_kind: EventStreamKind,
        stream_id: UUID,
        after_sequence: int,
        limit: int,
    ) -> tuple[DurableEvent, ...]:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")
        scope = _scope(tenant_id, stream_kind, stream_id)
        async with self._database.session() as session:
            rows = await session.scalars(
                select(DurableEventRow)
                .where(
                    *_event_scope_filters(scope),
                    DurableEventRow.sequence > after_sequence,
                    DurableEventRow.retention_until > to_database_datetime(datetime.now(UTC)),
                )
                .order_by(DurableEventRow.sequence)
                .limit(limit)
            )
            return tuple(_from_row(row) for row in rows)

    async def bounds(
        self,
        *,
        tenant_id: UUID,
        stream_kind: EventStreamKind,
        stream_id: UUID,
    ) -> tuple[int, int] | None:
        scope = _scope(tenant_id, stream_kind, stream_id)
        async with self._database.session() as session:
            result = await session.execute(
                select(
                    func.min(DurableEventRow.sequence),
                    func.max(DurableEventRow.sequence),
                ).where(
                    *_event_scope_filters(scope),
                    DurableEventRow.retention_until > to_database_datetime(datetime.now(UTC)),
                )
            )
            earliest, latest = result.one()
        if earliest is None or latest is None:
            return None
        return int(earliest), int(latest)


def _scope(
    tenant_id: UUID,
    stream_kind: EventStreamKind,
    stream_id: UUID,
) -> dict[str, str]:
    return {
        "tenant_id": str(tenant_id),
        "stream_kind": stream_kind.value,
        "stream_id": str(stream_id),
    }


def _scope_filters(scope: dict[str, str]) -> tuple[ColumnElement[bool], ...]:
    return (
        DurableEventStreamRow.tenant_id == scope["tenant_id"],
        DurableEventStreamRow.stream_kind == scope["stream_kind"],
        DurableEventStreamRow.stream_id == scope["stream_id"],
    )


def _event_scope_filters(scope: dict[str, str]) -> tuple[ColumnElement[bool], ...]:
    return (
        DurableEventRow.tenant_id == scope["tenant_id"],
        DurableEventRow.stream_kind == scope["stream_kind"],
        DurableEventRow.stream_id == scope["stream_id"],
    )


def _from_row(row: DurableEventRow) -> DurableEvent:
    return DurableEvent(
        request=EventAppendRequest(
            event_id=UUID(row.event_id),
            tenant_id=UUID(row.tenant_id),
            stream_kind=EventStreamKind(row.stream_kind),
            stream_id=UUID(row.stream_id),
            event_key=row.event_key,
            event_type=row.event_type,
            payload=row.payload,
            occurred_at=from_database_datetime(row.occurred_at),
        ),
        sequence=row.sequence,
        retention_until=from_database_datetime(row.retention_until),
    )


def _same_event_identity(left: EventAppendRequest, right: EventAppendRequest) -> bool:
    return (
        left.event_id == right.event_id
        and left.tenant_id == right.tenant_id
        and left.stream_kind is right.stream_kind
        and left.stream_id == right.stream_id
        and left.event_key == right.event_key
        and left.event_type == right.event_type
        and left.payload == right.payload
    )


__all__ = ["SqlAlchemyEventJournal"]
