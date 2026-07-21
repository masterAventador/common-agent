from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.events import SqlAlchemyEventJournal
from common_agent.events import (
    EventAppendRequest,
    EventCapacityExceeded,
    EventStreamKind,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.settings import TEST_DATABASE_URL


def test_event_journal_is_idempotent_monotonic_and_survives_reconstruction() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        stream_id = uuid4()
        now = datetime.now(UTC)
        first_request = EventAppendRequest(
            event_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            stream_kind=EventStreamKind.CONVERSATION,
            stream_id=stream_id,
            event_key="assistant-message-1:started",
            event_type="assistant.started",
            payload={"turn_id": str(uuid4()), "message_id": str(uuid4())},
            occurred_at=now,
        )
        second_request = EventAppendRequest(
            event_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            stream_kind=EventStreamKind.CONVERSATION,
            stream_id=stream_id,
            event_key="assistant-message-1:completed",
            event_type="assistant.completed",
            payload={"turn_id": str(uuid4()), "message_id": str(uuid4())},
            occurred_at=now + timedelta(seconds=1),
        )
        try:
            first_store = SqlAlchemyEventJournal(database)
            first = await first_store.append(
                first_request,
                retention_until=now + timedelta(days=30),
                maximum_events_per_stream=10,
            )
            duplicate = await first_store.append(
                first_request,
                retention_until=now + timedelta(days=30),
                maximum_events_per_stream=10,
            )
            assert first.sequence == 1
            assert duplicate == first

            reconstructed = SqlAlchemyEventJournal(database)
            second = await reconstructed.append(
                second_request,
                retention_until=now + timedelta(days=30),
                maximum_events_per_stream=10,
            )
            assert second.sequence == 2
            assert await reconstructed.bounds(
                tenant_id=DEFAULT_TENANT_ID,
                stream_kind=EventStreamKind.CONVERSATION,
                stream_id=stream_id,
            ) == (1, 2)
            assert await reconstructed.read(
                tenant_id=DEFAULT_TENANT_ID,
                stream_kind=EventStreamKind.CONVERSATION,
                stream_id=stream_id,
                after_sequence=1,
                limit=10,
            ) == (second,)
        finally:
            await database.stop()

    asyncio.run(scenario())


def test_event_journal_serializes_concurrent_appends_and_enforces_capacity() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        stream_id = uuid4()
        now = datetime.now(UTC)

        def request(index: int) -> EventAppendRequest:
            return EventAppendRequest(
                event_id=uuid4(),
                tenant_id=DEFAULT_TENANT_ID,
                stream_kind=EventStreamKind.WORKFLOW,
                stream_id=stream_id,
                event_key=f"node:{index}",
                event_type="workflow.node.completed",
                payload={"node_id": f"node-{index}"},
                occurred_at=now + timedelta(microseconds=index),
            )

        try:
            journal_a = SqlAlchemyEventJournal(database)
            journal_b = SqlAlchemyEventJournal(database)
            events = await asyncio.gather(
                journal_a.append(
                    request(1),
                    retention_until=now + timedelta(days=30),
                    maximum_events_per_stream=2,
                ),
                journal_b.append(
                    request(2),
                    retention_until=now + timedelta(days=30),
                    maximum_events_per_stream=2,
                ),
            )
            assert sorted(event.sequence for event in events) == [1, 2]

            with pytest.raises(EventCapacityExceeded):
                await journal_a.append(
                    request(3),
                    retention_until=now + timedelta(days=30),
                    maximum_events_per_stream=2,
                )
        finally:
            await database.stop()

    asyncio.run(scenario())


def test_event_journal_hides_expired_history_and_releases_its_idempotency_key() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        journal = SqlAlchemyEventJournal(database)
        stream_id = uuid4()
        now = datetime.now(UTC)
        expired = EventAppendRequest(
            event_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            stream_kind=EventStreamKind.CONVERSATION,
            stream_id=stream_id,
            event_key="assistant-message:terminal",
            event_type="assistant.completed",
            payload={"version": 1},
            occurred_at=now - timedelta(days=2),
        )
        replacement = EventAppendRequest(
            event_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            stream_kind=EventStreamKind.CONVERSATION,
            stream_id=stream_id,
            event_key=expired.event_key,
            event_type=expired.event_type,
            payload={"version": 2},
            occurred_at=now,
        )
        try:
            await journal.append(
                expired,
                retention_until=now - timedelta(days=1),
                maximum_events_per_stream=10,
            )

            assert (
                await journal.read(
                    tenant_id=DEFAULT_TENANT_ID,
                    stream_kind=EventStreamKind.CONVERSATION,
                    stream_id=stream_id,
                    after_sequence=0,
                    limit=10,
                )
                == ()
            )
            assert (
                await journal.bounds(
                    tenant_id=DEFAULT_TENANT_ID,
                    stream_kind=EventStreamKind.CONVERSATION,
                    stream_id=stream_id,
                )
                is None
            )

            retained = await journal.append(
                replacement,
                retention_until=now + timedelta(days=30),
                maximum_events_per_stream=10,
            )
            assert retained.sequence == 2
        finally:
            await database.stop()

    asyncio.run(scenario())
