from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from common_agent.conversations.events import (
    ConversationEventBroker,
    ConversationEventKind,
)
from common_agent.domain.conversation import Message
from common_agent.runtimes.base import RuntimeEventEmitter, RuntimeEventKind


def test_emitter_produces_a_reasoning_event_with_text() -> None:
    """思考增量是独立事件类型, 不复用正文增量。"""
    emitter = RuntimeEventEmitter(uuid4())

    event = emitter.reasoning("先比较大小")

    assert event.kind is RuntimeEventKind.REASONING
    assert event.delta == "先比较大小"
    assert event.error_code is None
    assert event.tool_call_id is None


def test_emitter_keeps_one_sequence_across_reasoning_and_delta() -> None:
    """思考和正文共用同一条序号轴, 否则会话侧的连续性校验会判定乱序。"""
    emitter = RuntimeEventEmitter(uuid4())

    sequences = [
        emitter.reasoning("想").sequence,
        emitter.delta("答").sequence,
        emitter.reasoning("再想").sequence,
        emitter.complete().sequence,
    ]

    assert sequences == [1, 2, 3, 4]


def test_reasoning_event_rejects_blank_text() -> None:
    emitter = RuntimeEventEmitter(uuid4())

    with pytest.raises(ValueError):
        emitter.reasoning("")


def test_broker_publishes_reasoning_while_the_message_is_still_active() -> None:
    async def exercise() -> None:
        conversation_id = uuid4()
        turn_id = uuid4()
        pending = Message.create_assistant(conversation_id=conversation_id, sequence_number=2)
        broker = ConversationEventBroker(history_limit=8, subscriber_queue_limit=8)

        await broker.publish(
            turn_id=turn_id,
            message=pending,
            kind=ConversationEventKind.ASSISTANT_STARTED,
        )
        reasoning_event = await broker.publish(
            turn_id=turn_id,
            message=pending,
            kind=ConversationEventKind.ASSISTANT_REASONING,
            delta="先比较大小",
        )

        assert reasoning_event.kind is ConversationEventKind.ASSISTANT_REASONING
        assert reasoning_event.delta == "先比较大小"
        # 思考不改消息正文, 回复内容仍然为空
        assert reasoning_event.message.content == ""

        stream = broker.stream(conversation_id, after_sequence=0)
        replayed = [await anext(stream), await anext(stream)]
        await stream.aclose()
        assert [event.kind for event in replayed] == [
            ConversationEventKind.ASSISTANT_STARTED,
            ConversationEventKind.ASSISTANT_REASONING,
        ]
        assert replayed[1].delta == "先比较大小"

    asyncio.run(exercise())


def test_reasoning_event_requires_content() -> None:
    async def exercise() -> None:
        pending = Message.create_assistant(conversation_id=uuid4(), sequence_number=2)
        broker = ConversationEventBroker(history_limit=4, subscriber_queue_limit=4)

        with pytest.raises(ValueError):
            await broker.publish(
                turn_id=uuid4(),
                message=pending,
                kind=ConversationEventKind.ASSISTANT_REASONING,
                delta=None,
            )

    asyncio.run(exercise())
