from __future__ import annotations

import builtins
from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ModelConfigurationReferenceRow,
    WorkflowAiChatTargetRow,
    WorkflowEdgeRow,
    WorkflowNodeRow,
    WorkflowRow,
    WorkflowRunRow,
)
from common_agent.adapters.persistence.tasks import SqlAlchemyTaskSubmission
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    AiChatTarget,
    EmployeeAiChatTarget,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    ModelAiChatTarget,
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
    WorkflowAiTargetSummary,
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunStatus,
    WorkflowRunTrigger,
    WorkflowRunValidationError,
)
from common_agent.pagination import PageAnchor, PageSlice, canonical_uuid_search
from common_agent.ports.workflows import (
    WorkflowAlreadyExists,
    WorkflowRepository,
    WorkflowRunAlreadyExists,
    WorkflowRunRepository,
)
from common_agent.tasks import TaskSubmission
from common_agent.tenancy.context import current_tenant


class SqlAlchemyWorkflowRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self._session = session
        self._tenant_id = str(tenant_id or current_tenant().tenant_id)

    async def list(self) -> tuple[WorkflowDefinition, ...]:
        rows = tuple(
            await self._session.scalars(
                select(WorkflowRow)
                .where(WorkflowRow.tenant_id == self._tenant_id)
                .order_by(WorkflowRow.created_at, WorkflowRow.id)
            )
        )
        if not rows:
            return ()
        node_rows, edge_rows = await self._load_graph_rows(tuple(row.id for row in rows))
        return tuple(_to_domain(row, node_rows[row.id], edge_rows[row.id]) for row in rows)

    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
    ) -> PageSlice[WorkflowDefinition]:
        statement = select(WorkflowRow).where(WorkflowRow.tenant_id == self._tenant_id)
        if search:
            searched_id = canonical_uuid_search(search)
            statement = statement.where(
                WorkflowRow.id == searched_id
                if searched_id is not None
                else WorkflowRow.name.startswith(search, autoescape=True)
            )
        if after is not None:
            after_time = to_database_datetime(after.created_at)
            statement = statement.where(
                or_(
                    WorkflowRow.created_at < after_time,
                    and_(
                        WorkflowRow.created_at == after_time,
                        WorkflowRow.id < after.id,
                    ),
                )
            )
        rows = tuple(
            await self._session.scalars(
                statement.order_by(
                    WorkflowRow.created_at.desc(),
                    WorkflowRow.id.desc(),
                ).limit(limit + 1)
            )
        )
        visible_rows = rows[:limit]
        if not visible_rows:
            return PageSlice(items=(), has_more=False)
        node_rows, edge_rows = await self._load_graph_rows(tuple(row.id for row in visible_rows))
        return PageSlice(
            items=tuple(
                _to_domain(row, node_rows[row.id], edge_rows[row.id]) for row in visible_rows
            ),
            has_more=len(rows) > limit,
        )

    async def get(self, workflow_id: UUID) -> WorkflowDefinition | None:
        row = await self._session.scalar(
            select(WorkflowRow).where(
                WorkflowRow.id == str(workflow_id),
                WorkflowRow.tenant_id == self._tenant_id,
            )
        )
        if row is None:
            return None
        node_rows, edge_rows = await self._load_graph_rows((row.id,))
        return _to_domain(row, node_rows[row.id], edge_rows[row.id])

    async def existing_ids(self, workflow_ids: tuple[UUID, ...]) -> frozenset[UUID]:
        if not workflow_ids:
            return frozenset()
        values = await self._session.scalars(
            select(WorkflowRow.id).where(
                WorkflowRow.id.in_(tuple(str(workflow_id) for workflow_id in workflow_ids)),
                WorkflowRow.tenant_id == self._tenant_id,
            )
        )
        return frozenset(UUID(value) for value in values)

    async def add(self, workflow: WorkflowDefinition) -> None:
        self._session.add(WorkflowRow(tenant_id=self._tenant_id, **_workflow_values(workflow)))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _mysql_error_code(error) == 1062:
                raise WorkflowAlreadyExists from None
            raise
        self._session.add_all(_node_rows(workflow))
        await self._session.flush()
        self._session.add_all(_target_rows(workflow, self._tenant_id))
        self._session.add_all(_model_reference_rows(workflow, self._tenant_id))
        await self._session.flush()
        self._session.add_all(_edge_rows(workflow))
        await self._session.flush()

    async def update(self, workflow: WorkflowDefinition) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(WorkflowRow)
                .where(
                    WorkflowRow.id == str(workflow.id),
                    WorkflowRow.tenant_id == self._tenant_id,
                )
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
        await self._session.execute(
            delete(ModelConfigurationReferenceRow).where(
                ModelConfigurationReferenceRow.tenant_id == self._tenant_id,
                ModelConfigurationReferenceRow.resource_type == "workflow",
                ModelConfigurationReferenceRow.resource_id == workflow_id,
            )
        )
        self._session.add_all(_node_rows(workflow))
        await self._session.flush()
        self._session.add_all(_target_rows(workflow, self._tenant_id))
        self._session.add_all(_model_reference_rows(workflow, self._tenant_id))
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
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self._session = session
        self._tenant_id = str(tenant_id or current_tenant().tenant_id)

    async def get(self, run_id: UUID) -> WorkflowRun | None:
        row = await self._session.scalar(
            select(WorkflowRunRow).where(
                WorkflowRunRow.id == str(run_id),
                WorkflowRunRow.tenant_id == self._tenant_id,
            )
        )
        return None if row is None else _run_to_domain(row)

    async def list_active(self) -> tuple[WorkflowRun, ...]:
        rows = await self._session.scalars(
            select(WorkflowRunRow)
            .where(
                WorkflowRunRow.status.in_(
                    (WorkflowRunStatus.PENDING.value, WorkflowRunStatus.RUNNING.value)
                ),
                WorkflowRunRow.tenant_id == self._tenant_id,
            )
            .order_by(WorkflowRunRow.created_at, WorkflowRunRow.id)
        )
        return tuple(_run_to_domain(row) for row in rows)

    async def list_for_conversation(self, conversation_id: UUID) -> tuple[WorkflowRun, ...]:
        rows = await self._session.scalars(
            select(WorkflowRunRow)
            .where(
                WorkflowRunRow.conversation_id == str(conversation_id),
                WorkflowRunRow.tenant_id == self._tenant_id,
            )
            .order_by(WorkflowRunRow.created_at, WorkflowRunRow.id)
        )
        return tuple(_run_to_domain(row) for row in rows)

    async def page_for_conversation(
        self,
        conversation_id: UUID,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
    ) -> PageSlice[WorkflowRun]:
        statement = select(WorkflowRunRow).where(
            WorkflowRunRow.conversation_id == str(conversation_id),
            WorkflowRunRow.tenant_id == self._tenant_id,
        )
        if search:
            searched_id = canonical_uuid_search(search)
            if searched_id is not None:
                statement = statement.where(WorkflowRunRow.id == searched_id)
            elif search in {status.value for status in WorkflowRunStatus}:
                statement = statement.where(WorkflowRunRow.status == search)
            else:
                statement = statement.where(
                    WorkflowRunRow.input.startswith(search, autoescape=True)
                )
        if after is not None:
            after_time = to_database_datetime(after.created_at)
            statement = statement.where(
                or_(
                    WorkflowRunRow.created_at < after_time,
                    and_(
                        WorkflowRunRow.created_at == after_time,
                        WorkflowRunRow.id < after.id,
                    ),
                )
            )
        rows = tuple(
            await self._session.scalars(
                statement.order_by(
                    WorkflowRunRow.created_at.desc(),
                    WorkflowRunRow.id.desc(),
                ).limit(limit + 1)
            )
        )
        return PageSlice(
            items=tuple(_run_to_domain(row) for row in rows[:limit]),
            has_more=len(rows) > limit,
        )

    async def add(self, run: WorkflowRun) -> None:
        self._session.add(WorkflowRunRow(tenant_id=self._tenant_id, **_run_values(run)))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _mysql_error_code(error) == 1062:
                raise WorkflowRunAlreadyExists from None
            raise

    async def update(self, run: WorkflowRun) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(WorkflowRunRow)
                .where(
                    WorkflowRunRow.id == str(run.id),
                    WorkflowRunRow.tenant_id == self._tenant_id,
                    WorkflowRunRow.status.in_(
                        (
                            WorkflowRunStatus.PENDING.value,
                            WorkflowRunStatus.RUNNING.value,
                        )
                    ),
                )
                .values(
                    status=run.status.value,
                    output=run.output,
                    current_node_id=run.current_node_id,
                    completed_node_ids=list(run.completed_node_ids),
                    ai_targets=[_ai_target_summary_values(value) for value in run.ai_targets],
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
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._workflows: WorkflowRepository | None = None
        self._workflow_runs: WorkflowRunRepository | None = None
        self._tasks: TaskSubmission | None = None

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

    @property
    def tasks(self) -> TaskSubmission:
        if self._tasks is None:
            raise RuntimeError("工作流事务尚未开始")
        return self._tasks

    async def __aenter__(self) -> SqlAlchemyWorkflowUnitOfWork:
        if self._context is not None:
            raise RuntimeError("工作流事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._workflows = SqlAlchemyWorkflowRepository(session, self._tenant_id)
        self._workflow_runs = SqlAlchemyWorkflowRunRepository(session, self._tenant_id)
        self._tasks = SqlAlchemyTaskSubmission(session)
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
        self._tasks = None
        if context is None:
            raise RuntimeError("工作流事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        session = self._session
        if session is None:
            raise RuntimeError("工作流事务尚未开始")
        await session.commit()


class SqlAlchemyWorkflowUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyWorkflowUnitOfWork:
        return SqlAlchemyWorkflowUnitOfWork(self._database, self._tenant_id_provider())


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
        "employee_id": None if run.origin is None else str(run.origin.employee_id),
        "conversation_id": None if run.origin is None else str(run.origin.conversation_id),
        "assistant_message_id": (
            None if run.origin is None else str(run.origin.assistant_message_id)
        ),
        "status": run.status.value,
        "input": run.input,
        "output": run.output,
        "current_node_id": run.current_node_id,
        "completed_node_ids": list(run.completed_node_ids),
        "ai_targets": [_ai_target_summary_values(value) for value in run.ai_targets],
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


def _target_rows(
    workflow: WorkflowDefinition,
    tenant_id: str,
) -> list[WorkflowAiChatTargetRow]:
    rows: list[WorkflowAiChatTargetRow] = []
    for node in workflow.nodes:
        config = node.config
        if not isinstance(config, AiChatNodeConfig) or config.target is None:
            continue
        employee_id = (
            str(config.target.employee_id)
            if isinstance(config.target, EmployeeAiChatTarget)
            else None
        )
        model_configuration_id = (
            str(config.target.model_configuration_id)
            if isinstance(config.target, ModelAiChatTarget)
            else None
        )
        rows.append(
            WorkflowAiChatTargetRow(
                tenant_id=tenant_id,
                workflow_id=str(workflow.id),
                node_id=node.id,
                target_type=config.target.type.value,
                employee_id=employee_id,
                model_configuration_id=model_configuration_id,
            )
        )
    return rows


def _model_reference_rows(
    workflow: WorkflowDefinition,
    tenant_id: str,
) -> list[ModelConfigurationReferenceRow]:
    model_ids = {
        node.config.target.model_configuration_id
        for node in workflow.nodes
        if isinstance(node.config, AiChatNodeConfig)
        and isinstance(node.config.target, ModelAiChatTarget)
    }
    return [
        ModelConfigurationReferenceRow(
            tenant_id=tenant_id,
            model_configuration_id=str(model_id),
            resource_type="workflow",
            resource_id=str(workflow.id),
            created_at=to_database_datetime(workflow.updated_at),
        )
        for model_id in model_ids
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
        values: dict[str, object] = {"prompt": config.prompt}
        if isinstance(config.target, EmployeeAiChatTarget):
            values["target"] = {
                "type": "employee",
                "employee_id": str(config.target.employee_id),
            }
        elif isinstance(config.target, ModelAiChatTarget):
            values["target"] = {
                "type": "model",
                "model_configuration_id": str(config.target.model_configuration_id),
            }
        return values
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
        origin=(
            None
            if row.employee_id is None
            or row.conversation_id is None
            or row.assistant_message_id is None
            else WorkflowRunOrigin(
                employee_id=UUID(row.employee_id),
                conversation_id=UUID(row.conversation_id),
                assistant_message_id=UUID(row.assistant_message_id),
            )
        ),
        created_at=from_database_datetime(row.created_at),
        started_at=(None if row.started_at is None else from_database_datetime(row.started_at)),
        finished_at=(None if row.finished_at is None else from_database_datetime(row.finished_at)),
        updated_at=from_database_datetime(row.updated_at),
        ai_targets=tuple(_ai_target_summary_from_values(value) for value in row.ai_targets),
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


def _ai_target_summary_values(summary: WorkflowAiTargetSummary) -> dict[str, str]:
    return {
        "node_id": summary.node_id,
        "target_type": summary.target_type.value,
        "target_id": str(summary.target_id),
        "target_name": summary.target_name,
        "model_configuration_id": str(summary.model_configuration_id),
        "model_identifier": summary.model_identifier,
    }


def _ai_target_summary_from_values(values: object) -> WorkflowAiTargetSummary:
    if not isinstance(values, dict) or set(values) != {
        "node_id",
        "target_type",
        "target_id",
        "target_name",
        "model_configuration_id",
        "model_identifier",
    }:
        raise WorkflowRunValidationError("ai_targets", "持久化执行目标摘要不合法")
    try:
        from common_agent.domain.workflow import AiChatTargetType

        return WorkflowAiTargetSummary(
            node_id=str(values["node_id"]),
            target_type=AiChatTargetType(str(values["target_type"])),
            target_id=UUID(str(values["target_id"])),
            target_name=str(values["target_name"]),
            model_configuration_id=UUID(str(values["model_configuration_id"])),
            model_identifier=str(values["model_identifier"]),
        )
    except (TypeError, ValueError):
        raise WorkflowRunValidationError("ai_targets", "持久化执行目标摘要不合法") from None


def _config_from_values(
    node_type: WorkflowNodeType,
    values: dict[str, object],
) -> WorkflowNodeConfig:
    if node_type in {WorkflowNodeType.START, WorkflowNodeType.END}:
        if values:
            raise WorkflowValidationError("config", "开始或结束节点配置必须为空")
        return StartNodeConfig() if node_type is WorkflowNodeType.START else EndNodeConfig()
    if node_type is WorkflowNodeType.AI_CHAT:
        if set(values) == {"prompt"}:
            return AiChatNodeConfig(prompt=values["prompt"])  # type: ignore[arg-type]
        if set(values) != {"prompt", "target"}:
            raise WorkflowValidationError("config", "AI 对话节点配置字段不合法")
        target = values["target"]
        if not isinstance(target, dict):
            raise WorkflowValidationError("config", "AI 对话节点执行目标不合法")
        if set(target) == {"type", "employee_id"} and target["type"] == "employee":
            try:
                resolved_target: AiChatTarget = EmployeeAiChatTarget(
                    employee_id=UUID(str(target["employee_id"]))
                )
            except (ValueError, TypeError):
                raise WorkflowValidationError("config", "AI 对话节点数字员工目标不合法") from None
        elif set(target) == {"type", "model_configuration_id"} and target["type"] == "model":
            try:
                resolved_target = ModelAiChatTarget(
                    model_configuration_id=UUID(str(target["model_configuration_id"]))
                )
            except (ValueError, TypeError):
                raise WorkflowValidationError("config", "AI 对话节点模型目标不合法") from None
        else:
            raise WorkflowValidationError("config", "AI 对话节点执行目标不合法")
        return AiChatNodeConfig(
            prompt=values["prompt"],  # type: ignore[arg-type]
            target=resolved_target,
        )
    if set(values) != {"knowledge_base_id"}:
        raise WorkflowValidationError("config", "知识检索节点配置字段不合法")
    return KnowledgeRetrievalNodeConfig(
        knowledge_base_id=values["knowledge_base_id"]  # type: ignore[arg-type]
    )


def _mysql_error_code(error: IntegrityError) -> int | None:
    arguments = getattr(error.orig, "args", ())
    return arguments[0] if arguments and isinstance(arguments[0], int) else None
