from __future__ import annotations

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest

from common_agent.conversations.events import (
    ConversationEventBroker,
    ConversationEventKind,
    EventHistoryUnavailable,
    EventStreamOverflow,
)
from common_agent.domain.conversation import Message


def test_event_broker_replays_monotonic_events_and_delivers_live_events() -> None:
    async def exercise() -> None:
        conversation_id = uuid4()
        turn_id = uuid4()
        pending = Message.create_assistant(
            conversation_id=conversation_id,
            sequence_number=2,
        )
        streaming = pending.append_delta(
            "第一段",
            updated_at=pending.updated_at + timedelta(microseconds=1),
        )
        completed = streaming.complete(
            updated_at=streaming.updated_at + timedelta(microseconds=1),
        )
        broker = ConversationEventBroker(history_limit=8, subscriber_queue_limit=8)

        started_event = await broker.publish(
            turn_id=turn_id,
            message=pending,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )
        delta_event = await broker.publish(
            turn_id=turn_id,
            message=streaming,
            kind=ConversationEventKind.ASSISTANT_DELTA,
            delta="第一段",
        )

        stream = broker.stream(conversation_id, after_sequence=0)
        assert await anext(stream) == started_event
        assert await anext(stream) == delta_event

        completed_event = await broker.publish(
            turn_id=turn_id,
            message=completed,
            kind=ConversationEventKind.ASSISTANT_COMPLETED,
        )
        assert await anext(stream) == completed_event
        await stream.aclose()

        assert [event.sequence for event in (started_event, delta_event, completed_event)] == [
            1,
            2,
            3,
        ]
        assert delta_event.delta == "第一段"
        assert completed_event.message == completed

    asyncio.run(exercise())


def test_event_broker_rejects_resume_before_retained_history() -> None:
    async def exercise() -> None:
        conversation_id = uuid4()
        turn_id = uuid4()
        pending = Message.create_assistant(
            conversation_id=conversation_id,
            sequence_number=2,
        )
        broker = ConversationEventBroker(history_limit=2, subscriber_queue_limit=2)

        for _ in range(3):
            await broker.publish(
                turn_id=turn_id,
                message=pending,
                kind=ConversationEventKind.ASSISTANT_STARTED,
            )

        stream = broker.stream(conversation_id, after_sequence=0)
        with pytest.raises(EventHistoryUnavailable):
            await anext(stream)

    asyncio.run(exercise())


def test_event_broker_closes_a_slow_subscriber_instead_of_dropping_events() -> None:
    async def exercise() -> None:
        conversation_id = uuid4()
        turn_id = uuid4()
        pending = Message.create_assistant(
            conversation_id=conversation_id,
            sequence_number=2,
        )
        broker = ConversationEventBroker(history_limit=8, subscriber_queue_limit=1)
        stream = broker.stream(conversation_id)
        waiting = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        first = await broker.publish(
            turn_id=turn_id,
            message=pending,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )
        assert await waiting == first

        await broker.publish(
            turn_id=turn_id,
            message=pending,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )
        await broker.publish(
            turn_id=turn_id,
            message=pending,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )
        with pytest.raises(EventStreamOverflow):
            await anext(stream)

    asyncio.run(exercise())
