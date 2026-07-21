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

from common_agent.domain.workflow import AiChatTargetType
from common_agent.domain.workflow_run import (
    WorkflowAiTargetSummary,
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunStatus,
    WorkflowRunTrigger,
)
from common_agent.events import EventAppendRequest, EventJournal, EventStreamKind


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
        self._key_namespace = key_namespace or (lambda run_id: str(run_id))
        self._journal = journal
        self._tenant_id_provider = tenant_id_provider
        self._persistent_poll_seconds = persistent_poll_seconds
        self._retention_days = retention_days
        self._maximum_events_per_stream = maximum_events_per_stream
        self._persistent_subscribers = 0
        self._states: dict[str, _WorkflowEventState] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def validate_resume(self, run_id: UUID, *, after_sequence: int = 0) -> None:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        if self._journal is not None:
            self._ensure_open()
            await self._validate_persistent_resume(run_id, after_sequence)
            return
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
        if self._journal is not None:
            self._ensure_open()
            return await self._publish_persistent(run=run, kind=kind, node_id=node_id)
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
        if self._journal is not None:
            async for event in self._stream_persistent(run_id, after_sequence=after_sequence):
                yield event
            return
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

    async def _publish_persistent(
        self,
        *,
        run: WorkflowRun,
        kind: WorkflowEventKind,
        node_id: str | None,
    ) -> WorkflowRunEvent:
        tenant_id = self._persistent_tenant_id
        occurred_at = datetime.now(UTC)
        payload = _workflow_payload(run=run, node_id=node_id)
        event_key = _durable_event_key(run.id, kind.value, payload)
        durable = await self._persistent_journal.append(
            EventAppendRequest(
                event_id=uuid5(
                    NAMESPACE_URL,
                    f"common-agent:{tenant_id}:workflow:{run.id}:{event_key}",
                ),
                tenant_id=tenant_id,
                stream_kind=EventStreamKind.WORKFLOW,
                stream_id=run.id,
                event_key=event_key,
                event_type=kind.value,
                payload=payload,
                occurred_at=occurred_at,
            ),
            retention_until=occurred_at + timedelta(days=self._retention_days),
            maximum_events_per_stream=self._maximum_events_per_stream,
        )
        return _workflow_event(durable.sequence, durable.request)

    async def _validate_persistent_resume(self, run_id: UUID, after_sequence: int) -> None:
        bounds = await self._persistent_journal.bounds(
            tenant_id=self._persistent_tenant_id,
            stream_kind=EventStreamKind.WORKFLOW,
            stream_id=run_id,
        )
        if bounds is None:
            if after_sequence != 0:
                raise WorkflowEventHistoryUnavailable
            return
        earliest, latest = bounds
        if after_sequence > latest or after_sequence < earliest - 1:
            raise WorkflowEventHistoryUnavailable

    async def _stream_persistent(
        self,
        run_id: UUID,
        *,
        after_sequence: int,
    ) -> AsyncGenerator[WorkflowRunEvent, None]:
        await self._validate_persistent_resume(run_id, after_sequence)
        async with self._lock:
            self._ensure_open()
            if self._persistent_subscribers >= self._total_subscriber_limit:
                raise WorkflowEventSubscriberLimitExceeded
            self._persistent_subscribers += 1
        current_sequence = after_sequence
        try:
            while True:
                self._ensure_open()
                batch = await self._persistent_journal.read(
                    tenant_id=self._persistent_tenant_id,
                    stream_kind=EventStreamKind.WORKFLOW,
                    stream_id=run_id,
                    after_sequence=current_sequence,
                    limit=self._subscriber_queue_limit,
                )
                if not batch:
                    await asyncio.sleep(self._persistent_poll_seconds)
                    continue
                for durable in batch:
                    event = _workflow_event(durable.sequence, durable.request)
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


