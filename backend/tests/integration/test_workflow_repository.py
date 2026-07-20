from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import DBAPIError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.workflows import SqlAlchemyWorkflowRepository
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    StartNodeConfig,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowNodeType,
)
from common_agent.ports.workflows import WorkflowAlreadyExists
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows


def _database_url() -> str:
    return os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)


@asynccontextmanager
async def _database() -> AsyncIterator[Database]:
    database = Database(_database_url())
    await database.start()
    try:
        yield database
    finally:
        await database.stop()


def _workflow(name: str) -> WorkflowDefinition:
    nodes = (
        WorkflowNode(
            id="start",
            type=WorkflowNodeType.START,
            position=WorkflowNodePosition(x=10.25, y=-20.5),
            config=StartNodeConfig(),
        ),
        WorkflowNode(
            id="chat",
            type=WorkflowNodeType.AI_CHAT,
            position=WorkflowNodePosition(x=250, y=0),
            config=AiChatNodeConfig(prompt="根据输入生成检索问题"),
        ),
        WorkflowNode(
            id="retrieve",
            type=WorkflowNodeType.KNOWLEDGE_RETRIEVAL,
            position=WorkflowNodePosition(x=500, y=20),
            config=KnowledgeRetrievalNodeConfig(knowledge_base_id="dataset-round-trip"),
        ),
        WorkflowNode(
            id="end",
            type=WorkflowNodeType.END,
            position=WorkflowNodePosition(x=750, y=0),
            config=EndNodeConfig(),
        ),
    )
    return WorkflowDefinition.create(
        name=name,
        description="验证位置与配置独立持久化",
        nodes=nodes,
        edges=(
            WorkflowEdge(id="edge-1", source="start", target="chat"),
            WorkflowEdge(id="edge-2", source="chat", target="retrieve"),
            WorkflowEdge(id="edge-3", source="retrieve", target="end"),
        ),
    )


def test_workflow_repository_round_trip_survives_database_restart() -> None:
    workflow = _workflow(f"repository-{uuid4().hex}")

    async def exercise() -> WorkflowDefinition | None:
        try:
            async with _database() as first, first.session() as session:
                await SqlAlchemyWorkflowRepository(session).add(workflow)
                await session.commit()

            async with _database() as second, second.session() as session:
                return await SqlAlchemyWorkflowRepository(session).get(workflow.id)
        finally:
            async with _database() as cleanup_database:
                await delete_workflows(cleanup_database, workflow.id)

    assert asyncio.run(exercise()) == workflow


def test_workflow_repository_lists_and_atomically_replaces_graph() -> None:
    first = _workflow(f"first-{uuid4().hex}")
    second = _workflow(f"second-{uuid4().hex}")
    changed = second.reconfigure(
        name="更新后的工作流",
        description="替换全部图数据",
        nodes=(second.nodes[0], second.nodes[-1]),
        edges=(WorkflowEdge(id="direct", source="start", target="end"),),
    )

    async def exercise() -> tuple[tuple[WorkflowDefinition, ...], WorkflowDefinition | None]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    repository = SqlAlchemyWorkflowRepository(session)
                    await repository.add(first)
                    await repository.add(second)
                    await session.commit()

                async with database.session() as session:
                    assert await SqlAlchemyWorkflowRepository(session).update(changed) is True
                    await session.commit()

                async with database.session() as session:
                    repository = SqlAlchemyWorkflowRepository(session)
                    return await repository.list(), await repository.get(uuid4())
            finally:
                await delete_workflows(database, first.id, second.id)

    workflows, missing = asyncio.run(exercise())
    assert first in workflows
    assert changed in workflows
    assert second not in workflows
    assert missing is None


