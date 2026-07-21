from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from time import monotonic
from uuid import UUID

from common_agent.domain.workflow_run import WorkflowRun, WorkflowRunStatus


class WorkflowEventKind(StrEnum):
    RUN_STARTED = "workflow.run.started"
    NODE_STARTED = "workflow.node.started"
    NODE_COMPLETED = "workflow.node.completed"
    NODE_FAILED = "workflow.node.failed"
    RUN_COMPLETED = "workflow.run.completed"
    RUN_FAILED = "workflow.run.failed"
    RUN_STOPPED = "workflow.run.stopped"


class WorkflowEventHistoryUnavailable(Exception):
    code = "workflow_event_history_unavailable"
    retryable = False

    def __init__(self) -> None:
        super().__init__("工作流事件历史已不可续传,请重新加载运行摘要")


class WorkflowEventStreamOverflow(Exception):
    code = "workflow_event_stream_overflow"
    retryable = True

    def __init__(self) -> None:
        super().__init__("工作流事件消费者处理速度过慢,请重新连接")


class WorkflowEventSubscriberLimitExceeded(WorkflowEventStreamOverflow):
    def __init__(self) -> None:
        super().__init__()
        self.args = ("工作流事件订阅者已达到容量上限,请稍后重连",)


@dataclass(frozen=True, slots=True)
class WorkflowRunEvent:
    sequence: int
    run: WorkflowRun
    kind: WorkflowEventKind
    node_id: str | None = None
    occurred_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def run_id(self) -> UUID:
        return self.run.id

    @property
    def workflow_id(self) -> UUID:
        return self.run.workflow_id


@dataclass(frozen=True, slots=True)
class WorkflowEventLifecycleSnapshot:
    state_count: int
    active_state_count: int
    subscriber_count: int
    retained_event_count: int


@dataclass(slots=True)
class _WorkflowEventState:
    next_sequence: int = 1
    history: deque[WorkflowRunEvent] = field(default_factory=deque)
    subscribers: set[asyncio.Queue[WorkflowRunEvent | object]] = field(default_factory=set)
    active: bool = False
    last_accessed: float = field(default_factory=monotonic)
    cleanup_handle: asyncio.TimerHandle | None = field(default=None, repr=False)


_OVERFLOW = object()


