from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from contextlib import suppress
from typing import Annotated
from uuid import UUID, uuid4

from langchain_core.tools import BaseTool, StructuredTool, ToolException

from common_agent.adapters.agent.deep_agents import RuntimeCapabilityUnavailable
from common_agent.application.workflow_service import (
    WorkflowNotFound,
    WorkflowRunNotActive,
    WorkflowService,
    WorkflowServiceError,
)
from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import WorkflowRun, WorkflowRunStatus, WorkflowRunTrigger


class WorkflowToolRegistry:
    """Resolve an employee allowlist into immutable, workflow-specific tools."""

    def __init__(self, workflows: WorkflowService) -> None:
        self._workflows = workflows

    async def resolve(self, workflow_ids: Sequence[UUID]) -> tuple[BaseTool, ...]:
        definitions: list[WorkflowDefinition] = []
        try:
            for workflow_id in workflow_ids:
                definitions.append(await self._workflows.get(workflow_id))
        except WorkflowNotFound:
            raise RuntimeCapabilityUnavailable from None
        return tuple(self._tool(definition) for definition in definitions)

    def _tool(self, workflow: WorkflowDefinition) -> BaseTool:
        async def run_workflow(
            input: Annotated[str, "传给工作流开始节点的输入"],
        ) -> str:
            run_id = uuid4()
            try:
                await self._workflows.start_run(
                    workflow.id,
                    run_id=run_id,
                    input=input,
                    trigger=WorkflowRunTrigger.EMPLOYEE,
                )
                run = await self._workflows.wait_for_run(run_id)
            except asyncio.CancelledError:
                with suppress(WorkflowRunNotActive, WorkflowServiceError):
                    await self._workflows.stop_run(run_id)
                with suppress(WorkflowServiceError):
                    await self._workflows.wait_for_run(run_id)
                raise
            except WorkflowServiceError as error:
                raise ToolException(f"工作流调用失败,错误码:{error.code}") from None
            return _tool_result(workflow, run)

        return StructuredTool.from_function(
            coroutine=run_workflow,
            name=f"run_workflow_{workflow.id.hex}",
            description=(
                f"运行已授权的工作流「{workflow.name}」。"
                "需要执行该工作流时调用,并把用户要求作为 input;等待平台返回真实终态后再回答。"
            ),
            handle_tool_error=True,
        )


def _tool_result(workflow: WorkflowDefinition, run: WorkflowRun) -> str:
    if run.status is WorkflowRunStatus.COMPLETED:
        return json.dumps(
            {
                "run_id": str(run.id),
                "workflow_id": str(run.workflow_id),
                "workflow_name": workflow.name,
                "status": run.status.value,
                "output": run.output,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if run.status is WorkflowRunStatus.FAILED:
        error_code = run.error_code or "workflow_execution_failed"
        raise ToolException(f"工作流运行失败,错误码:{error_code}")
    if run.status is WorkflowRunStatus.STOPPED:
        raise ToolException("工作流运行已停止")
    raise ToolException("工作流运行未返回终态")
