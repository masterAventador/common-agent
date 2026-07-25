from __future__ import annotations

import asyncio
import hashlib
import json
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from time import monotonic
from typing import cast
from uuid import NAMESPACE_URL, UUID, uuid5

from common_agent.domain.conversation import Citation, Message, MessageRole, MessageStatus
from common_agent.events import EventAppendRequest, EventJournal, EventStreamKind


class ConversationEventKind(StrEnum):
    ASSISTANT_STARTED = "assistant.started"
    ASSISTANT_DELTA = "assistant.delta"
    ASSISTANT_REASONING = "assistant.reasoning"
    ASSISTANT_COMPLETED = "assistant.completed"
    ASSISTANT_FAILED = "assistant.failed"
    ASSISTANT_STOPPED = "assistant.stopped"
    ASSISTANT_TOOL_STARTED = "assistant.tool.started"
    ASSISTANT_TOOL_COMPLETED = "assistant.tool.completed"
    ASSISTANT_TOOL_FAILED = "assistant.tool.failed"


@dataclass(frozen=True, slots=True)
class ToolCallEvent:
    tool_call_id: UUID
    capability_id: UUID
    capability_name: str
    error_code: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_call_id, UUID):
            raise ValueError("tool_call_id must be UUID")
        if not isinstance(self.capability_id, UUID):
            raise ValueError("capability_id must be UUID")
        if (
            not isinstance(self.capability_name, str)
            or not self.capability_name
            or self.capability_name != self.capability_name.strip()
            or len(self.capability_name) > 128
            or any(character in self.capability_name for character in "\r\n\0")
        ):
            raise ValueError("capability_name must be safe non-empty text")
        if self.error_code is not None and (
            not isinstance(self.error_code, str)
            or not self.error_code
            or self.error_code != self.error_code.strip()
            or len(self.error_code) > 128
            or any(character in self.error_code for character in "\r\n\0")
        ):
            raise ValueError("error_code must be safe non-empty text")


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
    tool_call: ToolCallEvent | None = None
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


