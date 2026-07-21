from __future__ import annotations

from datetime import datetime
from typing import Protocol
from uuid import UUID

from common_agent.events.models import (
    DurableEvent,
    EventAppendRequest,
    EventStreamKind,
)


class EventJournal(Protocol):
    async def append(
        self,
        request: EventAppendRequest,
        *,
        retention_until: datetime,
        maximum_events_per_stream: int,
    ) -> DurableEvent: ...

    async def read(
        self,
        *,
        tenant_id: UUID,
        stream_kind: EventStreamKind,
        stream_id: UUID,
        after_sequence: int,
        limit: int,
    ) -> tuple[DurableEvent, ...]: ...

    async def bounds(
        self,
        *,
        tenant_id: UUID,
        stream_kind: EventStreamKind,
        stream_id: UUID,
    ) -> tuple[int, int] | None: ...


__all__ = ["EventJournal"]
