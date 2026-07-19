from __future__ import annotations

from common_agent.domain.workflow import WorkflowNodeType


class WorkflowCompilationError(Exception):
    code: str
    retryable = False


class WorkflowNodeNotRegistered(WorkflowCompilationError):
    code = "workflow_node_not_registered"

    def __init__(self, node_type: WorkflowNodeType) -> None:
        self.node_type = node_type
        super().__init__("工作流包含尚未注册的节点类型")


class WorkflowNodeConfigurationInvalid(WorkflowCompilationError):
    code = "workflow_node_configuration_invalid"

    def __init__(self) -> None:
        super().__init__("工作流节点配置无效")


class WorkflowCompilationFailed(WorkflowCompilationError):
    code = "workflow_compilation_failed"

    def __init__(self) -> None:
        super().__init__("工作流编译失败")


class WorkflowExecutionError(Exception):
    code: str
    retryable: bool


class WorkflowStepLimitExceeded(WorkflowExecutionError):
    code = "workflow_step_limit_exceeded"
    retryable = False

    def __init__(self) -> None:
        super().__init__("工作流执行超过步数上限")


class WorkflowExecutionFailed(WorkflowExecutionError):
    code = "workflow_execution_failed"
    retryable = True

    def __init__(self) -> None:
        super().__init__("工作流执行失败")


class WorkflowExecutionStopped(WorkflowExecutionError):
    code = "workflow_execution_stopped"
    retryable = False

    def __init__(self) -> None:
        super().__init__("工作流执行已停止")
