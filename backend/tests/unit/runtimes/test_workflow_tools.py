from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from datetime import datetime
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.agent.workflow_tools import WorkflowToolRegistry
from common_agent.adapters.workflow.langgraph import LangGraphWorkflowCompiler
from common_agent.application.workflow_service import WorkflowService
from common_agent.audit import (
    AuditAction,
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditPage,
    AuditQuery,
    AuditService,
    build_audit_event,
)
from common_agent.domain.workflow_run import (
    WorkflowRunOrigin,
    WorkflowRunStatus,
    WorkflowRunTrigger,
)
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.observability import bind_observation_context
from common_agent.tenancy import TenantAccess, TenantRole, bind_tenant
from common_agent.workflows.events import WorkflowEventBroker
from common_agent.workflows.nodes.registry import create_workflow_node_registry
from tests.support.knowledge import KnowledgeProbe
from tests.unit.workflows.support import WorkflowUnitOfWorkFactoryProbe, workflow_configuration
from tests.unit.workflows.test_run_service import RunModelProbe

ORIGIN = WorkflowRunOrigin(
    employee_id=uuid4(),
    conversation_id=uuid4(),
    assistant_message_id=uuid4(),
)
TENANT_ACCESS = TenantAccess(tenant_id=uuid4(), user_id=uuid4(), role=TenantRole.OWNER)


class AuditStoreProbe:
    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        self.entries.append(entry)
        return build_audit_event(
            event_id=uuid4(),
            scope_key=f"tenant:{entry.tenant_id}",
            sequence=len(self.entries),
            previous_hash="0" * 64,
            retention_until=retention_until,
            entry=entry,
        )

    async def page(self, query: AuditQuery) -> AuditPage:
        raise AssertionError("not used")

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity:
        raise AssertionError("not used")


def _service(*, model: RunModelProbe | None = None) -> WorkflowService:
    knowledge = KnowledgeBaseService(KnowledgeProbe())
    return WorkflowService(
        WorkflowUnitOfWorkFactoryProbe(),
        knowledge,
        compiler=LangGraphWorkflowCompiler(
            create_workflow_node_registry(model or RunModelProbe(), knowledge)
        ),
        events=WorkflowEventBroker(),
    )


def test_resolved_tool_calls_shared_workflow_service_with_employee_trigger() -> None:
    async def exercise() -> None:
        service = _service()
        workflow = await service.create(workflow_configuration())
        registry = WorkflowToolRegistry(service)

        tools = await registry.resolve((workflow.id,), origin=ORIGIN)
        payload = json.loads(await tools[0].ainvoke({"input": "员工传入的真实参数"}))
        run = await service.get_run(UUID(payload["run_id"]))
        await service.aclose()

        assert payload == {
            "run_id": str(run.id),
            "workflow_id": str(workflow.id),
            "workflow_name": workflow.name,
            "status": "completed",
            "output": "工作流结果",
        }
        assert run.trigger is WorkflowRunTrigger.EMPLOYEE
        assert run.origin == ORIGIN
        assert run.status is WorkflowRunStatus.COMPLETED
        assert run.input == "员工传入的真实参数"

    asyncio.run(exercise())


def test_employee_triggered_workflow_run_is_audited_in_the_request_tenant() -> None:
    async def exercise() -> None:
        service = _service()
        workflow = await service.create(workflow_configuration())
        audit_store = AuditStoreProbe()
        registry = WorkflowToolRegistry(service, audit=AuditService(audit_store))

        with (
            bind_tenant(TENANT_ACCESS),
            bind_observation_context(request_id=str(uuid4())) as context,
        ):
            tool = (await registry.resolve((workflow.id,), origin=ORIGIN))[0]
            payload = json.loads(await tool.ainvoke({"input": "不得进入审计的业务正文"}))
        await service.aclose()

        assert len(audit_store.entries) == 1
        entry = audit_store.entries[0]
        assert entry.action is AuditAction.WORKFLOW_RUN_STARTED
        assert entry.tenant_id == TENANT_ACCESS.tenant_id
        assert entry.actor_user_id == TENANT_ACCESS.user_id
        assert entry.resource_id == payload["run_id"]
        assert entry.trace_id == context.trace_id
        assert "不得进入审计的业务正文" not in repr(entry)

    asyncio.run(exercise())


