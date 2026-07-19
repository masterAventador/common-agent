from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, TypedDict

from common_agent.runtimes.base import RuntimeKnowledgeChunk, RuntimeStopSignal


class WorkflowGraphState(TypedDict, total=False):
    input: str
    output: str
    knowledge: tuple[RuntimeKnowledgeChunk, ...]
    current_node_id: str
    completed_node_ids: tuple[str, ...]
    step_count: int


type WorkflowStateUpdate = WorkflowGraphState


class WorkflowExecutionObserver(Protocol):
    async def node_started(self, node_id: str) -> None: ...

    async def node_completed(self, node_id: str) -> None: ...


class WorkflowGraphContext(TypedDict):
    observer: WorkflowExecutionObserver
    stop: RuntimeStopSignal


@dataclass(frozen=True, slots=True)
class WorkflowExecutionResult:
    output: str = field(repr=False)
    completed_node_ids: tuple[str, ...]
    step_count: int