@dataclass(frozen=True, slots=True)
class ToolCallRecoveryState:
    attempted: bool
    unresolved: tuple[ToolCallEvent, ...] = ()


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
        journal: EventJournal | None = None,
        tenant_id_provider: Callable[[], UUID] | None = None,
        persistent_poll_seconds: float = 0.1,
        retention_days: int = 30,
        maximum_events_per_stream: int = 100_000,
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
        if (journal is None) != (tenant_id_provider is None):
            raise ValueError("journal and tenant_id_provider must be configured together")
        if not 0 < persistent_poll_seconds <= 10:
            raise ValueError("persistent_poll_seconds must be between 0 and 10")
        if not 1 <= retention_days <= 3650:
            raise ValueError("retention_days must be between 1 and 3650")
        if not 100 <= maximum_events_per_stream <= 1_000_000:
            raise ValueError("maximum_events_per_stream must be between 100 and 1000000")
        self._history_limit = history_limit
        self._subscriber_queue_limit = subscriber_queue_limit
        self._subscriber_limit = subscriber_limit
        self._total_subscriber_limit = total_subscriber_limit
        self._state_limit = state_limit
        self._state_ttl_seconds = state_ttl_seconds
        self._key_namespace = key_namespace or (lambda conversation_id: str(conversation_id))
        self._journal = journal
        self._tenant_id_provider = tenant_id_provider
        self._persistent_poll_seconds = persistent_poll_seconds
        self._retention_days = retention_days
        self._maximum_events_per_stream = maximum_events_per_stream
        self._persistent_subscribers = 0
        self._states: dict[str, _ConversationState] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def validate_resume(self, conversation_id: UUID, *, after_sequence: int = 0) -> None:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        if self._journal is not None:
            self._ensure_open()
            await self._validate_persistent_resume(conversation_id, after_sequence)
            return
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
        tool_call: ToolCallEvent | None = None,
    ) -> ConversationEvent:
        _validate_event(
            message=message,
            kind=kind,
            delta=delta,
            retry=retry,
            tool_call=tool_call,
        )
        if self._journal is not None:
            self._ensure_open()
            return await self._publish_persistent(
                turn_id=turn_id,
                message=message,
                kind=kind,
                delta=delta,
                retry=retry,
                tool_call=tool_call,
            )
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
                tool_call=tool_call,
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
        if self._journal is not None:
            async for event in self._stream_persistent(
                conversation_id,
                after_sequence=after_sequence,
            ):
                yield event
            return
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

    async def tool_call_recovery_state(
        self,
        conversation_id: UUID,
        message_id: UUID,
    ) -> ToolCallRecoveryState:
        """Return durable tool-attempt evidence used to prevent side-effect replay."""
        if self._journal is not None:
            self._ensure_open()
            events = await self._persistent_events(conversation_id)
        else:
            async with self._lock:
                self._ensure_open()
                state = self._states.get(self._key_namespace(conversation_id))
                events = () if state is None else tuple(state.history)
        active: dict[UUID, ToolCallEvent] = {}
        attempted = False
        for event in events:
            if event.message_id != message_id or event.tool_call is None:
                continue
            if event.kind is ConversationEventKind.ASSISTANT_TOOL_STARTED:
                attempted = True
                active[event.tool_call.tool_call_id] = event.tool_call
            elif event.kind in {
                ConversationEventKind.ASSISTANT_TOOL_COMPLETED,
                ConversationEventKind.ASSISTANT_TOOL_FAILED,
            }:
                active.pop(event.tool_call.tool_call_id, None)
        return ToolCallRecoveryState(
            attempted=attempted,
            unresolved=tuple(active.values()),
        )

    async def _publish_persistent(
        self,
        *,
        turn_id: UUID,
        message: Message,
        kind: ConversationEventKind,
        delta: str | None,
        retry: bool,
        tool_call: ToolCallEvent | None,
    ) -> ConversationEvent:
        journal = self._persistent_journal
        tenant_id = self._persistent_tenant_id
        occurred_at = datetime.now(UTC)
        payload = _conversation_payload(
            turn_id=turn_id,
            message=message,
            delta=delta,
            retry=retry,
            tool_call=tool_call,
        )
        event_key = _durable_event_key(message.id, kind.value, payload)
        durable = await journal.append(
            EventAppendRequest(
                event_id=uuid5(
                    NAMESPACE_URL,
                    f"common-agent:{tenant_id}:conversation:{message.conversation_id}:{event_key}",
                ),
                tenant_id=tenant_id,
                stream_kind=EventStreamKind.CONVERSATION,
                stream_id=message.conversation_id,
                event_key=event_key,
                event_type=kind.value,
                payload=payload,
                occurred_at=occurred_at,
            ),
            retention_until=occurred_at + timedelta(days=self._retention_days),
            maximum_events_per_stream=self._maximum_events_per_stream,
        )
        return _conversation_event(durable.sequence, durable.request)

    async def _validate_persistent_resume(
        self,
        conversation_id: UUID,
        after_sequence: int,
    ) -> None:
        bounds = await self._persistent_journal.bounds(
            tenant_id=self._persistent_tenant_id,
            stream_kind=EventStreamKind.CONVERSATION,
            stream_id=conversation_id,
        )
        if bounds is None:
            if after_sequence != 0:
                raise EventHistoryUnavailable
            return
        earliest, latest = bounds
        if after_sequence > latest or after_sequence < earliest - 1:
            raise EventHistoryUnavailable

    async def _persistent_events(
        self,
        conversation_id: UUID,
    ) -> tuple[ConversationEvent, ...]:
        bounds = await self._persistent_journal.bounds(
            tenant_id=self._persistent_tenant_id,
            stream_kind=EventStreamKind.CONVERSATION,
            stream_id=conversation_id,
        )
        if bounds is None:
            return ()
        earliest, latest = bounds
        current_sequence = earliest - 1
        events: list[ConversationEvent] = []
        while current_sequence < latest:
            batch = await self._persistent_journal.read(
                tenant_id=self._persistent_tenant_id,
                stream_kind=EventStreamKind.CONVERSATION,
                stream_id=conversation_id,
                after_sequence=current_sequence,
                limit=1000,
            )
            if not batch:
                break
            events.extend(
                _conversation_event(durable.sequence, durable.request) for durable in batch
            )
            current_sequence = batch[-1].sequence
        return tuple(events)

    async def _stream_persistent(
        self,
        conversation_id: UUID,
        *,
        after_sequence: int,
    ) -> AsyncGenerator[ConversationEvent, None]:
        await self._validate_persistent_resume(conversation_id, after_sequence)
        async with self._lock:
            self._ensure_open()
            if self._persistent_subscribers >= self._total_subscriber_limit:
                raise EventSubscriberLimitExceeded
            self._persistent_subscribers += 1
        current_sequence = after_sequence
        try:
            while True:
                self._ensure_open()
                batch = await self._persistent_journal.read(
                    tenant_id=self._persistent_tenant_id,
                    stream_kind=EventStreamKind.CONVERSATION,
                    stream_id=conversation_id,
                    after_sequence=current_sequence,
                    limit=self._subscriber_queue_limit,
                )
                if not batch:
                    await asyncio.sleep(self._persistent_poll_seconds)
                    continue
                for durable in batch:
                    event = _conversation_event(durable.sequence, durable.request)
                    current_sequence = event.sequence
                    yield event
        finally:
            async with self._lock:
                self._persistent_subscribers -= 1

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

    @property
    def _persistent_journal(self) -> EventJournal:
        if self._journal is None:
            raise RuntimeError("persistent event journal is not configured")
        return self._journal

    @property
    def _persistent_tenant_id(self) -> UUID:
        if self._tenant_id_provider is None:
            raise RuntimeError("persistent tenant provider is not configured")
        return self._tenant_id_provider()


