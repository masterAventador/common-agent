from __future__ import annotations

import asyncio
import json
from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.agent.workflow_tools import WorkflowToolRegistry
from common_agent.application.workflow_service import WorkflowService
from common_agent.domain.workflow_run import WorkflowRunStatus, WorkflowRunTrigger
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.workflows.compiler import WorkflowCompiler
from common_agent.workflows.events import WorkflowEventBroker
from common_agent.workflows.nodes.registry import create_workflow_node_registry
from tests.support.knowledge import KnowledgeProbe
from tests.unit.workflows.support import WorkflowUnitOfWorkFactoryProbe, workflow_configuration
from tests.unit.workflows.test_run_service import RunModelProbe


def _service(*, model: RunModelProbe | None = None) -> WorkflowService:
    knowledge = KnowledgeBaseService(KnowledgeProbe())
    return WorkflowService(
        WorkflowUnitOfWorkFactoryProbe(),
        knowledge,
        compiler=WorkflowCompiler(
            create_workflow_node_registry(model or RunModelProbe(), knowledge)
        ),
        events=WorkflowEventBroker(),
    )


def test_resolved_tool_calls_shared_workflow_service_with_employee_trigger() -> None:
    async def exercise() -> None:
        service = _service()
        workflow = await service.create(workflow_configuration())
        registry = WorkflowToolRegistry(service)

        tools = await registry.resolve((workflow.id,))
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
        assert run.status is WorkflowRunStatus.COMPLETED
        assert run.input == "员工传入的真实参数"

    asyncio.run(exercise())


def test_registry_exposes_exact_allowlist_and_fails_closed_for_missing_workflow() -> None:
    async def exercise() -> None:
        service = _service()
        first = await service.create(replace(workflow_configuration(), name="第一个工作流"))
        second = await service.create(replace(workflow_configuration(), name="第二个工作流"))
        registry = WorkflowToolRegistry(service)

        assert await registry.resolve(()) == ()
        allowed = await registry.resolve((second.id,))
        assert len(allowed) == 1
        assert second.id.hex in allowed[0].name
        assert first.id.hex not in allowed[0].name
        with pytest.raises(Exception) as captured:
            await registry.resolve((uuid4(),))
        await service.aclose()

        assert getattr(captured.value, "code", None) == "runtime_capability_unavailable"

    asyncio.run(exercise())


def test_failed_workflow_returns_only_stable_tool_error() -> None:
    async def exercise() -> None:
        service = _service(model=RunModelProbe(fail=True))
        workflow = await service.create(workflow_configuration())
        tool = (await WorkflowToolRegistry(service).resolve((workflow.id,)))[0]

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
            compiler=WorkflowCompiler(create_workflow_node_registry(model, knowledge)),
            events=WorkflowEventBroker(),
        )
        workflow = await service.create(workflow_configuration())
        tool = (await WorkflowToolRegistry(service).resolve((workflow.id,)))[0]
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
