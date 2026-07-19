from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from common_agent.runtimes.base import RuntimeKnowledgeChunk


class WorkflowGraphState(TypedDict, total=False):
    input: str
    output: str
    knowledge: tuple[RuntimeKnowledgeChunk, ...]
    current_node_id: str
    completed_node_ids: tuple[str, ...]
    step_count: int


type WorkflowStateUpdate = WorkflowGraphState


@dataclass(frozen=True, slots=True)
class WorkflowExecutionResult:
    output: str = field(repr=False)
    completed_node_ids: tuple[str, ...]
    step_count: int