def _validate_event(
    *,
    message: Message,
    kind: ConversationEventKind,
    delta: str | None,
    retry: bool,
    tool_call: ToolCallEvent | None,
) -> None:
    message_statuses = {
        ConversationEventKind.ASSISTANT_STARTED: MessageStatus.PENDING,
        ConversationEventKind.ASSISTANT_DELTA: MessageStatus.STREAMING,
        ConversationEventKind.ASSISTANT_COMPLETED: MessageStatus.COMPLETED,
        ConversationEventKind.ASSISTANT_FAILED: MessageStatus.FAILED,
        ConversationEventKind.ASSISTANT_STOPPED: MessageStatus.STOPPED,
    }
    tool_kinds = {
        ConversationEventKind.ASSISTANT_TOOL_STARTED,
        ConversationEventKind.ASSISTANT_TOOL_COMPLETED,
        ConversationEventKind.ASSISTANT_TOOL_FAILED,
    }
    # 思考事件不改消息正文, 因此不能按状态映射校验: 它可以出现在 pending 或 streaming 上
    if kind in tool_kinds or kind is ConversationEventKind.ASSISTANT_REASONING:
        if message.status not in {MessageStatus.PENDING, MessageStatus.STREAMING}:
            raise ValueError("reasoning and tool events require an active assistant message")
    elif message.status is not message_statuses[kind]:
        raise ValueError("event kind does not match persisted message status")
    if kind in {
        ConversationEventKind.ASSISTANT_DELTA,
        ConversationEventKind.ASSISTANT_REASONING,
    }:
        if delta is None or not delta:
            raise ValueError("delta event requires content")
    elif delta is not None:
        raise ValueError("only delta events may contain delta content")
    if retry and kind is not ConversationEventKind.ASSISTANT_STARTED:
        raise ValueError("only started events may be marked as retry")
    if kind in tool_kinds:
        if not isinstance(tool_call, ToolCallEvent):
            raise ValueError("tool event requires safe tool call metadata")
        if kind is ConversationEventKind.ASSISTANT_TOOL_FAILED:
            if tool_call.error_code is None:
                raise ValueError("failed tool event requires error code")
        elif tool_call.error_code is not None:
            raise ValueError("only failed tool event may contain error code")
    elif tool_call is not None:
        raise ValueError("only tool events may contain tool call metadata")


