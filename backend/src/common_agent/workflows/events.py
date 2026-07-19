from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
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


@dataclass(slots=True)
class _WorkflowEventState:
    next_sequence: int = 1
    history: deque[WorkflowRunEvent] = field(default_factory=deque)
    subscribers: set[asyncio.Queue[WorkflowRunEvent | object]] = field(default_factory=set)


_OVERFLOW = object()


class WorkflowEventBroker:
    def __init__(self, *, history_limit: int = 512, subscriber_queue_limit: int = 128) -> None:
        if history_limit < 1:
            raise ValueError("history_limit must be positive")
        if subscriber_queue_limit < 1:
            raise ValueError("subscriber_queue_limit must be positive")
        self._history_limit = history_limit
        self._subscriber_queue_limit = subscriber_queue_limit
        self._states: dict[UUID, _WorkflowEventState] = {}
        self._lock = asyncio.Lock()

    async def validate_resume(self, run_id: UUID, *, after_sequence: int = 0) -> None:
        if after_sequence < 0:
            raise ValueError("after_sequence must not be negative")
        async with self._lock:
            state = self._states.setdefault(run_id, _WorkflowEventState())
            _validate_resume_position(state, after_sequence)

    async def publish(
        self,
        *,
        run: WorkflowRun,
        kind: WorkflowEventKind,
        node_id: str | None = None,
    ) -> WorkflowRunEvent:
        _validate_event(run=run, kind=kind, node_id=node_id)
        async with self._lock:
            state = self._states.setdefault(run.id, _WorkflowEventState())
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
            state = self._states.setdefault(run_id, _WorkflowEventState())
            _validate_resume_position(state, after_sequence)
            replay = tuple(event for event in state.history if event.sequence > after_sequence)
            state.subscribers.add(queue)

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
                current = self._states.get(run_id)
                if current is not None:
                    current.subscribers.discard(queue)


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
