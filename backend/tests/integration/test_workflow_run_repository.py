from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.workflows import (
    SqlAlchemyWorkflowRepository,
    SqlAlchemyWorkflowRunRepository,
)
from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import WorkflowRun, WorkflowRunTrigger
from common_agent.ports.workflows import WorkflowRunAlreadyExists
from tests.support.settings import TEST_DATABASE_URL
from tests.support.workflows import delete_workflows
from tests.unit.workflows.support import workflow_configuration


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


def _records() -> tuple[WorkflowDefinition, WorkflowRun, WorkflowRun]:
    configuration = workflow_configuration()
    workflow = WorkflowDefinition.create(
        name=configuration.name,
        description=configuration.description,
        nodes=configuration.nodes,
        edges=configuration.edges,
    )
    pending = WorkflowRun.create(
        workflow_id=workflow.id,
        trigger=WorkflowRunTrigger.MANUAL,
        input="持久化输入",
        now=workflow.updated_at + timedelta(microseconds=1),
    )
    running = pending.start(now=pending.updated_at + timedelta(microseconds=1))
    return workflow, pending, running


def test_workflow_run_round_trip_and_update_survive_database_restart() -> None:
    workflow, pending, running = _records()

    async def exercise() -> WorkflowRun | None:
        try:
            async with _database() as first, first.session() as session:
                await SqlAlchemyWorkflowRepository(session).add(workflow)
                await SqlAlchemyWorkflowRunRepository(session).add(pending)
                await session.commit()

            async with _database() as second, second.session() as session:
                repository = SqlAlchemyWorkflowRunRepository(session)
                assert await repository.update(running) is True
                await session.commit()

            async with _database() as restarted, restarted.session() as session:
                return await SqlAlchemyWorkflowRunRepository(session).get(pending.id)
        finally:
            async with _database() as cleanup:
                await delete_workflows(cleanup, workflow.id)

    assert asyncio.run(exercise()) == running


def test_workflow_run_repository_lists_active_and_maps_duplicate_identity() -> None:
    workflow, pending, running = _records()
    second = WorkflowRun.create(
        workflow_id=workflow.id,
        trigger=WorkflowRunTrigger.EMPLOYEE,
        input="第二次运行",
        now=running.updated_at + timedelta(microseconds=1),
    )

    async def exercise() -> tuple[WorkflowRun, ...]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyWorkflowRepository(session).add(workflow)
                    repository = SqlAlchemyWorkflowRunRepository(session)
                    await repository.add(running)
                    await repository.add(second)
                    await session.commit()

                with pytest.raises(WorkflowRunAlreadyExists):
                    async with database.session() as session:
                        await SqlAlchemyWorkflowRunRepository(session).add(pending)

                async with database.session() as session:
                    return await SqlAlchemyWorkflowRunRepository(session).list_active()
            finally:
                await delete_workflows(database, workflow.id)

    active = asyncio.run(exercise())
    own_ids = {pending.id, second.id}
    assert {run.id for run in active if run.id in own_ids} == own_ids


def test_workflow_run_transaction_rollback_and_mysql_constraints_fail_closed() -> None:
    workflow, pending, _ = _records()

    async def exercise() -> WorkflowRun | None:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyWorkflowRepository(session).add(workflow)
                    await session.commit()

                with pytest.raises(RuntimeError, match="force rollback"):
                    async with database.session() as session:
                        await SqlAlchemyWorkflowRunRepository(session).add(pending)
                        raise RuntimeError("force rollback")

                with pytest.raises(DBAPIError):
                    async with database.session() as session:
                        await session.execute(
                            text(
                                "INSERT INTO workflow_runs "
                                "(id, workflow_id, trigger, status, input, output, "
                                "completed_node_ids, created_at, updated_at) VALUES "
                                "(:id, :workflow_id, 'script', 'pending', 'input', '', "
                                "JSON_ARRAY(), UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
                            ),
                            {"id": str(uuid4()), "workflow_id": str(workflow.id)},
                        )

                async with database.session() as session:
                    return await SqlAlchemyWorkflowRunRepository(session).get(pending.id)
            finally:
                await delete_workflows(database, workflow.id)

    assert asyncio.run(exercise()) is None
