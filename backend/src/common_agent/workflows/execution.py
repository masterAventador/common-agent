from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable
from uuid import UUID

from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import WorkflowAiTargetSummary
from common_agent.runtimes.base import RuntimeKnowledgeChunk


@dataclass(frozen=True, slots=True)
class WorkflowNodeExecutionContext:
    user_input: str = field(repr=False)
    output: str = field(repr=False)
    knowledge: tuple[RuntimeKnowledgeChunk, ...] = field(repr=False)
    node_id: str | None = None
    run_id: UUID | None = None
    observer: WorkflowExecutionObserver | None = field(default=None, repr=False)
    stop: WorkflowExecutionStopSignal | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.user_input, str) or not self.user_input.strip():
            raise ValueError("工作流节点输入不能为空")
        if not isinstance(self.output, str):
            raise ValueError("工作流节点输出必须是文本")
        if not isinstance(self.knowledge, tuple) or any(
            not isinstance(chunk, RuntimeKnowledgeChunk) for chunk in self.knowledge
        ):
            raise ValueError("工作流节点知识上下文无效")
        if self.node_id is not None and (
            not isinstance(self.node_id, str) or not self.node_id.strip()
        ):
            raise ValueError("工作流节点 ID 无效")
        if self.run_id is not None and not isinstance(self.run_id, UUID):
            raise ValueError("工作流运行 ID 无效")

    async def report_ai_target(self, summary: WorkflowAiTargetSummary) -> None:
        if self.observer is None:
            return
        if self.node_id is None or summary.node_id != self.node_id:
            raise ValueError("AI 执行目标摘要与当前节点不一致")
        await self.observer.ai_target_resolved(summary)


@dataclass(frozen=True, slots=True)
class WorkflowNodeExecutionResult:
    output: str | None = field(default=None, repr=False)
    knowledge: tuple[RuntimeKnowledgeChunk, ...] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.output is None and self.knowledge is None:
            raise ValueError("工作流节点结果不能为空")
        if self.output is not None and (
            not isinstance(self.output, str) or not self.output.strip()
        ):
            raise ValueError("工作流节点输出不能为空")
        if self.knowledge is not None and (
            not isinstance(self.knowledge, tuple)
            or any(not isinstance(chunk, RuntimeKnowledgeChunk) for chunk in self.knowledge)
        ):
            raise ValueError("工作流节点知识结果无效")


@runtime_checkable
class WorkflowExecutionObserver(Protocol):
    async def node_started(self, node_id: str) -> None: ...

    async def node_completed(self, node_id: str) -> None: ...

    async def ai_target_resolved(self, summary: WorkflowAiTargetSummary) -> None: ...


@runtime_checkable
class WorkflowExecutionStopSignal(Protocol):
    @property
    def is_requested(self) -> bool: ...

    async def wait(self) -> None: ...


class WorkflowExecutionStopToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_requested(self) -> bool:
        return self._event.is_set()

    def request_stop(self) -> bool:
        if self._event.is_set():
            return False
        self._event.set()
        return True

    async def wait(self) -> None:
        await self._event.wait()


@dataclass(frozen=True, slots=True)
class WorkflowExecutionResult:
    output: str = field(repr=False)
    completed_node_ids: tuple[str, ...]
    step_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.output, str) or not self.output.strip():
            raise ValueError("工作流执行输出不能为空")
        if (
            not isinstance(self.completed_node_ids, tuple)
            or not self.completed_node_ids
            or any(
                not isinstance(node_id, str) or not node_id.strip()
                for node_id in self.completed_node_ids
            )
            or len(set(self.completed_node_ids)) != len(self.completed_node_ids)
        ):
            raise ValueError("工作流已完成节点无效")
        if (
            not isinstance(self.step_count, int)
            or isinstance(self.step_count, bool)
            or self.step_count != len(self.completed_node_ids)
        ):
            raise ValueError("工作流执行步数与已完成节点不一致")


@runtime_checkable
class CompiledWorkflow(Protocol):
    @property
    def workflow_id(self) -> str: ...

    async def invoke(
        self,
        user_input: str,
        *,
        observer: WorkflowExecutionObserver | None = None,
        stop: WorkflowExecutionStopSignal | None = None,
        run_id: UUID | None = None,
    ) -> WorkflowExecutionResult: ...


@runtime_checkable
class WorkflowCompiler(Protocol):
    def compile(self, workflow: WorkflowDefinition) -> CompiledWorkflow: ...
