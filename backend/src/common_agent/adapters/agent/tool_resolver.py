from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from langchain_core.tools import BaseTool

from common_agent.domain.workflow_run import WorkflowRunOrigin
from common_agent.tools.models import ToolGrantTarget


class WorkflowToolResolver(Protocol):
    async def resolve(
        self,
        workflow_ids: Sequence[UUID],
        *,
        origin: WorkflowRunOrigin | None,
    ) -> tuple[BaseTool, ...]: ...


class CapabilityToolResolver(Protocol):
    async def resolve(
        self,
        capability_ids: Sequence[UUID],
        *,
        target: ToolGrantTarget | None,
    ) -> tuple[BaseTool, ...]: ...


class CompositeDeepAgentToolResolver:
    def __init__(
        self,
        workflows: WorkflowToolResolver,
        capabilities: CapabilityToolResolver,
    ) -> None:
        self._workflows = workflows
        self._capabilities = capabilities

    async def resolve(
        self,
        workflow_ids: Sequence[UUID],
        *,
        tool_capability_ids: Sequence[UUID] = (),
        tool_grant_target: ToolGrantTarget | None = None,
        origin: WorkflowRunOrigin | None,
    ) -> tuple[BaseTool, ...]:
        workflow_tools = await self._workflows.resolve(workflow_ids, origin=origin)
        capability_tools = await self._capabilities.resolve(
            tool_capability_ids,
            target=tool_grant_target,
        )
        names = [tool.name for tool in (*workflow_tools, *capability_tools)]
        if len(set(names)) != len(names):
            raise ValueError("工作流与 MCP 工具名称不能冲突")
        return (*workflow_tools, *capability_tools)


__all__ = [
    "CapabilityToolResolver",
    "CompositeDeepAgentToolResolver",
    "WorkflowToolResolver",
]
