from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Annotated
from uuid import UUID

from langchain_core.tools import BaseTool, StructuredTool, ToolException

from common_agent.adapters.agent.deep_agents import RuntimeCapabilityUnavailable
from common_agent.adapters.mcp.workflows import WorkflowMcpRuntime
from common_agent.application.workflow_service import WorkflowNotFound, WorkflowService
from common_agent.audit import AuditService
from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import WorkflowRunOrigin
from common_agent.ports.mcp import McpToolCallError, McpToolClient, McpToolDescriptor


class WorkflowToolRegistry:
    """Resolve an employee allowlist into MCP-backed workflow tools."""

    def __init__(self, workflows: WorkflowService, *, audit: AuditService | None = None) -> None:
        self._workflows = workflows
        self._audit = audit

    async def resolve(
        self,
        workflow_ids: Sequence[UUID],
        *,
        origin: WorkflowRunOrigin | None,
    ) -> tuple[BaseTool, ...]:
        try:
            definitions = await self._workflows.get_many(tuple(workflow_ids))
        except WorkflowNotFound:
            raise RuntimeCapabilityUnavailable from None
        runtime = WorkflowMcpRuntime(
            self._workflows,
            definitions,
            origin=origin,
            audit=self._audit,
        )
        descriptors = {descriptor.name: descriptor for descriptor in await runtime.list_tools()}
        try:
            return tuple(
                self._tool(
                    definition,
                    descriptors[f"run_workflow_{definition.id.hex}"],
                    runtime,
                )
                for definition in definitions
            )
        except KeyError:
            raise RuntimeCapabilityUnavailable from None

    @staticmethod
    def _tool(
        workflow: WorkflowDefinition,
        descriptor: McpToolDescriptor,
        runtime: McpToolClient,
    ) -> BaseTool:
        async def run_workflow(
            input: Annotated[str, "传给工作流开始节点的输入"],
        ) -> str:
            try:
                response = await runtime.call_tool(descriptor.name, {"input": input})
                return _tool_result(workflow, response.output)
            except McpToolCallError as error:
                raise ToolException(f"工作流调用失败,错误码:{error.code}") from None

        return StructuredTool.from_function(
            coroutine=run_workflow,
            name=descriptor.name,
            description=descriptor.description,
            handle_tool_error=True,
        )


def _tool_result(workflow: WorkflowDefinition, output: dict[str, object]) -> str:
    status = output.get("status")
    if status == "failed":
        error_code = output.get("error_code")
        if not isinstance(error_code, str) or not error_code:
            error_code = "workflow_execution_failed"
        raise ToolException(f"工作流运行失败,错误码:{error_code}")
    if status == "stopped":
        raise ToolException("工作流运行已停止")
    if status != "completed":
        raise ToolException("工作流运行未返回终态")
    expected_workflow_id = str(workflow.id)
    if output.get("workflow_id") != expected_workflow_id:
        raise ToolException("工作流调用失败,错误码:tool_protocol_error")
    run_id = output.get("run_id")
    if not isinstance(run_id, str):
        raise ToolException("工作流调用失败,错误码:tool_protocol_error")
    return json.dumps(
        {
            "run_id": run_id,
            "workflow_id": expected_workflow_id,
            "workflow_name": workflow.name,
            "status": status,
            "output": output.get("output"),
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


__all__ = ["WorkflowToolRegistry"]
