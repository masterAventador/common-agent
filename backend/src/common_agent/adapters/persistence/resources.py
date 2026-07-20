from __future__ import annotations

import json
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


class SqlAlchemyResourceDeletionStore:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def delete_employee(self, employee_id: UUID) -> LocalDeleteResult:
        async with self._database.session() as session:
            row = await session.get(EmployeeRow, str(employee_id))
            if row is None:
                return LocalDeleteResult(deleted=False)
            if await _exists(
                session,
                select(literal(1))
                .select_from(ConversationRow)
                .where(ConversationRow.employee_id == str(employee_id)),
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
        async with self._database.session() as session:
            employee_binding = await _exists(
                session,
                select(literal(1))
                .select_from(EmployeeRow)
                .where(EmployeeRow.knowledge_base_id == knowledge_base_id),
            )
            workflow_node = await _exists(
                session,
                select(literal(1))
                .select_from(WorkflowNodeRow)
                .where(
                    func.json_unquote(
                        func.json_extract(WorkflowNodeRow.config, "$.knowledge_base_id")
                    )
                    == knowledge_base_id
                ),
            )
        return KnowledgeBaseReferences(
            employee_bindings=int(employee_binding),
            workflow_nodes=int(workflow_node),
        )

    async def get_workflow_references(self, workflow_id: UUID) -> WorkflowReferences:
        async with self._database.session() as session:
            return await _workflow_references(session, workflow_id)

    async def delete_workflow(self, workflow_id: UUID) -> LocalDeleteResult:
        async with self._database.session() as session:
            row = await session.get(WorkflowRow, str(workflow_id))
            if row is None:
                return LocalDeleteResult(deleted=False)
            references = await _workflow_references(session, workflow_id)
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
                    delete(WorkflowRow).where(WorkflowRow.id == str(workflow_id))
                ),
            )
            await session.commit()
        return LocalDeleteResult(deleted=bool(result.rowcount))


async def _workflow_references(session: Any, workflow_id: UUID) -> WorkflowReferences:
    employee_binding = await _exists(
        session,
        select(literal(1))
        .select_from(EmployeeRow)
        .where(
            func.json_contains(
                EmployeeRow.allowed_workflow_ids,
                json.dumps(str(workflow_id)),
            )
            == 1
        ),
    )
    active_run = await _exists(
        session,
        select(literal(1))
        .select_from(WorkflowRunRow)
        .where(
            WorkflowRunRow.workflow_id == str(workflow_id),
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