def _validate_resume_position(state: _ConversationState, after_sequence: int) -> None:
    latest = state.next_sequence - 1
    earliest = state.history[0].sequence if state.history else latest + 1
    if after_sequence > latest or (state.history and after_sequence < earliest - 1):
        raise EventHistoryUnavailable


def _conversation_payload(
    *,
    turn_id: UUID,
    message: Message,
    delta: str | None,
    retry: bool,
    tool_call: ToolCallEvent | None,
) -> dict[str, object]:
    return {
        "turn_id": str(turn_id),
        "message": {
            "id": str(message.id),
            "conversation_id": str(message.conversation_id),
            "sequence_number": message.sequence_number,
            "role": message.role.value,
            "content": message.content,
            "status": message.status.value,
            "citations": [
                {
                    "position": citation.position,
                    "knowledge_base_id": citation.knowledge_base_id,
                    "chunk_id": citation.chunk_id,
                    "document_id": citation.document_id,
                    "document_name": citation.document_name,
                    "content": citation.content,
                    "score": citation.score,
                }
                for citation in message.citations
            ],
            "error_code": message.error_code,
            "model_configuration_id": (
                None
                if message.model_configuration_id is None
                else str(message.model_configuration_id)
            ),
            "model_identifier": message.model_identifier,
            "created_at": message.created_at.isoformat(),
            "updated_at": message.updated_at.isoformat(),
        },
        "delta": delta,
        "retry": retry,
        "tool_call": (
            None
            if tool_call is None
            else {
                "tool_call_id": str(tool_call.tool_call_id),
                "capability_id": str(tool_call.capability_id),
                "capability_name": tool_call.capability_name,
                "error_code": tool_call.error_code,
            }
        ),
    }


def _durable_event_key(message_id: UUID, event_type: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{message_id}:{event_type}:{digest}"


def _conversation_event(sequence: int, request: EventAppendRequest) -> ConversationEvent:
    payload = request.payload
    raw_message = cast(dict[str, object], payload["message"])
    raw_citations = cast(list[dict[str, object]], raw_message["citations"])
    message = Message(
        id=UUID(str(raw_message["id"])),
        conversation_id=UUID(str(raw_message["conversation_id"])),
        sequence_number=int(str(raw_message["sequence_number"])),
        role=MessageRole(str(raw_message["role"])),
        content=str(raw_message["content"]),
        status=MessageStatus(str(raw_message["status"])),
        citations=tuple(
            Citation(
                position=int(str(item["position"])),
                knowledge_base_id=str(item["knowledge_base_id"]),
                chunk_id=str(item["chunk_id"]),
                document_id=str(item["document_id"]),
                document_name=str(item["document_name"]),
                content=str(item["content"]),
                score=float(str(item["score"])),
            )
            for item in raw_citations
        ),
        error_code=(None if raw_message["error_code"] is None else str(raw_message["error_code"])),
        model_configuration_id=(
            None
            if raw_message.get("model_configuration_id") is None
            else UUID(str(raw_message["model_configuration_id"]))
        ),
        model_identifier=(
            None
            if raw_message.get("model_identifier") is None
            else str(raw_message["model_identifier"])
        ),
        created_at=datetime.fromisoformat(str(raw_message["created_at"])),
        updated_at=datetime.fromisoformat(str(raw_message["updated_at"])),
    )
    raw_tool_call = payload.get("tool_call")
    tool_call = None
    if raw_tool_call is not None:
        raw_tool_call = cast(dict[str, object], raw_tool_call)
        tool_call = ToolCallEvent(
            tool_call_id=UUID(str(raw_tool_call["tool_call_id"])),
            capability_id=UUID(str(raw_tool_call["capability_id"])),
            capability_name=str(raw_tool_call["capability_name"]),
            error_code=(
                None
                if raw_tool_call.get("error_code") is None
                else str(raw_tool_call["error_code"])
            ),
        )
    return ConversationEvent(
        sequence=sequence,
        turn_id=UUID(str(payload["turn_id"])),
        message=message,
        kind=ConversationEventKind(request.event_type),
        delta=None if payload["delta"] is None else str(payload["delta"]),
        retry=bool(payload["retry"]),
        tool_call=tool_call,
        occurred_at=request.occurred_at,
    )
