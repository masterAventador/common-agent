from __future__ import annotations

import builtins
from collections import defaultdict
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    WorkflowEdgeRow,
    WorkflowNodeRow,
    WorkflowRow,
    WorkflowRunRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    StartNodeConfig,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeConfig,
    WorkflowNodePosition,
    WorkflowNodeType,
    WorkflowValidationError,
)
from common_agent.domain.workflow_run import (
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunTrigger,
    WorkflowRunValidationError,
)
from common_agent.ports.workflows import (
    WorkflowAlreadyExists,
    WorkflowRepository,
    WorkflowRunAlreadyExists,
    WorkflowRunRepository,
)


class SqlAlchemyWorkflowRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> tuple[WorkflowDefinition, ...]:
        rows = tuple(
            await self._session.scalars(
                select(WorkflowRow).order_by(WorkflowRow.created_at, WorkflowRow.id)
            )
        )
        if not rows:
            return ()
        node_rows, edge_rows = await self._load_graph_rows(tuple(row.id for row in rows))
        return tuple(_to_domain(row, node_rows[row.id], edge_rows[row.id]) for row in rows)

    async def get(self, workflow_id: UUID) -> WorkflowDefinition | None:
        row = await self._session.get(WorkflowRow, str(workflow_id))
        if row is None:
            return None
        node_rows, edge_rows = await self._load_graph_rows((row.id,))
        return _to_domain(row, node_rows[row.id], edge_rows[row.id])

    async def add(self, workflow: WorkflowDefinition) -> None:
        self._session.add(WorkflowRow(**_workflow_values(workflow)))
        try:
            await self._session.flush()
        except IntegrityError:
            raise WorkflowAlreadyExists from None
        self._session.add_all(_node_rows(workflow))
        await self._session.flush()
        self._session.add_all(_edge_rows(workflow))
        await self._session.flush()

    async def update(self, workflow: WorkflowDefinition) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(WorkflowRow)
                .where(WorkflowRow.id == str(workflow.id))
                .values(
                    name=workflow.name,
                    description=workflow.description,
                    updated_at=to_database_datetime(workflow.updated_at),
                )
            ),
        )
        if not result.rowcount:
            return False

        workflow_id = str(workflow.id)
        await self._session.execute(
            delete(WorkflowEdgeRow).where(WorkflowEdgeRow.workflow_id == workflow_id)
        )
        await self._session.execute(
            delete(WorkflowNodeRow).where(WorkflowNodeRow.workflow_id == workflow_id)
        )
        self._session.add_all(_node_rows(workflow))
        await self._session.flush()
        self._session.add_all(_edge_rows(workflow))
        await self._session.flush()
        return True

    async def _load_graph_rows(
        self,
        workflow_ids: tuple[str, ...],
    ) -> tuple[
        dict[str, builtins.list[WorkflowNodeRow]],
        dict[str, builtins.list[WorkflowEdgeRow]],
    ]:
        nodes: defaultdict[str, builtins.list[WorkflowNodeRow]] = defaultdict(list)
        edges: defaultdict[str, builtins.list[WorkflowEdgeRow]] = defaultdict(list)
        node_result = await self._session.scalars(
            select(WorkflowNodeRow)
            .where(WorkflowNodeRow.workflow_id.in_(workflow_ids))
            .order_by(WorkflowNodeRow.workflow_id, WorkflowNodeRow.ordinal)
        )
        for node_row in node_result:
            nodes[node_row.workflow_id].append(node_row)
        edge_result = await self._session.scalars(
            select(WorkflowEdgeRow)
            .where(WorkflowEdgeRow.workflow_id.in_(workflow_ids))
            .order_by(WorkflowEdgeRow.workflow_id, WorkflowEdgeRow.ordinal)
        )
        for edge_row in edge_result:
            edges[edge_row.workflow_id].append(edge_row)
        return dict(nodes), dict(edges)


class SqlAlchemyWorkflowRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, run_id: UUID) -> WorkflowRun | None:
        row = await self._session.get(WorkflowRunRow, str(run_id))
        return None if row is None else _run_to_domain(row)

    async def list_active(self) -> tuple[WorkflowRun, ...]:
        rows = await self._session.scalars(
            select(WorkflowRunRow)
            .where(
                WorkflowRunRow.status.in_(
                    (WorkflowRunStatus.PENDING.value, WorkflowRunStatus.RUNNING.value)
                )
            )
            .order_by(WorkflowRunRow.created_at, WorkflowRunRow.id)
        )
        return tuple(_run_to_domain(row) for row in rows)

    async def add(self, run: WorkflowRun) -> None:
        self._session.add(WorkflowRunRow(**_run_values(run)))
        try:
            await self._session.flush()
        except IntegrityError:
            raise WorkflowRunAlreadyExists from None

    async def update(self, run: WorkflowRun) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(WorkflowRunRow)
                .where(WorkflowRunRow.id == str(run.id))
                .values(
                    status=run.status.value,
                    output=run.output,
                    current_node_id=run.current_node_id,
                    completed_node_ids=list(run.completed_node_ids),
                    failed_node_id=run.failed_node_id,
                    error_code=run.error_code,
                    started_at=(
                        None if run.started_at is None else to_database_datetime(run.started_at)
                    ),
                    finished_at=(
                        None if run.finished_at is None else to_database_datetime(run.finished_at)
                    ),
                    updated_at=to_database_datetime(run.updated_at),
                )
            ),
        )
        return bool(result.rowcount)


