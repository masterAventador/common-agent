from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, func, literal, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ConversationRow,
    EmployeeRow,
    WorkflowNodeRow,
    WorkflowRow,
    WorkflowRunRow,
)
from common_agent.domain.workflow_run import WorkflowRunStatus
from common_agent.ports.resources import (
    KnowledgeBaseReferences,
    LocalDeleteBlock,
    LocalDeleteResult,
    WorkflowReferences,
)
from common_agent.tenancy.context import current_tenant


class SqlAlchemyResourceDeletionStore:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    async def delete_employee(self, employee_id: UUID) -> LocalDeleteResult:
        tenant_id = str(self._tenant_id_provider())
        async with self._database.session() as session:
            row = await session.scalar(
                select(EmployeeRow).where(
                    EmployeeRow.id == str(employee_id),
                    EmployeeRow.tenant_id == tenant_id,
                )
            )
            if row is None:
                return LocalDeleteResult(deleted=False)
            if await _exists(
                session,
                select(literal(1))
                .select_from(ConversationRow)
                .where(
                    ConversationRow.employee_id == str(employee_id),
                    ConversationRow.tenant_id == tenant_id,
                ),
            ):
                return LocalDeleteResult(
                    deleted=False,
                    blocked_by=LocalDeleteBlock.EMPLOYEE_CONVERSATIONS,
                )
            try:
                await session.delete(row)
                await session.commit()
            except IntegrityError:
                await session.rollback()
                return LocalDeleteResult(
                    deleted=False,
                    blocked_by=LocalDeleteBlock.EMPLOYEE_CONVERSATIONS,
                )
        return LocalDeleteResult(deleted=True)

    async def get_knowledge_base_references(
        self, knowledge_base_id: str
    ) -> KnowledgeBaseReferences:
        tenant_id = str(self._tenant_id_provider())
        async with self._database.session() as session:
            employee_binding = await _exists(
                session,
                select(literal(1))
                .select_from(EmployeeRow)
                .where(
                    EmployeeRow.knowledge_base_id == knowledge_base_id,
                    EmployeeRow.tenant_id == tenant_id,
                ),
            )
            workflow_node = await _exists(
                session,
                select(literal(1))
                .select_from(WorkflowNodeRow)
                .join(WorkflowRow, WorkflowRow.id == WorkflowNodeRow.workflow_id)
                .where(
                    WorkflowRow.tenant_id == tenant_id,
                    func.json_unquote(
                        func.json_extract(WorkflowNodeRow.config, "$.knowledge_base_id")
                    )
                    == knowledge_base_id,
                ),
            )
        return KnowledgeBaseReferences(
            employee_bindings=int(employee_binding),
            workflow_nodes=int(workflow_node),
        )

    async def get_workflow_references(self, workflow_id: UUID) -> WorkflowReferences:
        tenant_id = str(self._tenant_id_provider())
        async with self._database.session() as session:
            return await _workflow_references(session, workflow_id, tenant_id)

    async def delete_workflow(self, workflow_id: UUID) -> LocalDeleteResult:
        tenant_id = str(self._tenant_id_provider())
        async with self._database.session() as session:
            row = await session.scalar(
                select(WorkflowRow).where(
                    WorkflowRow.id == str(workflow_id),
                    WorkflowRow.tenant_id == tenant_id,
                )
            )
            if row is None:
                return LocalDeleteResult(deleted=False)
            references = await _workflow_references(session, workflow_id, tenant_id)
            if references.employee_bindings:
                return LocalDeleteResult(
                    deleted=False,
                    blocked_by=LocalDeleteBlock.WORKFLOW_EMPLOYEES,
                )
            if references.active_runs:
                return LocalDeleteResult(
                    deleted=False,
                    blocked_by=LocalDeleteBlock.WORKFLOW_ACTIVE_RUNS,
                )
            result = cast(
                CursorResult[Any],
                await session.execute(
                    delete(WorkflowRow).where(
                        WorkflowRow.id == str(workflow_id),
                        WorkflowRow.tenant_id == tenant_id,
                    )
                ),
            )
            await session.commit()
        return LocalDeleteResult(deleted=bool(result.rowcount))


async def _workflow_references(
    session: Any,
    workflow_id: UUID,
    tenant_id: str,
) -> WorkflowReferences:
    employee_binding = await _exists(
        session,
        select(literal(1))
        .select_from(EmployeeRow)
        .where(
            EmployeeRow.tenant_id == tenant_id,
            func.json_contains(
                EmployeeRow.allowed_workflow_ids,
                json.dumps(str(workflow_id)),
            )
            == 1,
        ),
    )
    active_run = await _exists(
        session,
        select(literal(1))
        .select_from(WorkflowRunRow)
        .where(
            WorkflowRunRow.workflow_id == str(workflow_id),
            WorkflowRunRow.tenant_id == tenant_id,
            WorkflowRunRow.status.in_(
                (WorkflowRunStatus.PENDING.value, WorkflowRunStatus.RUNNING.value)
            ),
        ),
    )
    return WorkflowReferences(
        employee_bindings=int(employee_binding),
        active_runs=int(active_run),
    )


async def _exists(session: Any, statement: Any) -> bool:
    return (await session.scalar(statement.limit(1))) is not None


__all__ = ["SqlAlchemyResourceDeletionStore"]
