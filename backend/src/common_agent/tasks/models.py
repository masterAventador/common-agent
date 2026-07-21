from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class TaskKind(StrEnum):
    CONVERSATION_REPLY = "conversation.reply"
    WORKFLOW_RUN = "workflow.run"


class TaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True, slots=True)
class ConversationReplyPayload:
    conversation_id: UUID
    turn_id: UUID
    user_message_id: UUID
    assistant_message_id: UUID
    retry: bool

    def __post_init__(self) -> None:
        for name in ("conversation_id", "turn_id", "user_message_id", "assistant_message_id"):
            _uuid(name, getattr(self, name))
        if not isinstance(self.retry, bool):
            raise ValueError("retry must be boolean")


@dataclass(frozen=True, slots=True)
class WorkflowRunPayload:
    run_id: UUID
    workflow_id: UUID

    def __post_init__(self) -> None:
        _uuid("run_id", self.run_id)
        _uuid("workflow_id", self.workflow_id)


TaskPayload = ConversationReplyPayload | WorkflowRunPayload


@dataclass(frozen=True, slots=True)
class TaskRequest:
    task_id: UUID
    tenant_id: UUID
    kind: TaskKind
    idempotency_key: str
    aggregate_id: UUID
    payload: TaskPayload
    created_at: datetime

    def __post_init__(self) -> None:
        _uuid("task_id", self.task_id)
        _uuid("tenant_id", self.tenant_id)
        _uuid("aggregate_id", self.aggregate_id)
        _utc("created_at", self.created_at)
        if not isinstance(self.kind, TaskKind):
            raise ValueError("kind must be TaskKind")
        expected_payload = {
            TaskKind.CONVERSATION_REPLY: ConversationReplyPayload,
            TaskKind.WORKFLOW_RUN: WorkflowRunPayload,
        }[self.kind]
        if not isinstance(self.payload, expected_payload):
            raise ValueError("payload does not match task kind")
        payload_aggregate = (
            self.payload.conversation_id
            if isinstance(self.payload, ConversationReplyPayload)
            else self.payload.run_id
        )
        if payload_aggregate != self.aggregate_id:
            raise ValueError("payload aggregate does not match aggregate_id")
        _safe_text("idempotency_key", self.idempotency_key, maximum=191)


@dataclass(frozen=True, slots=True)
class DurableTask:
    request: TaskRequest
    state: TaskState
    attempts: int
    max_attempts: int
    available_at: datetime
    lease_owner: str | None
    lease_token: UUID | None
    lease_until: datetime | None
    stop_requested: bool
    error_code: str | None
    updated_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request, TaskRequest):
            raise ValueError("request must be TaskRequest")
        if not isinstance(self.state, TaskState):
            raise ValueError("state must be TaskState")
        if not isinstance(self.attempts, int) or isinstance(self.attempts, bool):
            raise ValueError("attempts must be an integer")
        if not isinstance(self.max_attempts, int) or isinstance(self.max_attempts, bool):
            raise ValueError("max_attempts must be an integer")
        if not 1 <= self.max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        if not 0 <= self.attempts <= self.max_attempts:
            raise ValueError("attempts must be between zero and max_attempts")
        _utc("available_at", self.available_at)
        _utc("updated_at", self.updated_at)
        if self.updated_at < self.request.created_at:
            raise ValueError("updated_at must not precede created_at")
        if not isinstance(self.stop_requested, bool):
            raise ValueError("stop_requested must be boolean")
        if self.state is TaskState.RUNNING:
            if self.lease_owner is None or self.lease_token is None or self.lease_until is None:
                raise ValueError("running task requires a lease")
            _safe_text("lease_owner", self.lease_owner, maximum=128)
            _uuid("lease_token", self.lease_token)
            _utc("lease_until", self.lease_until)
        elif (
            self.lease_owner is not None
            or self.lease_token is not None
            or self.lease_until is not None
        ):
            raise ValueError("only running tasks may hold a lease")
        if self.state in {TaskState.FAILED, TaskState.RETRY_WAIT}:
            if self.error_code is None:
                raise ValueError("failed or retrying task requires error_code")
            _safe_text("error_code", self.error_code, maximum=128)
        elif self.error_code is not None:
            raise ValueError("only failed or retrying tasks may have error_code")

    @property
    def is_terminal(self) -> bool:
        return self.state in {TaskState.SUCCEEDED, TaskState.FAILED, TaskState.CANCELLED}

    @property
    def is_active(self) -> bool:
        return not self.is_terminal


@dataclass(frozen=True, slots=True)
class TaskEnqueueResult:
    task: DurableTask
    created: bool


@dataclass(frozen=True, slots=True)
class TaskLeaseState:
    owned: bool
    stop_requested: bool


@dataclass(frozen=True, slots=True)
class TaskBacklog:
    pending: int = 0
    running: int = 0
    retry_wait: int = 0
    failed: int = 0
    oldest_available_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in ("pending", "running", "retry_wait", "failed"):
            value = getattr(self, name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{name} must be a non-negative integer")
        if self.oldest_available_at is not None:
            _utc("oldest_available_at", self.oldest_available_at)


class TaskNotFound(LookupError):
    pass


class TaskIdempotencyConflict(RuntimeError):
    pass


def _uuid(name: str, value: object) -> UUID:
    if not isinstance(value, UUID):
        raise ValueError(f"{name} must be UUID")
    return value


def _utc(name: str, value: object) -> datetime:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError(f"{name} must use UTC")
    return value


def _safe_text(name: str, value: object, *, maximum: int) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value
        or len(value) > maximum
        or any(character in value for character in "\r\n\0")
    ):
        raise ValueError(f"{name} must be safe non-empty text")
    return value


__all__ = [
    "ConversationReplyPayload",
    "DurableTask",
    "TaskBacklog",
    "TaskEnqueueResult",
    "TaskIdempotencyConflict",
    "TaskKind",
    "TaskLeaseState",
    "TaskNotFound",
    "TaskPayload",
    "TaskRequest",
    "TaskState",
    "WorkflowRunPayload",
]
