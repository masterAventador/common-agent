from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Sequence
from contextlib import suppress
from datetime import UTC, datetime
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
from common_agent.audit import (
    AuditAction,
    AuditEntry,
    AuditOutcome,
    AuditResourceType,
    AuditService,
)
from common_agent.domain.workflow import WorkflowDefinition
from common_agent.domain.workflow_run import (
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunStatus,
    WorkflowRunTrigger,
)
from common_agent.observability import current_observation_context
from common_agent.tenancy import current_tenant


class WorkflowToolRegistry:
    """Resolve an employee allowlist into immutable, workflow-specific tools."""

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
        return tuple(self._tool(definition, origin) for definition in definitions)

    def _tool(
        self,
        workflow: WorkflowDefinition,
        origin: WorkflowRunOrigin | None,
    ) -> BaseTool:
        async def run_workflow(
            input: Annotated[str, "传给工作流开始节点的输入"],
        ) -> str:
            run_id = uuid4()
            try:
                await self._workflows.start_run(
                    workflow.id,
                    run_id=run_id,
                    input=input,
                    trigger=(
                        WorkflowRunTrigger.EMPLOYEE
                        if origin is not None
                        else WorkflowRunTrigger.MANUAL
                    ),
                    origin=origin,
                )
                await self._record_started(run_id)
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

    async def _record_started(self, run_id: UUID) -> None:
        if self._audit is None:
            return
        access = current_tenant()
        context = current_observation_context()
        await self._audit.record(
            AuditEntry(
                tenant_id=access.tenant_id,
                actor_user_id=access.user_id,
                action=AuditAction.WORKFLOW_RUN_STARTED,
                outcome=AuditOutcome.SUCCEEDED,
                request_id=_request_id(context.request_id if context is not None else None),
                trace_id=context.trace_id if context is not None else secrets.token_hex(16),
                resource_type=AuditResourceType.WORKFLOW_RUN,
                resource_id=str(run_id),
                error_code=None,
                occurred_at=datetime.now(UTC),
            )
        )


def _request_id(value: str | None) -> UUID:
    try:
        return UUID(value) if value is not None else uuid4()
    except ValueError:
        return uuid4()


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
