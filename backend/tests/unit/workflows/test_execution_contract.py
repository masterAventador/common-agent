from __future__ import annotations

import asyncio
from typing import cast
from uuid import UUID

import pytest

from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import WorkflowAiTargetSummary
from common_agent.runtimes.base import RuntimeKnowledgeChunk
from common_agent.workflows.execution import (
    CompiledWorkflow,
    WorkflowCompiler,
    WorkflowExecutionObserver,
    WorkflowExecutionResult,
    WorkflowExecutionStopSignal,
    WorkflowExecutionStopToken,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
)


class _ObserverProbe:
    async def node_started(self, node_id: str) -> None:
        del node_id

    async def node_completed(self, node_id: str) -> None:
        del node_id

    async def ai_target_resolved(self, summary: WorkflowAiTargetSummary) -> None:
        del summary


class _CompiledProbe:
    workflow_id = "workflow-probe"

    async def invoke(
        self,
        user_input: str,
        *,
        observer: WorkflowExecutionObserver | None = None,
        stop: WorkflowExecutionStopSignal | None = None,
        run_id: UUID | None = None,
    ) -> WorkflowExecutionResult:
        del observer, stop, run_id
        return WorkflowExecutionResult(
            output=user_input,
            completed_node_ids=("start", "end"),
            step_count=2,
        )


class _CompilerProbe:
    def compile(self, workflow: WorkflowDefinition) -> CompiledWorkflow:
        del workflow
        return _CompiledProbe()


def test_platform_graph_execution_protocol_is_strict_and_runtime_checkable() -> None:
    token = WorkflowExecutionStopToken()
    context = WorkflowNodeExecutionContext(user_input="输入", output="", knowledge=())
    node_result = WorkflowNodeExecutionResult(output="输出")
    execution_result = asyncio.run(_CompiledProbe().invoke("完成", observer=_ObserverProbe()))

    assert isinstance(token, WorkflowExecutionStopSignal)
    assert isinstance(_CompiledProbe(), CompiledWorkflow)
    assert isinstance(_CompilerProbe(), WorkflowCompiler)
    assert context.user_input == "输入"
    assert node_result.output == "输出"
    assert execution_result.completed_node_ids == ("start", "end")
    assert token.request_stop() is True
    assert token.request_stop() is False
    assert token.is_requested is True
    asyncio.run(asyncio.wait_for(token.wait(), timeout=0.1))

    with pytest.raises(ValueError):
        WorkflowNodeExecutionContext(user_input="", output="", knowledge=())
    with pytest.raises(ValueError):
        WorkflowNodeExecutionContext(
            user_input="输入",
            output=cast(str, None),
            knowledge=(),
        )
    with pytest.raises(ValueError):
        WorkflowNodeExecutionContext(
            user_input="输入",
            output="",
            knowledge=cast(tuple[RuntimeKnowledgeChunk, ...], ("非法知识",)),
        )
    with pytest.raises(ValueError):
        WorkflowNodeExecutionResult()
    with pytest.raises(ValueError):
        WorkflowNodeExecutionResult(output=" ")
    with pytest.raises(ValueError):
        WorkflowNodeExecutionResult(
            knowledge=cast(tuple[RuntimeKnowledgeChunk, ...], ("非法知识",))
        )
    with pytest.raises(ValueError):
        WorkflowExecutionResult(output="", completed_node_ids=("start",), step_count=1)
    with pytest.raises(ValueError):
        WorkflowExecutionResult(
            output="完成",
            completed_node_ids=("start", "start"),
            step_count=2,
        )
    with pytest.raises(ValueError):
        WorkflowExecutionResult(output="完成", completed_node_ids=("start",), step_count=2)
