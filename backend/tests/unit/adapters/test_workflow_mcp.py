from __future__ import annotations

import asyncio
from uuid import UUID

from common_agent.adapters.mcp.workflows import WorkflowMcpRuntime
from common_agent.domain.workflow_run import WorkflowRunStatus, WorkflowRunTrigger
from tests.unit.runtimes.test_workflow_tools import ORIGIN, _service
from tests.unit.workflows.support import workflow_configuration


def test_workflow_capability_lists_and_calls_through_the_real_mcp_protocol() -> None:
    async def exercise() -> None:
        service = _service()
        workflow = await service.create(workflow_configuration())
        runtime = WorkflowMcpRuntime(service, (workflow,), origin=ORIGIN)

        tools = await runtime.list_tools()
        assert [tool.name for tool in tools] == [f"run_workflow_{workflow.id.hex}"]
        assert tools[0].input_schema["required"] == ["input"]

        response = await runtime.call_tool(
            tools[0].name,
            {"input": "经 MCP 传给工作流的参数"},
        )
        run = await service.get_run(UUID(str(response.output["run_id"])))
        await service.aclose()

        assert response.output["status"] == "completed"
        assert response.output["output"] == "工作流结果"
        assert run.status is WorkflowRunStatus.COMPLETED
        assert run.trigger is WorkflowRunTrigger.EMPLOYEE
        assert run.origin == ORIGIN
        assert run.input == "经 MCP 传给工作流的参数"

    asyncio.run(exercise())
