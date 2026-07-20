from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID


class WorkflowServiceError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __init__(self) -> None:
        super().__init__(self.message)


class WorkflowNotFound(WorkflowServiceError):
    code = "workflow_not_found"
    message = "工作流不存在"


class WorkflowRunNotFound(WorkflowServiceError):
    code = "workflow_run_not_found"
    message = "工作流运行不存在"


class WorkflowRunConflict(WorkflowServiceError):
    code = "workflow_run_conflict"
    message = "工作流运行请求已经提交"


class WorkflowRunNotActive(WorkflowServiceError):
    code = "workflow_run_not_active"
    message = "工作流运行当前不可停止"


class WorkflowExecutionUnavailable(WorkflowServiceError):
    code = "workflow_execution_unavailable"
    message = "工作流执行服务暂时不可用"
    retryable = True


class WorkflowRunResultInvalid(Exception):
    code = "workflow_run_result_invalid"


@dataclass(frozen=True, slots=True)
class WorkflowRunStopAccepted:
    run_id: UUID


__all__ = [
    "WorkflowExecutionUnavailable",
    "WorkflowNotFound",
    "WorkflowRunConflict",
    "WorkflowRunNotActive",
    "WorkflowRunNotFound",
    "WorkflowRunResultInvalid",
    "WorkflowRunStopAccepted",
    "WorkflowServiceError",
]
