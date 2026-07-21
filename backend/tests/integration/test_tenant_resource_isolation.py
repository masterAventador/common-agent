from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from common_agent.adapters.agent.deep_agents import RuntimeCapabilityUnavailable
from common_agent.adapters.agent.workflow_tools import WorkflowToolRegistry
from common_agent.adapters.persistence.conversations import (
    SqlAlchemyConversationRepository,
)
from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeRepository
from common_agent.adapters.persistence.models import EmployeeRow, TenantRow, WorkflowRow
from common_agent.adapters.persistence.workflows import (
    SqlAlchemyWorkflowRepository,
    SqlAlchemyWorkflowRunRepository,
)
from common_agent.application.workflow_service import WorkflowNotFound, WorkflowService
from common_agent.domain.conversation import Conversation
from common_agent.domain.employee import Employee
from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import (
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunTrigger,
)
from common_agent.tenancy import TenantAccess, TenantRole, bind_tenant
from common_agent.tenancy.constants import DEFAULT_ORGANIZATION_ID, DEFAULT_TENANT_ID
from tests.support.settings import TEST_DATABASE_URL
from tests.unit.workflows.support import workflow_configuration


class _TenantScopedWorkflowLookup:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def get(self, workflow_id: UUID) -> WorkflowDefinition:
        async with self._database.session() as session:
            workflow = await SqlAlchemyWorkflowRepository(session).get(workflow_id)
        if workflow is None:
            raise WorkflowNotFound
        return workflow


def _database_url() -> str:
    return os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)


def test_resource_queries_and_cross_resource_foreign_keys_are_tenant_scoped() -> None:
    async def exercise() -> None:
        database = Database(_database_url())
        tenant_b = uuid4()
        employee = Employee.create(name=f"tenant-a-{uuid4().hex}", system_prompt="隔离测试")
        conversation = Conversation.create(employee_id=employee.id, title="越权会话")
        configuration = workflow_configuration()
        workflow = WorkflowDefinition.create(
            name=f"tenant-a-{uuid4().hex}",
            description=configuration.description,
            nodes=configuration.nodes,
            edges=configuration.edges,
        )
        run = WorkflowRun.create(
            workflow_id=workflow.id,
            trigger=WorkflowRunTrigger.MANUAL,
            input="越权运行",
        )
        await database.start()
        try:
            async with database.session() as session:
                session.add(
                    TenantRow(
                        id=str(tenant_b),
                        organization_id=str(DEFAULT_ORGANIZATION_ID),
                        name=f"隔离工作区-{tenant_b.hex}",
                        created_at=datetime.now(UTC).replace(tzinfo=None),
                    )
                )
                await session.commit()

            async with database.session() as session:
                await SqlAlchemyEmployeeRepository(session, DEFAULT_TENANT_ID).add(employee)
                await SqlAlchemyWorkflowRepository(session, DEFAULT_TENANT_ID).add(workflow)
                await session.commit()

            async with database.session() as session:
                tenant_b_employees = SqlAlchemyEmployeeRepository(session, tenant_b)
                tenant_b_workflows = SqlAlchemyWorkflowRepository(session, tenant_b)
                assert await tenant_b_employees.get(employee.id) is None
                assert employee not in await tenant_b_employees.list()
                assert await tenant_b_workflows.get(workflow.id) is None

            with pytest.raises(IntegrityError):
                async with database.session() as session:
                    await SqlAlchemyConversationRepository(session, tenant_b).add(conversation)
                    await session.commit()

            with pytest.raises(IntegrityError):
                async with database.session() as session:
                    await SqlAlchemyWorkflowRunRepository(session, tenant_b).add(run)
                    await session.commit()

            with bind_tenant(
                TenantAccess(
                    tenant_id=tenant_b,
                    user_id=uuid4(),
                    role=TenantRole.OWNER,
                )
            ):
                registry = WorkflowToolRegistry(
                    cast(WorkflowService, _TenantScopedWorkflowLookup(database))
                )
                with pytest.raises(RuntimeCapabilityUnavailable):
                    await registry.resolve(
                        (workflow.id,),
                        origin=WorkflowRunOrigin(
                            employee_id=uuid4(),
                            conversation_id=uuid4(),
                            assistant_message_id=uuid4(),
                        ),
                    )
        finally:
            async with database.session() as session:
                await session.execute(delete(TenantRow).where(TenantRow.id == str(tenant_b)))
                await session.execute(delete(WorkflowRow).where(WorkflowRow.id == str(workflow.id)))
                await session.execute(delete(EmployeeRow).where(EmployeeRow.id == str(employee.id)))
                await session.commit()
            await database.stop()

    asyncio.run(exercise())
