from __future__ import annotations

from typing import TypedDict

from common_agent.runtimes.base import RuntimeKnowledgeChunk
from common_agent.workflows.execution import (
    WorkflowExecutionObserver,
    WorkflowExecutionStopSignal,
)


class WorkflowGraphState(TypedDict, total=False):
    input: str
    output: str
    knowledge: tuple[RuntimeKnowledgeChunk, ...]
    current_node_id: str
    completed_node_ids: tuple[str, ...]
    step_count: int


class WorkflowGraphContext(TypedDict):
    observer: WorkflowExecutionObserver
    stop: WorkflowExecutionStopSignal


type WorkflowGraphUpdate = WorkflowGraphState
