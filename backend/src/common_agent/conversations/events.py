from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
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


class EventSubscriberLimitExceeded(EventStreamOverflow):
    def __init__(self) -> None:
        super().__init__()
        self.args = ("会话事件订阅者已达到容量上限,请稍后重连",)


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


@dataclass(frozen=True, slots=True)
class ConversationEventLifecycleSnapshot:
    state_count: int
    active_state_count: int
    subscriber_count: int
    retained_event_count: int


@dataclass(slots=True)
class _ConversationState:
    next_sequence: int = 1
    history: deque[ConversationEvent] = field(default_factory=deque)
    subscribers: set[asyncio.Queue[ConversationEvent | object]] = field(default_factory=set)
    active: bool = False
    last_accessed: float = field(default_factory=monotonic)
    cleanup_handle: asyncio.TimerHandle | None = field(default=None, repr=False)


_OVERFLOW = object()


class ConversationEventBroker:
    def __init__(
        self,
        *,
        history_limit: int = 512,
        subscriber_queue_limit: int = 128,
        subscriber_limit: int = 64,
        total_subscriber_limit: int = 1024,
        state_limit: int = 1024,
        state_ttl_seconds: float = 300,
        key_namespace: Callable[[UUID], str] | None = None,
    ) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        if subscriber_queue_limit < 1:
            raise ValueError("subscriber_queue_limit must be positive")
        if subscriber_limit < 1:
            raise ValueError("subscriber_limit must be positive")
        if total_subscriber_limit < 1:
            raise ValueError("total_subscriber_limit must be positive")
        if state_limit < 1:
            raise ValueError("state_limit must be positive")
        if state_ttl_seconds <= 0 or state_ttl_seconds > 86_400:
            raise ValueError("state_ttl_seconds must be between 0 and 86400")
        self._history_limit = history_limit
        self._subscriber_queue_limit = subscriber_queue_limit
        self._subscriber_limit = subscriber_limit
        self._total_subscriber_limit = total_subscriber_limit
        self._state_limit = state_limit
        self._state_ttl_seconds = state_ttl_seconds
        self._key_namespace = key_namespace or (lambda conversation_id: str(conversation_id))
        self._states: dict[str, _ConversationState] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def validate_resume(self, conversation_id: UUID, *, after_sequence: int = 0) -> None:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        async with self._lock:
            self._ensure_open()
            key = self._key_namespace(conversation_id)
            state, created = self._state_locked(key)
            try:
                _validate_resume_position(state, after_sequence)
            except EventHistoryUnavailable:
                if created:
                    self._drop_state_locked(key, state)
                raise
            self._touch_locked(key, state)

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
            self._ensure_open()
            key = self._key_namespace(message.conversation_id)
            state, _ = self._state_locked(key)
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
            if kind is ConversationEventKind.ASSISTANT_STARTED:
                state.active = True
            elif kind in {
                ConversationEventKind.ASSISTANT_COMPLETED,
                ConversationEventKind.ASSISTANT_FAILED,
                ConversationEventKind.ASSISTANT_STOPPED,
            }:
                state.active = False
            state.last_accessed = monotonic()

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
            self._trim_lru_locked()
            self._schedule_cleanup_locked(key, state)
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
            self._ensure_open()
            key = self._key_namespace(conversation_id)
            state, created = self._state_locked(key)
            try:
                _validate_resume_position(state, after_sequence)
            except EventHistoryUnavailable:
                if created:
                    self._drop_state_locked(key, state)
                raise
            if len(state.subscribers) >= self._subscriber_limit:
                if created:
                    self._drop_state_locked(key, state)
                raise EventSubscriberLimitExceeded
            if self._subscriber_count_locked() >= self._total_subscriber_limit:
                if created:
                    self._drop_state_locked(key, state)
                raise EventSubscriberLimitExceeded
            replay = tuple(event for event in state.history if event.sequence > after_sequence)
            state.subscribers.add(queue)
            state.last_accessed = monotonic()
            self._cancel_cleanup_locked(state)

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
                current_state = self._states.get(key)
                if current_state is not None:
                    current_state.subscribers.discard(queue)
                    current_state.last_accessed = monotonic()
                    self._schedule_cleanup_locked(key, current_state)

    async def lifecycle_snapshot(self) -> ConversationEventLifecycleSnapshot:
        async with self._lock:
            self._prune_expired_locked()
            return ConversationEventLifecycleSnapshot(
                state_count=len(self._states),
                active_state_count=sum(state.active for state in self._states.values()),
                subscriber_count=sum(len(state.subscribers) for state in self._states.values()),
                retained_event_count=sum(len(state.history) for state in self._states.values()),
            )

    async def aclose(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            for state in self._states.values():
                self._cancel_cleanup_locked(state)
                for subscriber in state.subscribers:
                    while not subscriber.empty():
                        subscriber.get_nowait()
                    subscriber.put_nowait(_OVERFLOW)
            self._states.clear()

    def _state_locked(self, key: str) -> tuple[_ConversationState, bool]:
        now = monotonic()
        self._prune_expired_locked(now)
        state = self._states.get(key)
        if state is not None:
            state.last_accessed = now
            return state, False

        self._evict_lru_locked()
        state = _ConversationState(last_accessed=now)
        self._states[key] = state
        return state, True

    def _touch_locked(self, key: str, state: _ConversationState) -> None:
        state.last_accessed = monotonic()
        self._schedule_cleanup_locked(key, state)

    def _evict_lru_locked(self) -> None:
        while len(self._states) >= self._state_limit:
            candidates = (
                (key, state)
                for key, state in self._states.items()
                if not state.active and not state.subscribers
            )
            victim = min(candidates, key=lambda item: item[1].last_accessed, default=None)
            if victim is None:
                return
            self._drop_state_locked(*victim)

    def _trim_lru_locked(self) -> None:
        while len(self._states) > self._state_limit:
            candidates = (
                (key, state)
                for key, state in self._states.items()
                if not state.active and not state.subscribers
            )
            victim = min(candidates, key=lambda item: item[1].last_accessed, default=None)
            if victim is None:
                return
            self._drop_state_locked(*victim)

    def _subscriber_count_locked(self) -> int:
        return sum(len(state.subscribers) for state in self._states.values())

    def _prune_expired_locked(self, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        expired = tuple(
            (key, state)
            for key, state in self._states.items()
            if not state.active
            and not state.subscribers
            and current - state.last_accessed >= self._state_ttl_seconds
        )
        for key, state in expired:
            self._drop_state_locked(key, state)

    def _schedule_cleanup_locked(
        self,
        key: str,
        state: _ConversationState,
    ) -> None:
        self._cancel_cleanup_locked(state)
        if state.active or state.subscribers or self._closed:
            return
        marker = state.last_accessed
        state.cleanup_handle = asyncio.get_running_loop().call_later(
            self._state_ttl_seconds,
            self._start_expiry,
            key,
            marker,
        )

    def _start_expiry(self, key: str, marker: float) -> None:
        if self._closed:
            return
        asyncio.get_running_loop().create_task(
            self._expire_state(key, marker),
            name=f"conversation-event-expiry-{key}",
        )

    async def _expire_state(self, key: str, marker: float) -> None:
        async with self._lock:
            state = self._states.get(key)
            if state is None or state.last_accessed != marker:
                return
            state.cleanup_handle = None
            self._prune_expired_locked()
            current = self._states.get(key)
            if current is state:
                self._schedule_cleanup_locked(key, state)

    def _drop_state_locked(
        self,
        key: str,
        state: _ConversationState,
    ) -> None:
        if self._states.get(key) is not state:
            return
        self._cancel_cleanup_locked(state)
        self._states.pop(key, None)

    @staticmethod
    def _cancel_cleanup_locked(state: _ConversationState) -> None:
        handle = state.cleanup_handle
        state.cleanup_handle = None
        if handle is not None:
            handle.cancel()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("conversation event broker is closed")


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
