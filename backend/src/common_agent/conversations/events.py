from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from common_agent.domain.conversation import Message, MessageStatus


class ConversationEventKind(StrEnum):
    ASSISTANT_STARTED = "assistant.started"
    ASSISTANT_DELTA = "assistant.delta"
    ASSISTANT_COMPLETED = "assistant.completed"
    ASSISTANT_FAILED = "assistant.failed"
    ASSISTANT_STOPPED = "assistant.stopped"


class EventHistoryUnavailable(Exception):
    code = "event_history_unavailable"
    retryable = False

    def __init__(self) -> None:
        super().__init__("事件历史已不可续传,请重新加载会话消息")


class EventStreamOverflow(Exception):
    code = "event_stream_overflow"
    retryable = True

    def __init__(self) -> None:
        super().__init__("事件消费者处理速度过慢,请重新连接")


@dataclass(frozen=True, slots=True)
class ConversationEvent:
    sequence: int
    turn_id: UUID
    message: Message
    kind: ConversationEventKind
    delta: str | None = field(default=None, repr=False)
    retry: bool = False
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def conversation_id(self) -> UUID:
        return self.message.conversation_id

    @property
    def message_id(self) -> UUID:
        return self.message.id


@dataclass(slots=True)
class _ConversationState:
    next_sequence: int = 1
    history: deque[ConversationEvent] = field(default_factory=deque)
    subscribers: set[asyncio.Queue[ConversationEvent | object]] = field(default_factory=set)


_OVERFLOW = object()


class ConversationEventBroker:
    def __init__(self, *, history_limit: int = 512, subscriber_queue_limit: int = 128) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        if subscriber_queue_limit < 1:
            raise ValueError("subscriber_queue_limit must be positive")
        self._history_limit = history_limit
        self._subscriber_queue_limit = subscriber_queue_limit
        self._states: dict[UUID, _ConversationState] = {}
        self._lock = asyncio.Lock()

    async def validate_resume(self, conversation_id: UUID, *, after_sequence: int = 0) -> None:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        async with self._lock:
            state = self._states.setdefault(conversation_id, _ConversationState())
            _validate_resume_position(state, after_sequence)

    async def publish(
        self,
        *,
        turn_id: UUID,
        message: Message,
        kind: ConversationEventKind,
        delta: str | None = None,
        retry: bool = False,
    ) -> ConversationEvent:
        _validate_event(message=message, kind=kind, delta=delta, retry=retry)
        async with self._lock:
            state = self._states.setdefault(message.conversation_id, _ConversationState())
            event = ConversationEvent(
                sequence=state.next_sequence,
                turn_id=turn_id,
                message=message,
                kind=kind,
                delta=delta,
                retry=retry,
            )
            state.next_sequence += 1
            state.history.append(event)
            while len(state.history) > self._history_limit:
                state.history.popleft()

            overflowed: list[asyncio.Queue[ConversationEvent | object]] = []
            for subscriber in state.subscribers:
                try:
                    subscriber.put_nowait(event)
                except asyncio.QueueFull:
                    overflowed.append(subscriber)
            for subscriber in overflowed:
                state.subscribers.discard(subscriber)
                while not subscriber.empty():
                    subscriber.get_nowait()
                subscriber.put_nowait(_OVERFLOW)
            return event

    async def stream(
        self,
        conversation_id: UUID,
        *,
        after_sequence: int = 0,
    ) -> AsyncGenerator[ConversationEvent, None]:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        queue: asyncio.Queue[ConversationEvent | object] = asyncio.Queue(
            maxsize=self._subscriber_queue_limit
        )
        async with self._lock:
            state = self._states.setdefault(conversation_id, _ConversationState())
            _validate_resume_position(state, after_sequence)
            replay = tuple(event for event in state.history if event.sequence > after_sequence)
            state.subscribers.add(queue)

        try:
            for event in replay:
                yield event
            while True:
                queued = await queue.get()
                if queued is _OVERFLOW:
                    raise EventStreamOverflow
                if not isinstance(queued, ConversationEvent):
                    raise RuntimeError("unexpected conversation event")
                yield queued
        finally:
            async with self._lock:
                current_state = self._states.get(conversation_id)
                if current_state is not None:
                    current_state.subscribers.discard(queue)


def _validate_event(
    *,
    message: Message,
    kind: ConversationEventKind,
    delta: str | None,
    retry: bool,
) -> None:
    expected_status = {
        ConversationEventKind.ASSISTANT_STARTED: MessageStatus.PENDING,
        ConversationEventKind.ASSISTANT_DELTA: MessageStatus.STREAMING,
        ConversationEventKind.ASSISTANT_COMPLETED: MessageStatus.COMPLETED,
        ConversationEventKind.ASSISTANT_FAILED: MessageStatus.FAILED,
        ConversationEventKind.ASSISTANT_STOPPED: MessageStatus.STOPPED,
    }[kind]
    if message.status is not expected_status:
        raise ValueError("event kind does not match persisted message status")
    if kind is ConversationEventKind.ASSISTANT_DELTA:
        if delta is None or not delta:
            raise ValueError("delta event requires content")
    elif delta is not None:
        raise ValueError("only delta events may contain delta content")
    if retry and kind is not ConversationEventKind.ASSISTANT_STARTED:
        raise ValueError("only started events may be marked as retry")


def _validate_resume_position(state: _ConversationState, after_sequence: int) -> None:
    latest = state.next_sequence - 1
    earliest = state.history[0].sequence if state.history else latest + 1
    if after_sequence > latest or (state.history and after_sequence < earliest - 1):
        raise EventHistoryUnavailable