def test_workflow_page_batches_graph_loading_without_n_plus_one_queries() -> None:
    workflows = tuple(_workflow(f"page-batch-{index}-{uuid4().hex}") for index in range(25))

    async def exercise() -> tuple[int, int, bool]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    repository = SqlAlchemyWorkflowRepository(session)
                    for workflow in workflows:
                        await repository.add(workflow)
                    await session.commit()

                async with database.session() as session:
                    statements: list[str] = []

                    def record_statement(
                        _connection: object,
                        _cursor: object,
                        statement: str,
                        _parameters: object,
                        _context: object,
                        _executemany: object,
                    ) -> None:
                        statements.append(statement)

                    bind = session.get_bind()
                    event.listen(bind, "before_cursor_execute", record_statement)
                    try:
                        page = await SqlAlchemyWorkflowRepository(session).page(
                            limit=20,
                            search="page-batch",
                            after=None,
                        )
                    finally:
                        event.remove(bind, "before_cursor_execute", record_statement)
                    return len(page.items), len(statements), page.has_more
            finally:
                await delete_workflows(database, *(workflow.id for workflow in workflows))

    item_count, statement_count, has_more = asyncio.run(exercise())
    assert item_count == 20
    assert statement_count == 3
    assert has_more is True


def test_workflow_repository_rollback_does_not_persist_definition_or_graph() -> None:
    workflow = _workflow(f"rollback-{uuid4().hex}")

    async def exercise() -> WorkflowDefinition | None:
        async with _database() as database:
            with pytest.raises(RuntimeError, match="force rollback"):
                async with database.session() as session:
                    await SqlAlchemyWorkflowRepository(session).add(workflow)
                    raise RuntimeError("force rollback")

            async with database.session() as session:
                return await SqlAlchemyWorkflowRepository(session).get(workflow.id)

    assert asyncio.run(exercise()) is None


def test_workflow_repository_maps_duplicate_identity_without_committing() -> None:
    workflow = _workflow(f"duplicate-{uuid4().hex}")

    async def exercise() -> WorkflowDefinition | None:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyWorkflowRepository(session).add(workflow)
                    await session.commit()

                with pytest.raises(WorkflowAlreadyExists):
                    async with database.session() as session:
                        await SqlAlchemyWorkflowRepository(session).add(workflow)

                async with database.session() as session:
                    return await SqlAlchemyWorkflowRepository(session).get(workflow.id)
            finally:
                await delete_workflows(database, workflow.id)

    assert asyncio.run(exercise()) == workflow


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("name", ""),
        ("name", " leading"),
        ("description", " trailing"),
    ],
)
def test_workflow_mysql_constraints_reject_invalid_definition_fields(
    column: str, value: str
) -> None:
    workflow_id = str(uuid4())

    async def exercise() -> None:
        async with _database() as database:
            values = {
                "id": workflow_id,
                "name": "valid-name",
                "description": "",
            }
            values[column] = value
            with pytest.raises(DBAPIError):
                async with database.session() as session:
                    await session.execute(
                        text(
                            "INSERT INTO workflows "
                            "(id, name, description, created_at, updated_at) VALUES "
                            "(:id, :name, :description, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
                        ),
                        values,
                    )

    asyncio.run(exercise())


def test_workflow_mysql_constraints_reject_unknown_node_and_missing_edge_endpoint() -> None:
    workflow_id = str(uuid4())

    async def exercise() -> None:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await session.execute(
                        text(
                            "INSERT INTO workflows "
                            "(id, name, description, created_at, updated_at) VALUES "
                            "(:id, 'direct-write', '', UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
                        ),
                        {"id": workflow_id},
                    )
                    await session.commit()

                with pytest.raises(DBAPIError):
                    async with database.session() as session:
                        await session.execute(
                            text(
                                "INSERT INTO workflow_nodes "
                                "(workflow_id, id, ordinal, type, position_x, position_y, config) "
                                "VALUES (:workflow_id, 'unknown', 0, 'script', 0, 0, JSON_OBJECT())"
                            ),
                            {"workflow_id": workflow_id},
                        )

                async with database.session() as session:
                    await session.execute(
                        text(
                            "INSERT INTO workflow_nodes "
                            "(workflow_id, id, ordinal, type, position_x, position_y, config) "
                            "VALUES (:workflow_id, 'start', 0, 'start', 0, 0, JSON_OBJECT())"
                        ),
                        {"workflow_id": workflow_id},
                    )
                    await session.commit()

                with pytest.raises(DBAPIError):
                    async with database.session() as session:
                        await session.execute(
                            text(
                                "INSERT INTO workflow_edges "
                                "(workflow_id, id, ordinal, source, target) VALUES "
                                "(:workflow_id, 'edge', 0, 'start', 'missing')"
                            ),
                            {"workflow_id": workflow_id},
                        )
            finally:
                await delete_workflows(database, workflow_id)

    asyncio.run(exercise())
