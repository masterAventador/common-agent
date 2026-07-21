from __future__ import annotations

import asyncio
from collections.abc import Mapping
from contextlib import suppress
from dataclasses import dataclass
from typing import Protocol, cast
from uuid import UUID

from langgraph.errors import GraphRecursionError
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime

from common_agent.adapters.workflow.langgraph.state import (
    WorkflowGraphContext,
    WorkflowGraphState,
    WorkflowGraphUpdate,
)
from common_agent.domain.workflow import WorkflowDefinition, WorkflowNodeType
from common_agent.domain.workflow_run import WorkflowAiTargetSummary
from common_agent.knowledge.base import KnowledgeServiceError
from common_agent.models.base import ModelServiceError
from common_agent.workflows.errors import (
    WorkflowCompilationError,
    WorkflowCompilationFailed,
    WorkflowExecutionError,
    WorkflowExecutionFailed,
    WorkflowExecutionStopped,
    WorkflowNodeNotRegistered,
    WorkflowStepLimitExceeded,
)
from common_agent.workflows.execution import (
    WorkflowExecutionObserver,
    WorkflowExecutionResult,
    WorkflowExecutionStopSignal,
    WorkflowNodeExecutionContext,
    WorkflowNodeExecutionResult,
)
from common_agent.workflows.nodes.registry import WorkflowNodeRegistry, WorkflowNodeRunner
from common_agent.workflows.validator import MAX_WORKFLOW_NODES, ensure_workflow_graph_valid

MAX_WORKFLOW_STEPS = MAX_WORKFLOW_NODES + 2


class _CompiledGraph(Protocol):
    async def ainvoke(
        self,
        input: object,
        config: Mapping[str, object] | None = None,
        *,
        context: object | None = None,
    ) -> object: ...


class _NoopObserver:
    async def node_started(self, node_id: str) -> None:
        del node_id

    async def node_completed(self, node_id: str) -> None:
        del node_id

    async def ai_target_resolved(self, summary: WorkflowAiTargetSummary) -> None:
        del summary


class _NeverStop:
    @property
    def is_requested(self) -> bool:
        return False

    async def wait(self) -> None:
        await asyncio.Event().wait()


@dataclass(frozen=True, slots=True)
class _ObservedNode:
    node_id: str
    runner: WorkflowNodeRunner

    async def __call__(
        self,
        state: WorkflowGraphState,
        *,
        runtime: Runtime[WorkflowGraphContext],
    ) -> WorkflowGraphUpdate:
        observer = runtime.context["observer"]
        stop = runtime.context["stop"]
        if stop.is_requested:
            raise WorkflowExecutionStopped()
        await observer.node_started(self.node_id)
        if stop.is_requested:
            raise WorkflowExecutionStopped()

        runner_task: asyncio.Future[WorkflowNodeExecutionResult] = asyncio.ensure_future(
            self.runner(_node_context(state, self.node_id, runtime.context))
        )
        stop_task = asyncio.create_task(stop.wait())
        try:
            waiters = {
                cast(asyncio.Future[object], runner_task),
                cast(asyncio.Future[object], stop_task),
            }
            done, _ = await asyncio.wait(
                waiters,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if stop_task in done or stop.is_requested:
                await _discard_task(runner_task)
                raise WorkflowExecutionStopped()
            await _discard_task(stop_task)
            update = _node_update(state, self.node_id, runner_task.result())
            await observer.node_completed(self.node_id)
            return update
        finally:
            await _discard_task(runner_task)
            await _discard_task(stop_task)


@dataclass(frozen=True, slots=True)
class _LangGraphCompiledWorkflow:
    workflow_id: str
    _graph: _CompiledGraph
    _step_limit: int

    async def invoke(
        self,
        user_input: str,
        *,
        observer: WorkflowExecutionObserver | None = None,
        stop: WorkflowExecutionStopSignal | None = None,
        run_id: UUID | None = None,
    ) -> WorkflowExecutionResult:
        if not isinstance(user_input, str) or not user_input.strip():
            raise WorkflowExecutionFailed()
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
                context={
                    "observer": observer or _NoopObserver(),
                    "stop": stop or _NeverStop(),
                    "run_id": run_id,
                },
            )
        except GraphRecursionError:
            raise WorkflowStepLimitExceeded() from None
        except (ModelServiceError, KnowledgeServiceError, WorkflowExecutionError):
            raise
        except Exception:
            raise WorkflowExecutionFailed() from None
        return _execution_result(result)


class LangGraphWorkflowCompiler:
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

    def compile(self, workflow: WorkflowDefinition) -> _LangGraphCompiledWorkflow:
        ensure_workflow_graph_valid(workflow.nodes, workflow.edges)
        graph = StateGraph(WorkflowGraphState, context_schema=WorkflowGraphContext)
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
                    _ObservedNode(node.id, runner),
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
        return _LangGraphCompiledWorkflow(str(workflow.id), compiled, self._step_limit)


async def _discard_task[Result](task: asyncio.Future[Result]) -> None:
    if not task.done():
        task.cancel()
    with suppress(asyncio.CancelledError, Exception):
        await task


def _node_context(
    state: WorkflowGraphState,
    node_id: str,
    context: WorkflowGraphContext,
) -> WorkflowNodeExecutionContext:
    try:
        return WorkflowNodeExecutionContext(
            user_input=state["input"],
            output=state.get("output", ""),
            knowledge=state.get("knowledge", ()),
            node_id=node_id,
            run_id=context["run_id"],
            observer=context["observer"],
            stop=context["stop"],
        )
    except (KeyError, TypeError, ValueError):
        raise WorkflowExecutionFailed() from None


def _node_update(
    state: WorkflowGraphState,
    node_id: str,
    result: WorkflowNodeExecutionResult,
) -> WorkflowGraphUpdate:
    if not isinstance(result, WorkflowNodeExecutionResult):
        raise WorkflowExecutionFailed()
    completed_node_ids = state.get("completed_node_ids", ())
    step_count = state.get("step_count", 0)
    if (
        not isinstance(completed_node_ids, tuple)
        or any(not isinstance(completed, str) for completed in completed_node_ids)
        or not isinstance(step_count, int)
        or isinstance(step_count, bool)
        or step_count != len(completed_node_ids)
        or node_id in completed_node_ids
    ):
        raise WorkflowExecutionFailed()
    update: WorkflowGraphUpdate = {
        "current_node_id": node_id,
        "completed_node_ids": (*completed_node_ids, node_id),
        "step_count": step_count + 1,
    }
    if result.output is not None:
        update["output"] = result.output
    if result.knowledge is not None:
        update["knowledge"] = result.knowledge
    return update


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
    try:
        return WorkflowExecutionResult(
            output=output,
            completed_node_ids=completed_node_ids,
            step_count=step_count,
        )
    except (TypeError, ValueError):
        raise WorkflowExecutionFailed() from None
