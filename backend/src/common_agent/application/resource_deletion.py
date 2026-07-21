from __future__ import annotations

from uuid import UUID

from common_agent.application.resource_locks import (
    ResourceMutationGuard,
    employee_resource,
    knowledge_base_resource,
    workflow_resource,
)
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.resources import LocalDeleteBlock, ResourceDeletionStore


class ResourceDeletionError(Exception):
    code: str
    message: str
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


class EmployeeHasConversations(ResourceDeletionError):
    code = "employee_in_use_by_conversations"
    message = "数字员工仍被会话引用。请先删除相关会话"


class EmployeeHasWorkflowTargets(ResourceDeletionError):
    code = "employee_in_use_by_workflows"
    message = "数字员工仍被工作流 AI 对话节点引用。请先修改相关工作流"


class KnowledgeBaseHasEmployeeBindings(ResourceDeletionError):
    code = "knowledge_base_in_use_by_employees"
    message = "知识库仍被数字员工绑定。请先解除绑定"


class KnowledgeBaseHasWorkflowReferences(ResourceDeletionError):
    code = "knowledge_base_in_use_by_workflows"
    message = "知识库仍被工作流节点引用。请先修改相关工作流"


class WorkflowHasEmployeeBindings(ResourceDeletionError):
    code = "workflow_in_use_by_employees"
    message = "工作流仍在数字员工允许列表中。请先解除绑定"


class WorkflowHasActiveRuns(ResourceDeletionError):
    code = "workflow_has_active_runs"
    message = "工作流仍有运行中的执行。请等待完成或停止后重试"
    retryable = True


class ResourceDeletionService:
    def __init__(
        self,
        store: ResourceDeletionStore,
        knowledge_bases: KnowledgeBaseService,
        *,
        guard: ResourceMutationGuard,
    ) -> None:
        self._store = store
        self._knowledge_bases = knowledge_bases
        self._guard = guard

    async def delete_employee(self, employee_id: UUID) -> bool:
        async with self._guard.hold(employee_resource(employee_id)):
            result = await self._store.delete_employee(employee_id)
        if result.blocked_by is LocalDeleteBlock.EMPLOYEE_CONVERSATIONS:
            raise EmployeeHasConversations
        if result.blocked_by is LocalDeleteBlock.EMPLOYEE_WORKFLOW_TARGETS:
            raise EmployeeHasWorkflowTargets
        return result.deleted

    async def delete_knowledge_base(self, knowledge_base_id: str) -> bool:
        async with self._guard.hold(knowledge_base_resource(knowledge_base_id)):
            try:
                await self._knowledge_bases.get_knowledge_base(knowledge_base_id)
            except KnowledgeBaseNotFound:
                return False
            references = await self._store.get_knowledge_base_references(knowledge_base_id)
            if references.employee_bindings:
                raise KnowledgeBaseHasEmployeeBindings
            if references.workflow_nodes:
                raise KnowledgeBaseHasWorkflowReferences
            try:
                await self._knowledge_bases.delete_knowledge_base(knowledge_base_id)
            except KnowledgeBaseNotFound:
                return False
        return True

    async def delete_workflow(self, workflow_id: UUID) -> bool:
        async with self._guard.hold(workflow_resource(workflow_id)):
            references = await self._store.get_workflow_references(workflow_id)
            if references.employee_bindings:
                raise WorkflowHasEmployeeBindings
            if references.active_runs:
                raise WorkflowHasActiveRuns
            result = await self._store.delete_workflow(workflow_id)
        if result.blocked_by is LocalDeleteBlock.WORKFLOW_EMPLOYEES:
            raise WorkflowHasEmployeeBindings
        if result.blocked_by is LocalDeleteBlock.WORKFLOW_ACTIVE_RUNS:
            raise WorkflowHasActiveRuns
        return result.deleted


__all__ = [
    "EmployeeHasConversations",
    "EmployeeHasWorkflowTargets",
    "KnowledgeBaseHasEmployeeBindings",
    "KnowledgeBaseHasWorkflowReferences",
    "ResourceDeletionError",
    "ResourceDeletionService",
    "WorkflowHasActiveRuns",
    "WorkflowHasEmployeeBindings",
]
