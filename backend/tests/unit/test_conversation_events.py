from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest

from common_agent.conversations.events import (
    ConversationEventBroker,
    ConversationEventKind,
    EventHistoryUnavailable,
    EventStreamOverflow,
    EventSubscriberLimitExceeded,
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


def test_event_broker_bounds_terminal_states_and_preserves_active_state() -> None:
    async def exercise() -> None:
        broker = ConversationEventBroker(
            history_limit=4,
            state_limit=16,
            state_ttl_seconds=60,
        )
        active_id = uuid4()
        active = Message.create_assistant(conversation_id=active_id, sequence_number=2)
        active_event = await broker.publish(
            turn_id=uuid4(),
            message=active,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )

        for _ in range(500):
            conversation_id = uuid4()
            turn_id = uuid4()
            pending = Message.create_assistant(
                conversation_id=conversation_id,
                sequence_number=2,
            )
            streaming = pending.append_delta("x")
            completed = streaming.complete()
            await broker.publish(
                turn_id=turn_id,
                message=pending,
                kind=ConversationEventKind.ASSISTANT_STARTED,
            )
            await broker.publish(
                turn_id=turn_id,
                message=streaming,
                kind=ConversationEventKind.ASSISTANT_DELTA,
                delta="x",
            )
            await broker.publish(
                turn_id=turn_id,
                message=completed,
                kind=ConversationEventKind.ASSISTANT_COMPLETED,
            )

        snapshot = await broker.lifecycle_snapshot()
        active_stream = broker.stream(active_id)
        assert await anext(active_stream) == active_event
        await active_stream.aclose()
        await broker.aclose()

        assert snapshot.state_count <= 16
        assert snapshot.active_state_count == 1
        assert snapshot.subscriber_count == 0
        assert snapshot.retained_event_count <= 16 * 4

    asyncio.run(exercise())


def test_event_broker_expires_terminal_state_but_not_live_subscriber() -> None:
    async def exercise() -> None:
        broker = ConversationEventBroker(
            history_limit=4,
            state_limit=8,
            state_ttl_seconds=0.02,
            subscriber_limit=1,
        )
        conversation_id = uuid4()
        turn_id = uuid4()
        pending = Message.create_assistant(
            conversation_id=conversation_id,
            sequence_number=2,
        )
        streaming = pending.append_delta("x")
        completed = streaming.complete()
        await broker.publish(
            turn_id=turn_id,
            message=pending,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )
        await broker.publish(
            turn_id=turn_id,
            message=streaming,
            kind=ConversationEventKind.ASSISTANT_DELTA,
            delta="x",
        )
        terminal = await broker.publish(
            turn_id=turn_id,
            message=completed,
            kind=ConversationEventKind.ASSISTANT_COMPLETED,
        )

        stream = broker.stream(conversation_id, after_sequence=terminal.sequence - 1)
        assert await anext(stream) == terminal
        await asyncio.sleep(0.04)
        retained = await broker.lifecycle_snapshot()
        assert retained.state_count == 1
        assert retained.subscriber_count == 1

        second = broker.stream(conversation_id)
        with pytest.raises(EventSubscriberLimitExceeded, match="订阅者"):
            await anext(second)
        await second.aclose()
        await stream.aclose()
        await asyncio.sleep(0.04)

        expired = await broker.lifecycle_snapshot()
        assert expired.state_count == 0
        with pytest.raises(EventHistoryUnavailable):
            await broker.validate_resume(
                conversation_id,
                after_sequence=terminal.sequence,
            )
        await broker.aclose()

    asyncio.run(exercise())


def test_event_broker_globally_bounds_subscribers_across_conversations() -> None:
    async def exercise() -> None:
        broker = ConversationEventBroker(
            state_limit=1,
            subscriber_limit=4,
            total_subscriber_limit=1,
        )
        first_id = uuid4()
        first_stream = broker.stream(first_id)
        first_waiter = asyncio.create_task(anext(first_stream))
        await asyncio.sleep(0)

        second_stream = broker.stream(uuid4())
        with pytest.raises(EventSubscriberLimitExceeded, match="订阅者"):
            await anext(second_stream)
        await second_stream.aclose()

        pending = Message.create_assistant(
            conversation_id=first_id,
            sequence_number=2,
        )
        event = await broker.publish(
            turn_id=uuid4(),
            message=pending,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )
        assert await first_waiter == event
        await first_stream.aclose()
        assert (await broker.lifecycle_snapshot()).subscriber_count == 0
        await broker.aclose()

    asyncio.run(exercise())


def test_event_broker_trims_completed_overflow_without_evicting_active_states() -> None:
    async def exercise() -> None:
        broker = ConversationEventBroker(state_limit=2, state_ttl_seconds=60)
        active_messages = [
            Message.create_assistant(conversation_id=uuid4(), sequence_number=2) for _ in range(4)
        ]
        for pending in active_messages:
            await broker.publish(
                turn_id=uuid4(),
                message=pending,
                kind=ConversationEventKind.ASSISTANT_STARTED,
            )
        assert (await broker.lifecycle_snapshot()).active_state_count == 4

        await broker.publish(
            turn_id=uuid4(),
            message=active_messages[0].append_delta("done").complete(),
            kind=ConversationEventKind.ASSISTANT_COMPLETED,
        )
        snapshot = await broker.lifecycle_snapshot()
        assert snapshot.state_count == 3
        assert snapshot.active_state_count == 3

        for pending in active_messages[1:]:
            stream = broker.stream(pending.conversation_id)
            assert (await anext(stream)).message.conversation_id == pending.conversation_id
            await stream.aclose()
        await broker.aclose()

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "arguments",
    [
        {"history_limit": 0},
        {"subscriber_queue_limit": 0},
        {"subscriber_limit": 0},
        {"total_subscriber_limit": 0},
        {"state_limit": 0},
        {"state_ttl_seconds": 0},
        {"state_ttl_seconds": 86_401},
    ],
)
def test_event_broker_rejects_invalid_lifecycle_limits(arguments: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        ConversationEventBroker(**arguments)
