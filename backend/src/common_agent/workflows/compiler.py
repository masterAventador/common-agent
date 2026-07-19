from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, cast

from langchain_core.runnables import RunnableLambda
from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph

from common_agent.domain.workflow import WorkflowDefinition, WorkflowNodeType
from common_agent.knowledge.base import KnowledgeServiceError
from common_agent.models.base import ModelServiceError
from common_agent.workflows.errors import (
    WorkflowCompilationError,
    WorkflowCompilationFailed,
    WorkflowExecutionError,
    WorkflowExecutionFailed,
    WorkflowNodeNotRegistered,
    WorkflowStepLimitExceeded,
)
from common_agent.workflows.nodes.registry import WorkflowNodeRegistry
from common_agent.workflows.state import WorkflowExecutionResult, WorkflowGraphState
from common_agent.workflows.validator import MAX_WORKFLOW_NODES, ensure_workflow_graph_valid

MAX_WORKFLOW_STEPS = MAX_WORKFLOW_NODES + 2


class _CompiledGraph(Protocol):
    async def ainvoke(
        self,
        input: object,
        config: Mapping[str, object] | None = None,
    ) -> object: ...


@dataclass(frozen=True, slots=True)
class CompiledWorkflow:
    workflow_id: str
    _graph: _CompiledGraph
    _step_limit: int

    async def invoke(self, user_input: str) -> WorkflowExecutionResult:
        initial: WorkflowGraphState = {
            "input": user_input,
            "output": "",
            "knowledge": (),
            "completed_node_ids": (),
            "step_count": 0,
        }
        try:
            result = await self._graph.ainvoke(
                initial,
                {"recursion_limit": self._step_limit},
            )
        except GraphRecursionError:
            raise WorkflowStepLimitExceeded() from None
        except (ModelServiceError, KnowledgeServiceError, WorkflowExecutionError):
            raise
        except Exception:
            raise WorkflowExecutionFailed() from None
        return _execution_result(result)


class WorkflowCompiler:
    def __init__(
        self,
        registry: WorkflowNodeRegistry,
        *,
        step_limit: int = MAX_WORKFLOW_STEPS,
    ) -> None:
        if (
            not isinstance(step_limit, int)
            or isinstance(step_limit, bool)
            or not 1 <= step_limit <= MAX_WORKFLOW_STEPS
        ):
            raise ValueError(f"step_limit 必须是 1 到 {MAX_WORKFLOW_STEPS} 之间的整数")
        self._registry = registry
        self._step_limit = step_limit

    def compile(self, workflow: WorkflowDefinition) -> CompiledWorkflow:
        ensure_workflow_graph_valid(workflow.nodes, workflow.edges)
        graph = StateGraph(WorkflowGraphState)
        internal_ids = {
            node.id: f"platform_workflow_node_{position}"
            for position, node in enumerate(workflow.nodes)
        }
        start_node_id: str | None = None
        end_node_ids: list[str] = []
        try:
            for node in workflow.nodes:
                runner = self._registry.create(node)
                if runner is None:
                    raise WorkflowNodeNotRegistered(node.type)
                internal_id = internal_ids[node.id]
                graph.add_node(
                    internal_id,
                    RunnableLambda(runner),
                    metadata={"platform_node_id": node.id, "platform_node_type": node.type.value},
                )
                if node.type is WorkflowNodeType.START:
                    start_node_id = internal_id
                if node.type is WorkflowNodeType.END:
                    end_node_ids.append(internal_id)

            if start_node_id is None:
                raise WorkflowCompilationFailed()
            graph.add_edge(START, start_node_id)
            for edge in workflow.edges:
                graph.add_edge(internal_ids[edge.source], internal_ids[edge.target])
            for end_node_id in end_node_ids:
                graph.add_edge(end_node_id, END)
            compiled = cast(_CompiledGraph, graph.compile())
        except WorkflowCompilationError:
            raise
        except Exception:
            raise WorkflowCompilationFailed() from None
        return CompiledWorkflow(str(workflow.id), compiled, self._step_limit)


def _execution_result(result: object) -> WorkflowExecutionResult:
    if not isinstance(result, dict):
        raise WorkflowExecutionFailed()
    output = result.get("output")
    completed_node_ids = result.get("completed_node_ids")
    step_count = result.get("step_count")
    if (
        not isinstance(output, str)
        or not isinstance(completed_node_ids, tuple)
        or any(not isinstance(node_id, str) for node_id in completed_node_ids)
        or not isinstance(step_count, int)
        or isinstance(step_count, bool)
    ):
        raise WorkflowExecutionFailed()
    return WorkflowExecutionResult(
        output=output,
        completed_node_ids=completed_node_ids,
        step_count=step_count,
    )