class SqlAlchemyWorkflowUnitOfWork:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._workflows: WorkflowRepository | None = None
        self._workflow_runs: WorkflowRunRepository | None = None

    @property
    def workflows(self) -> WorkflowRepository:
        if self._workflows is None:
            raise RuntimeError("工作流事务尚未开始")
        return self._workflows

    @property
    def workflow_runs(self) -> WorkflowRunRepository:
        if self._workflow_runs is None:
            raise RuntimeError("工作流事务尚未开始")
        return self._workflow_runs

    async def __aenter__(self) -> SqlAlchemyWorkflowUnitOfWork:
        if self._context is not None:
            raise RuntimeError("工作流事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._workflows = SqlAlchemyWorkflowRepository(session)
        self._workflow_runs = SqlAlchemyWorkflowRunRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._context
        self._context = None
        self._session = None
        self._workflows = None
        self._workflow_runs = None
        if context is None:
            raise RuntimeError("工作流事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        session = self._session
        if session is None:
            raise RuntimeError("工作流事务尚未开始")
        await session.commit()


class SqlAlchemyWorkflowUnitOfWorkFactory:
    def __init__(self, database: Database) -> None:
        self._database = database

    def __call__(self) -> SqlAlchemyWorkflowUnitOfWork:
        return SqlAlchemyWorkflowUnitOfWork(self._database)


def _workflow_values(workflow: WorkflowDefinition) -> dict[str, object]:
    return {
        "id": str(workflow.id),
        "name": workflow.name,
        "description": workflow.description,
        "created_at": to_database_datetime(workflow.created_at),
        "updated_at": to_database_datetime(workflow.updated_at),
    }


def _run_values(run: WorkflowRun) -> dict[str, object]:
    return {
        "id": str(run.id),
        "workflow_id": str(run.workflow_id),
        "trigger": run.trigger.value,
        "status": run.status.value,
        "input": run.input,
        "output": run.output,
        "current_node_id": run.current_node_id,
        "completed_node_ids": list(run.completed_node_ids),
        "failed_node_id": run.failed_node_id,
        "error_code": run.error_code,
        "created_at": to_database_datetime(run.created_at),
        "started_at": None if run.started_at is None else to_database_datetime(run.started_at),
        "finished_at": (None if run.finished_at is None else to_database_datetime(run.finished_at)),
        "updated_at": to_database_datetime(run.updated_at),
    }


def _node_rows(workflow: WorkflowDefinition) -> list[WorkflowNodeRow]:
    workflow_id = str(workflow.id)
    return [
        WorkflowNodeRow(
            workflow_id=workflow_id,
            id=node.id,
            ordinal=ordinal,
            type=node.type.value,
            position_x=node.position.x,
            position_y=node.position.y,
            config=_config_values(node.config),
        )
        for ordinal, node in enumerate(workflow.nodes)
    ]


def _edge_rows(workflow: WorkflowDefinition) -> list[WorkflowEdgeRow]:
    workflow_id = str(workflow.id)
    return [
        WorkflowEdgeRow(
            workflow_id=workflow_id,
            id=edge.id,
            ordinal=ordinal,
            source=edge.source,
            target=edge.target,
        )
        for ordinal, edge in enumerate(workflow.edges)
    ]


def _config_values(config: WorkflowNodeConfig) -> dict[str, object]:
    if isinstance(config, AiChatNodeConfig):
        return {"prompt": config.prompt}
    if isinstance(config, KnowledgeRetrievalNodeConfig):
        return {"knowledge_base_id": config.knowledge_base_id}
    return {}


def _to_domain(
    workflow: WorkflowRow,
    nodes: list[WorkflowNodeRow],
    edges: list[WorkflowEdgeRow],
) -> WorkflowDefinition:
    return WorkflowDefinition(
        id=UUID(workflow.id),
        name=workflow.name,
        description=workflow.description,
        nodes=tuple(_node_to_domain(node) for node in nodes),
        edges=tuple(
            WorkflowEdge(id=edge.id, source=edge.source, target=edge.target) for edge in edges
        ),
        created_at=from_database_datetime(workflow.created_at),
        updated_at=from_database_datetime(workflow.updated_at),
    )


def _run_to_domain(row: WorkflowRunRow) -> WorkflowRun:
    try:
        trigger = WorkflowRunTrigger(row.trigger)
        status = WorkflowRunStatus(row.status)
    except ValueError:
        raise WorkflowRunValidationError("status", "持久化运行枚举无法识别") from None
    return WorkflowRun(
        id=UUID(row.id),
        workflow_id=UUID(row.workflow_id),
        trigger=trigger,
        status=status,
        input=row.input,
        output=row.output,
        current_node_id=row.current_node_id,
        completed_node_ids=tuple(row.completed_node_ids),
        failed_node_id=row.failed_node_id,
        error_code=row.error_code,
        created_at=from_database_datetime(row.created_at),
        started_at=(None if row.started_at is None else from_database_datetime(row.started_at)),
        finished_at=(None if row.finished_at is None else from_database_datetime(row.finished_at)),
        updated_at=from_database_datetime(row.updated_at),
    )


def _node_to_domain(row: WorkflowNodeRow) -> WorkflowNode:
    try:
        node_type = WorkflowNodeType(row.type)
    except ValueError:
        raise WorkflowValidationError("type", "持久化节点类型无法识别") from None
    return WorkflowNode(
        id=row.id,
        type=node_type,
        position=WorkflowNodePosition(x=row.position_x, y=row.position_y),
        config=_config_from_values(node_type, row.config),
    )


def _config_from_values(
    node_type: WorkflowNodeType,
    values: dict[str, object],
) -> WorkflowNodeConfig:
    if node_type in {WorkflowNodeType.START, WorkflowNodeType.END}:
        if values:
            raise WorkflowValidationError("config", "开始或结束节点配置必须为空")
        return StartNodeConfig() if node_type is WorkflowNodeType.START else EndNodeConfig()
    if node_type is WorkflowNodeType.AI_CHAT:
        if set(values) != {"prompt"}:
            raise WorkflowValidationError("config", "AI 对话节点配置字段不合法")
        return AiChatNodeConfig(prompt=values["prompt"])  # type: ignore[arg-type]
    if set(values) != {"knowledge_base_id"}:
        raise WorkflowValidationError("config", "知识检索节点配置字段不合法")
    return KnowledgeRetrievalNodeConfig(
        knowledge_base_id=values["knowledge_base_id"]  # type: ignore[arg-type]
    )
