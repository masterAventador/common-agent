from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol
from uuid import UUID


class LocalDeleteBlock(StrEnum):
    EMPLOYEE_CONVERSATIONS = "employee_conversations"
    EMPLOYEE_WORKFLOW_TARGETS = "employee_workflow_targets"
    WORKFLOW_EMPLOYEES = "workflow_employees"
    WORKFLOW_ACTIVE_RUNS = "workflow_active_runs"


@dataclass(frozen=True, slots=True)
class LocalDeleteResult:
    deleted: bool
    blocked_by: LocalDeleteBlock | None = None

    def __post_init__(self) -> None:
        if self.deleted and self.blocked_by is not None:
            raise ValueError("已删除结果不能同时包含引用阻断")


@dataclass(frozen=True, slots=True)
class KnowledgeBaseReferences:
    employee_bindings: int = 0
    workflow_nodes: int = 0


@dataclass(frozen=True, slots=True)
class WorkflowReferences:
    employee_bindings: int = 0
    active_runs: int = 0


class ResourceDeletionStore(Protocol):
    async def delete_employee(self, employee_id: UUID) -> LocalDeleteResult: ...

    async def get_knowledge_base_references(
        self, knowledge_base_id: str
    ) -> KnowledgeBaseReferences: ...

    async def get_workflow_references(self, workflow_id: UUID) -> WorkflowReferences: ...

    async def delete_workflow(self, workflow_id: UUID) -> LocalDeleteResult: ...


__all__ = [
    "KnowledgeBaseReferences",
    "LocalDeleteBlock",
    "LocalDeleteResult",
    "ResourceDeletionStore",
    "WorkflowReferences",
]
