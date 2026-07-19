from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from common_agent.domain.workflow import WORKFLOW_NODE_ID_MAX_LENGTH

WORKFLOW_RUN_INPUT_MAX_LENGTH = 200_000
WORKFLOW_RUN_OUTPUT_MAX_LENGTH = 200_000
WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH = 128


class WorkflowRunValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"工作流运行字段 {field} {reason}")


class WorkflowRunTransitionError(ValueError):
    def __init__(self, status: WorkflowRunStatus, action: str) -> None:
        self.status = status
        self.action = action
        super().__init__(f"工作流运行状态 {status.value} 不允许执行 {action}")


class WorkflowRunTrigger(StrEnum):
    MANUAL = "manual"
    EMPLOYEE = "employee"


class WorkflowRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


TERMINAL_WORKFLOW_RUN_STATUSES = frozenset(
    {
        WorkflowRunStatus.COMPLETED,
        WorkflowRunStatus.FAILED,
        WorkflowRunStatus.STOPPED,
    }
)


@dataclass(frozen=True, slots=True)
class WorkflowRun:
    id: UUID
    workflow_id: UUID
    trigger: WorkflowRunTrigger
    status: WorkflowRunStatus
    input: str = field(repr=False)
    output: str = field(repr=False)
    current_node_id: str | None
    completed_node_ids: tuple[str, ...]
    failed_node_id: str | None
    error_code: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime

    def __post_init__(self) -> None:
        _uuid("id", self.id)
        _uuid("workflow_id", self.workflow_id)
        if not isinstance(self.trigger, WorkflowRunTrigger):
            raise WorkflowRunValidationError("trigger", "不是支持的触发来源")
        if not isinstance(self.status, WorkflowRunStatus):
            raise WorkflowRunValidationError("status", "不是支持的状态")
        _content("input", self.input, WORKFLOW_RUN_INPUT_MAX_LENGTH, required=True)
        _content(
            "output",
            self.output,
            WORKFLOW_RUN_OUTPUT_MAX_LENGTH,
            required=self.status is WorkflowRunStatus.COMPLETED,
        )
        current_node_id = _optional_text(
            "current_node_id", self.current_node_id, WORKFLOW_NODE_ID_MAX_LENGTH
        )
        completed_node_ids = _node_ids(self.completed_node_ids)
        failed_node_id = _optional_text(
            "failed_node_id", self.failed_node_id, WORKFLOW_NODE_ID_MAX_LENGTH
        )
        error_code = _optional_text(
            "error_code", self.error_code, WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH
        )
        _timestamp("created_at", self.created_at)
        _timestamp("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise WorkflowRunValidationError("updated_at", "不能早于创建时间")
        _optional_timestamp("started_at", self.started_at)
        _optional_timestamp("finished_at", self.finished_at)
        if self.started_at is not None and self.started_at < self.created_at:
            raise WorkflowRunValidationError("started_at", "不能早于创建时间")
        if self.finished_at is not None and self.finished_at < self.created_at:
            raise WorkflowRunValidationError("finished_at", "不能早于创建时间")
        if self.finished_at is not None and self.finished_at != self.updated_at:
            raise WorkflowRunValidationError("finished_at", "必须等于终态更新时间")
        _validate_status_fields(
            status=self.status,
            output=self.output,
            current_node_id=current_node_id,
            completed_node_ids=completed_node_ids,
            failed_node_id=failed_node_id,
            error_code=error_code,
            started_at=self.started_at,
            finished_at=self.finished_at,
        )
        object.__setattr__(self, "current_node_id", current_node_id)
        object.__setattr__(self, "completed_node_ids", completed_node_ids)
        object.__setattr__(self, "failed_node_id", failed_node_id)
        object.__setattr__(self, "error_code", error_code)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_WORKFLOW_RUN_STATUSES

    @classmethod
    def create(
        cls,
        *,
        workflow_id: UUID,
        trigger: WorkflowRunTrigger,
        input: str,
        run_id: UUID | None = None,
        now: datetime | None = None,
    ) -> WorkflowRun:
        created_at = now or datetime.now(UTC)
        return cls(
            id=run_id or uuid4(),
            workflow_id=workflow_id,
            trigger=trigger,
            status=WorkflowRunStatus.PENDING,
            input=input,
            output="",
            current_node_id=None,
            completed_node_ids=(),
            failed_node_id=None,
            error_code=None,
            created_at=created_at,
            started_at=None,
            finished_at=None,
            updated_at=created_at,
        )

    def start(self, *, now: datetime | None = None) -> WorkflowRun:
        self._ensure_status({WorkflowRunStatus.PENDING}, "开始")
        changed_at = self._changed_at(now)
        return replace(
            self,
            status=WorkflowRunStatus.RUNNING,
            started_at=changed_at,
            updated_at=changed_at,
        )

    def start_node(self, node_id: str, *, now: datetime | None = None) -> WorkflowRun:
        self._ensure_status({WorkflowRunStatus.RUNNING}, "开始节点")
        normalized = _required_text("node_id", node_id, WORKFLOW_NODE_ID_MAX_LENGTH)
        if normalized in self.completed_node_ids:
            raise WorkflowRunTransitionError(self.status, "重复开始已完成节点")
        return replace(
            self,
            current_node_id=normalized,
            updated_at=self._changed_at(now),
        )

    def complete_node(self, node_id: str, *, now: datetime | None = None) -> WorkflowRun:
        self._ensure_status({WorkflowRunStatus.RUNNING}, "完成节点")
        normalized = _required_text("node_id", node_id, WORKFLOW_NODE_ID_MAX_LENGTH)
        if self.current_node_id != normalized:
            raise WorkflowRunTransitionError(self.status, "完成非当前节点")
        if normalized in self.completed_node_ids:
            raise WorkflowRunTransitionError(self.status, "重复完成节点")
        return replace(
            self,
            completed_node_ids=(*self.completed_node_ids, normalized),
            updated_at=self._changed_at(now),
        )

    def complete(self, output: str, *, now: datetime | None = None) -> WorkflowRun:
        self._ensure_status({WorkflowRunStatus.RUNNING}, "完成运行")
        changed_at = self._changed_at(now)
        return replace(
            self,
            status=WorkflowRunStatus.COMPLETED,
            output=output,
            finished_at=changed_at,
            updated_at=changed_at,
        )

    def fail(self, error_code: str, *, now: datetime | None = None) -> WorkflowRun:
        self._ensure_status(
            {WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING},
            "标记失败",
        )
        changed_at = self._changed_at(now)
        return replace(
            self,
            status=WorkflowRunStatus.FAILED,
            failed_node_id=self.current_node_id,
            error_code=error_code,
            finished_at=changed_at,
            updated_at=changed_at,
        )

    def stop(self, *, now: datetime | None = None) -> WorkflowRun:
        self._ensure_status(
            {WorkflowRunStatus.PENDING, WorkflowRunStatus.RUNNING},
            "停止",
        )
        changed_at = self._changed_at(now)
        return replace(
            self,
            status=WorkflowRunStatus.STOPPED,
            failed_node_id=None,
            error_code=None,
            finished_at=changed_at,
            updated_at=changed_at,
        )

    def _changed_at(self, value: datetime | None) -> datetime:
        changed_at = value or datetime.now(UTC)
        _timestamp("updated_at", changed_at)
        if changed_at < self.updated_at:
            raise WorkflowRunValidationError("updated_at", "不能早于当前更新时间")
        return changed_at

    def _ensure_status(self, allowed: set[WorkflowRunStatus], action: str) -> None:
        if self.status not in allowed:
            raise WorkflowRunTransitionError(self.status, action)


def _validate_status_fields(
    *,
    status: WorkflowRunStatus,
    output: str,
    current_node_id: str | None,
    completed_node_ids: tuple[str, ...],
    failed_node_id: str | None,
    error_code: str | None,
    started_at: datetime | None,
    finished_at: datetime | None,
) -> None:
    if current_node_id is not None and completed_node_ids:
        current_position = (
            completed_node_ids.index(current_node_id)
            if current_node_id in completed_node_ids
            else -1
        )
        if current_position not in {-1, len(completed_node_ids) - 1}:
            raise WorkflowRunValidationError("current_node_id", "必须是最后完成或正在执行的节点")
    if status is WorkflowRunStatus.PENDING:
        if (
            any(
                value is not None
                for value in (current_node_id, failed_node_id, error_code, started_at, finished_at)
            )
            or completed_node_ids
            or output
        ):
            raise WorkflowRunValidationError("status", "pending 状态包含运行结果")
        return
    if status is WorkflowRunStatus.RUNNING:
        if started_at is None or finished_at is not None or failed_node_id or error_code or output:
            raise WorkflowRunValidationError("status", "running 状态字段不一致")
        return
    if finished_at is None:
        raise WorkflowRunValidationError("finished_at", "终态必须包含完成时间")
    if status is WorkflowRunStatus.COMPLETED:
        if started_at is None or not output.strip() or failed_node_id or error_code:
            raise WorkflowRunValidationError("status", "completed 状态字段不一致")
    elif status is WorkflowRunStatus.FAILED:
        if not error_code or output or failed_node_id != current_node_id:
            raise WorkflowRunValidationError("status", "failed 状态字段不一致")
    elif output or failed_node_id or error_code:
        raise WorkflowRunValidationError("status", "stopped 状态字段不一致")


def _node_ids(values: Iterable[str]) -> tuple[str, ...]:
    result = tuple(
        _required_text("completed_node_ids", value, WORKFLOW_NODE_ID_MAX_LENGTH) for value in values
    )
    if len(set(result)) != len(result):
        raise WorkflowRunValidationError("completed_node_ids", "不能重复")
    return result


def _content(field: str, value: object, maximum: int, *, required: bool) -> str:
    if not isinstance(value, str):
        raise WorkflowRunValidationError(field, "必须是字符串")
    if required and not value.strip():
        raise WorkflowRunValidationError(field, "不能为空")
    if not required and value and not value.strip():
        raise WorkflowRunValidationError(field, "不能只包含空白")
    if len(value) > maximum:
        raise WorkflowRunValidationError(field, f"不能超过 {maximum} 个字符")
    return value


def _required_text(field: str, value: object, maximum: int) -> str:
    normalized = _optional_text(field, value, maximum)
    if normalized is None:
        raise WorkflowRunValidationError(field, "不能为空")
    return normalized


def _optional_text(field: str, value: object | None, maximum: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise WorkflowRunValidationError(field, "必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise WorkflowRunValidationError(field, "不能为空")
    if len(normalized) > maximum:
        raise WorkflowRunValidationError(field, f"不能超过 {maximum} 个字符")
    return normalized


def _uuid(field: str, value: object) -> UUID:
    if not isinstance(value, UUID):
        raise WorkflowRunValidationError(field, "必须是 UUID")
    return value


def _timestamp(field: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise WorkflowRunValidationError(field, "必须是时间")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise WorkflowRunValidationError(field, "必须使用 UTC 时区")
    return value


def _optional_timestamp(field: str, value: object | None) -> datetime | None:
    return None if value is None else _timestamp(field, value)