def test_registry_exposes_exact_allowlist_and_fails_closed_for_missing_workflow() -> None:
    async def exercise() -> None:
        service = _service()
        first = await service.create(replace(workflow_configuration(), name="第一个工作流"))
        second = await service.create(replace(workflow_configuration(), name="第二个工作流"))
        registry = WorkflowToolRegistry(service)

        assert await registry.resolve((), origin=ORIGIN) == ()
        allowed = await registry.resolve((second.id,), origin=ORIGIN)
        assert len(allowed) == 1
        assert second.id.hex in allowed[0].name
        assert first.id.hex not in allowed[0].name
        with pytest.raises(Exception) as captured:
            await registry.resolve((uuid4(),), origin=ORIGIN)
        await service.aclose()

        assert getattr(captured.value, "code", None) == "runtime_capability_unavailable"

    asyncio.run(exercise())


def test_registry_resolves_the_allowlist_with_one_batch_lookup() -> None:
    async def exercise() -> None:
        units = WorkflowUnitOfWorkFactoryProbe()
        knowledge = KnowledgeBaseService(KnowledgeProbe())
        service = WorkflowService(units, knowledge)
        first = await service.create(replace(workflow_configuration(), name="第一个工作流"))
        second = await service.create(replace(workflow_configuration(), name="第二个工作流"))
        units.repository.get_calls = 0
        units.repository.get_many_calls = 0

        tools = await WorkflowToolRegistry(service).resolve(
            (second.id, first.id),
            origin=ORIGIN,
        )
        await service.aclose()

        assert [tool.name for tool in tools] == [
            f"run_workflow_{second.id.hex}",
            f"run_workflow_{first.id.hex}",
        ]
        assert units.repository.get_many_calls == 1
        assert units.repository.get_calls == 0

    asyncio.run(exercise())


def test_failed_workflow_returns_only_stable_tool_error() -> None:
    async def exercise() -> None:
        service = _service(model=RunModelProbe(fail=True))
        workflow = await service.create(workflow_configuration())
        tool = (await WorkflowToolRegistry(service).resolve((workflow.id,), origin=ORIGIN))[0]

        result = await tool.ainvoke({"input": "不要泄漏供应商异常"})
        await service.aclose()

        assert result == "工作流运行失败,错误码:model_unavailable"

    asyncio.run(exercise())


def test_cancelled_tool_stops_the_shared_workflow_run_before_propagating() -> None:
    async def exercise() -> None:
        model = RunModelProbe(block=True)
        units = WorkflowUnitOfWorkFactoryProbe()
        knowledge = KnowledgeBaseService(KnowledgeProbe())
        service = WorkflowService(
            units,
            knowledge,
            compiler=LangGraphWorkflowCompiler(create_workflow_node_registry(model, knowledge)),
            events=WorkflowEventBroker(),
        )
        workflow = await service.create(workflow_configuration())
        tool = (await WorkflowToolRegistry(service).resolve((workflow.id,), origin=ORIGIN))[0]
        invocation = asyncio.create_task(tool.ainvoke({"input": "取消当前工具"}))
        await asyncio.wait_for(model.started.wait(), timeout=1)

        invocation.cancel()
        with pytest.raises(asyncio.CancelledError):
            await invocation
        runs = tuple(units.run_repository.values.values())
        await service.aclose()

        assert len(runs) == 1
        assert runs[0].status is WorkflowRunStatus.STOPPED
        assert runs[0].trigger is WorkflowRunTrigger.EMPLOYEE

    asyncio.run(exercise())