def _workflow_payload(*, run: WorkflowRun, node_id: str | None) -> dict[str, object]:
    origin: dict[str, object] | None = None
    if run.origin is not None:
        origin = {
            "employee_id": str(run.origin.employee_id),
            "conversation_id": str(run.origin.conversation_id),
            "assistant_message_id": str(run.origin.assistant_message_id),
        }
    return {
        "run": {
            "id": str(run.id),
            "workflow_id": str(run.workflow_id),
            "trigger": run.trigger.value,
            "status": run.status.value,
            "input": run.input,
            "output": run.output,
            "current_node_id": run.current_node_id,
            "completed_node_ids": list(run.completed_node_ids),
            "failed_node_id": run.failed_node_id,
            "error_code": run.error_code,
            "origin": origin,
            "ai_targets": [
                {
                    "node_id": target.node_id,
                    "target_type": target.target_type.value,
                    "target_id": str(target.target_id),
                    "target_name": target.target_name,
                    "model_configuration_id": str(target.model_configuration_id),
                    "model_identifier": target.model_identifier,
                }
                for target in run.ai_targets
            ],
            "created_at": run.created_at.isoformat(),
            "started_at": run.started_at.isoformat() if run.started_at is not None else None,
            "finished_at": run.finished_at.isoformat() if run.finished_at is not None else None,
            "updated_at": run.updated_at.isoformat(),
        },
        "node_id": node_id,
    }


def _durable_event_key(run_id: UUID, event_type: str, payload: dict[str, object]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"{run_id}:{event_type}:{digest}"


def _workflow_event(sequence: int, request: EventAppendRequest) -> WorkflowRunEvent:
    payload = request.payload
    raw = cast(dict[str, object], payload["run"])
    raw_origin = cast(dict[str, object] | None, raw["origin"])
    origin = (
        None
        if raw_origin is None
        else WorkflowRunOrigin(
            employee_id=UUID(str(raw_origin["employee_id"])),
            conversation_id=UUID(str(raw_origin["conversation_id"])),
            assistant_message_id=UUID(str(raw_origin["assistant_message_id"])),
        )
    )
    run = WorkflowRun(
        id=UUID(str(raw["id"])),
        workflow_id=UUID(str(raw["workflow_id"])),
        trigger=WorkflowRunTrigger(str(raw["trigger"])),
        status=WorkflowRunStatus(str(raw["status"])),
        input=str(raw["input"]),
        output=str(raw["output"]),
        current_node_id=None if raw["current_node_id"] is None else str(raw["current_node_id"]),
        completed_node_ids=tuple(
            str(value) for value in cast(list[object], raw["completed_node_ids"])
        ),
        failed_node_id=None if raw["failed_node_id"] is None else str(raw["failed_node_id"]),
        error_code=None if raw["error_code"] is None else str(raw["error_code"]),
        origin=origin,
        ai_targets=tuple(
            WorkflowAiTargetSummary(
                node_id=str(value["node_id"]),
                target_type=AiChatTargetType(str(value["target_type"])),
                target_id=UUID(str(value["target_id"])),
                target_name=str(value["target_name"]),
                model_configuration_id=UUID(str(value["model_configuration_id"])),
                model_identifier=str(value["model_identifier"]),
            )
            for value in cast(list[dict[str, object]], raw.get("ai_targets", []))
        ),
        created_at=datetime.fromisoformat(str(raw["created_at"])),
        started_at=(
            None if raw["started_at"] is None else datetime.fromisoformat(str(raw["started_at"]))
        ),
        finished_at=(
            None if raw["finished_at"] is None else datetime.fromisoformat(str(raw["finished_at"]))
        ),
        updated_at=datetime.fromisoformat(str(raw["updated_at"])),
    )
    return WorkflowRunEvent(
        sequence=sequence,
        run=run,
        kind=WorkflowEventKind(request.event_type),
        node_id=None if payload["node_id"] is None else str(payload["node_id"]),
        occurred_at=request.occurred_at,
    )