class WorkflowEventBroker:
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
        self._key_namespace = key_namespace or (lambda run_id: str(run_id))
        self._states: dict[str, _WorkflowEventState] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def validate_resume(self, run_id: UUID, *, after_sequence: int = 0) -> None:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        async with self._lock:
            self._ensure_open()
            key = self._key_namespace(run_id)
            state, created = self._state_locked(key)
            try:
                _validate_resume_position(state, after_sequence)
            except WorkflowEventHistoryUnavailable:
                if created:
                    self._drop_state_locked(key, state)
                raise
            self._touch_locked(key, state)

    async def publish(
        self,
        *,
        run: WorkflowRun,
        kind: WorkflowEventKind,
        node_id: str | None = None,
    ) -> WorkflowRunEvent:
        _validate_event(run=run, kind=kind, node_id=node_id)
        async with self._lock:
            self._ensure_open()
            key = self._key_namespace(run.id)
            state, _ = self._state_locked(key)
            event = WorkflowRunEvent(
                sequence=state.next_sequence,
                run=run,
                kind=kind,
                node_id=node_id,
            )
            state.next_sequence += 1
            state.history.append(event)
            while len(state.history) > self._history_limit:
                state.history.popleft()
            if kind is WorkflowEventKind.RUN_STARTED:
                state.active = True
            elif kind in {
                WorkflowEventKind.RUN_COMPLETED,
                WorkflowEventKind.RUN_FAILED,
                WorkflowEventKind.RUN_STOPPED,
            }:
                state.active = False
            state.last_accessed = monotonic()

            overflowed: list[asyncio.Queue[WorkflowRunEvent | object]] = []
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
        run_id: UUID,
        *,
        after_sequence: int = 0,
    ) -> AsyncGenerator[WorkflowRunEvent, None]:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        queue: asyncio.Queue[WorkflowRunEvent | object] = asyncio.Queue(
            maxsize=self._subscriber_queue_limit
        )
        async with self._lock:
            self._ensure_open()
            key = self._key_namespace(run_id)
            state, created = self._state_locked(key)
            try:
                _validate_resume_position(state, after_sequence)
            except WorkflowEventHistoryUnavailable:
                if created:
                    self._drop_state_locked(key, state)
                raise
            if len(state.subscribers) >= self._subscriber_limit:
                if created:
                    self._drop_state_locked(key, state)
                raise WorkflowEventSubscriberLimitExceeded
            if self._subscriber_count_locked() >= self._total_subscriber_limit:
                if created:
                    self._drop_state_locked(key, state)
                raise WorkflowEventSubscriberLimitExceeded
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
                    raise WorkflowEventStreamOverflow
                if not isinstance(queued, WorkflowRunEvent):
                    raise RuntimeError("unexpected workflow event")
                yield queued
        finally:
            async with self._lock:
                current = self._states.get(key)
                if current is not None:
                    current.subscribers.discard(queue)
                    current.last_accessed = monotonic()
                    self._schedule_cleanup_locked(key, current)

    async def lifecycle_snapshot(self) -> WorkflowEventLifecycleSnapshot:
        async with self._lock:
            self._prune_expired_locked()
            return WorkflowEventLifecycleSnapshot(
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

    def _state_locked(self, key: str) -> tuple[_WorkflowEventState, bool]:
        now = monotonic()
        self._prune_expired_locked(now)
        state = self._states.get(key)
        if state is not None:
            state.last_accessed = now
            return state, False

        self._evict_lru_locked()
        state = _WorkflowEventState(last_accessed=now)
        self._states[key] = state
        return state, True

    def _touch_locked(self, key: str, state: _WorkflowEventState) -> None:
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
        state: _WorkflowEventState,
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
            name=f"workflow-event-expiry-{key}",
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

    def _drop_state_locked(self, key: str, state: _WorkflowEventState) -> None:
        if self._states.get(key) is not state:
            return
        self._cancel_cleanup_locked(state)
        self._states.pop(key, None)

    @staticmethod
    def _cancel_cleanup_locked(state: _WorkflowEventState) -> None:
        handle = state.cleanup_handle
        state.cleanup_handle = None
        if handle is not None:
            handle.cancel()

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("workflow event broker is closed")


def _validate_event(
    *,
    run: WorkflowRun,
    kind: WorkflowEventKind,
    node_id: str | None,
) -> None:
    expected_status = {
        WorkflowEventKind.RUN_STARTED: WorkflowRunStatus.RUNNING,
        WorkflowEventKind.NODE_STARTED: WorkflowRunStatus.RUNNING,
        WorkflowEventKind.NODE_COMPLETED: WorkflowRunStatus.RUNNING,
        WorkflowEventKind.NODE_FAILED: WorkflowRunStatus.FAILED,
        WorkflowEventKind.RUN_COMPLETED: WorkflowRunStatus.COMPLETED,
        WorkflowEventKind.RUN_FAILED: WorkflowRunStatus.FAILED,
        WorkflowEventKind.RUN_STOPPED: WorkflowRunStatus.STOPPED,
    }[kind]
    if run.status is not expected_status:
        raise ValueError("事件类型与已持久化运行状态不一致")

    node_events = {
        WorkflowEventKind.NODE_STARTED,
        WorkflowEventKind.NODE_COMPLETED,
        WorkflowEventKind.NODE_FAILED,
    }
    if kind not in node_events:
        if node_id is not None:
            raise ValueError("运行事件不能包含节点")
        return
    if node_id is None:
        raise ValueError("节点事件必须包含节点")
    if kind is WorkflowEventKind.NODE_STARTED:
        valid = run.current_node_id == node_id and node_id not in run.completed_node_ids
    elif kind is WorkflowEventKind.NODE_COMPLETED:
        valid = run.current_node_id == node_id and node_id in run.completed_node_ids
    else:
        valid = run.failed_node_id == node_id
    if not valid:
        raise ValueError("节点事件与已持久化节点状态不一致")


def _validate_resume_position(state: _WorkflowEventState, after_sequence: int) -> None:
    latest = state.next_sequence - 1
    earliest = state.history[0].sequence if state.history else latest + 1
    if after_sequence > latest or (state.history and after_sequence < earliest - 1):
        raise WorkflowEventHistoryUnavailable
