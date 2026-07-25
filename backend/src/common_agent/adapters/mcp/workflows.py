from __future__ import annotations

import asyncio
import json
import re
import secrets
from collections.abc import Mapping, Sequence
from contextlib import suppress
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

from mcp import types
from mcp.server.lowlevel import Server
from mcp.shared.memory import create_connected_server_and_client_session

from common_agent.application.workflow_service import (
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
    WORKFLOW_RUN_INPUT_MAX_LENGTH,
    WorkflowRun,
    WorkflowRunOrigin,
    WorkflowRunTrigger,
)
from common_agent.observability import current_observation_context
from common_agent.ports.mcp import (
    McpToolCallError,
    McpToolCallResponse,
    McpToolDescriptor,
)
from common_agent.tenancy import current_tenant
from common_agent.tools.models import ToolCallErrorCode

_ERROR_CODE_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{1,127}$")
_CALL_TOKEN_ARGUMENT = "_common_agent_call_token"
_INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "input": {
            "type": "string",
            "minLength": 1,
            "maxLength": WORKFLOW_RUN_INPUT_MAX_LENGTH,
            "description": "传给工作流开始节点的输入。",
        }
    },
    "required": ["input"],
    "additionalProperties": False,
}
_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "run_id": {"type": "string"},
        "workflow_id": {"type": "string"},
        "workflow_name": {"type": "string"},
        "status": {"type": "string"},
        "output": {},
        "error_code": {"type": ["string", "null"]},
    },
    "required": [
        "run_id",
        "workflow_id",
        "workflow_name",
        "status",
        "output",
        "error_code",
    ],
    "additionalProperties": False,
}


class WorkflowMcpRuntime:
    """Expose an immutable workflow allowlist through the official MCP protocol."""

    def __init__(
        self,
        workflows: WorkflowService,
        definitions: Sequence[WorkflowDefinition],
        *,
        origin: WorkflowRunOrigin | None,
        audit: AuditService | None = None,
    ) -> None:
        self._workflows = workflows
        self._definitions = {
            _tool_name(definition.id): definition for definition in definitions
        }
        if len(self._definitions) != len(definitions):
            raise ValueError("工作流 MCP 工具名称不能重复")
        self._origin = origin
        self._audit = audit
        self._active_runs: dict[str, UUID] = {}
        self._cancelled_runs: dict[str, UUID] = {}
        self._server: Server[object] = Server("common-agent-workflows")
        self._register_handlers()

    async def list_tools(self) -> Sequence[McpToolDescriptor]:
        async with create_connected_server_and_client_session(self._server) as session:
            result = await session.list_tools()
        return tuple(
            McpToolDescriptor(
                name=tool.name,
                display_name=tool.title or tool.name,
                description=tool.description or "",
                input_schema=cast(dict[str, object], tool.inputSchema),
            )
            for tool in result.tools
        )

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse:
        if _CALL_TOKEN_ARGUMENT in arguments:
            raise McpToolCallError(ToolCallErrorCode.INVALID_ARGUMENTS.value)
        call_token = uuid4().hex
        try:
            async with create_connected_server_and_client_session(self._server) as session:
                result = await session.call_tool(
                    name,
                    dict(arguments),
                    meta={_CALL_TOKEN_ARGUMENT: call_token},
                )
        except asyncio.CancelledError:
            await asyncio.shield(self._stop_active_call(call_token))
            raise
        if result.isError:
            raise McpToolCallError(_error_code(result.content))
        if not isinstance(result.structuredContent, dict):
            raise McpToolCallError(ToolCallErrorCode.PROTOCOL_ERROR.value)
        return McpToolCallResponse(output=cast(dict[str, object], result.structuredContent))

    def _register_handlers(self) -> None:
        # MCP SDK 1.x decorators do not publish complete typing metadata.
        @self._server.list_tools()  # type: ignore[no-untyped-call,untyped-decorator]
        async def list_tools() -> list[types.Tool]:
            return [
                types.Tool(
                    name=name,
                    title=definition.name,
                    description=(
                        f"运行已授权的工作流「{definition.name}」。"
                        "需要执行该工作流时调用,并把用户要求作为 input;"
                        "等待平台返回真实终态后再回答。"
                    ),
                    inputSchema=_INPUT_SCHEMA,
                    outputSchema=_OUTPUT_SCHEMA,
                )
                for name, definition in self._definitions.items()
            ]

        @self._server.call_tool(validate_input=False)  # type: ignore[untyped-decorator]
        async def call_tool(name: str, arguments: dict[str, object]) -> types.CallToolResult:
            definition = self._definitions.get(name)
            if definition is None:
                return _error_result(ToolCallErrorCode.CAPABILITY_UNAVAILABLE.value)
            if set(arguments) != {"input"}:
                return _error_result(ToolCallErrorCode.INVALID_ARGUMENTS.value)
            input_value = arguments.get("input")
            call_token = _request_call_token(self._server)
            if (
                not isinstance(input_value, str)
                or not input_value.strip()
                or len(input_value) > WORKFLOW_RUN_INPUT_MAX_LENGTH
                or not isinstance(call_token, str)
                or len(call_token) != 32
            ):
                return _error_result(ToolCallErrorCode.INVALID_ARGUMENTS.value)
            try:
                run = await self._run(definition, input_value, call_token=call_token)
            except asyncio.CancelledError:
                raise
            except WorkflowServiceError as error:
                return _error_result(_stable_error_code(error.code))
            except Exception:
                return _error_result(ToolCallErrorCode.EXECUTION_FAILED.value)
            output = _run_output(definition, run)
            return types.CallToolResult(
                content=[
                    types.TextContent(
                        type="text",
                        text=json.dumps(output, ensure_ascii=False, separators=(",", ":")),
                    )
                ],
                structuredContent=output,
                isError=False,
            )

    async def _run(
        self,
        definition: WorkflowDefinition,
        input_value: str,
        *,
        call_token: str,
    ) -> WorkflowRun:
        run_id = uuid4()
        self._active_runs[call_token] = run_id
        try:
            await self._workflows.start_run(
                definition.id,
                run_id=run_id,
                input=input_value,
                trigger=(
                    WorkflowRunTrigger.EMPLOYEE
                    if self._origin is not None
                    else WorkflowRunTrigger.MANUAL
                ),
                origin=self._origin,
            )
            await self._record_started(run_id)
            return await self._workflows.wait_for_run(run_id)
        except asyncio.CancelledError:
            self._cancelled_runs[call_token] = run_id
            await asyncio.shield(self._stop_run(run_id))
            raise
        finally:
            if call_token not in self._cancelled_runs:
                self._active_runs.pop(call_token, None)

    async def _stop_active_call(self, call_token: str) -> None:
        run_id = self._active_runs.get(call_token) or self._cancelled_runs.get(call_token)
        if run_id is None:
            return
        await self._stop_run(run_id)
        self._active_runs.pop(call_token, None)
        self._cancelled_runs.pop(call_token, None)

    async def _stop_run(self, run_id: UUID) -> None:
        with suppress(WorkflowRunNotActive, WorkflowServiceError):
            await self._workflows.stop_run(run_id)
        with suppress(WorkflowServiceError):
            await self._workflows.wait_for_run(run_id)

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


def _tool_name(workflow_id: UUID) -> str:
    return f"run_workflow_{workflow_id.hex}"


def _request_call_token(server: Server[object]) -> str | None:
    meta = server.request_context.meta
    if meta is None or meta.model_extra is None:
        return None
    value = meta.model_extra.get(_CALL_TOKEN_ARGUMENT)
    return value if isinstance(value, str) else None


def _run_output(
    definition: WorkflowDefinition,
    run: WorkflowRun,
) -> dict[str, object]:
    return {
        "run_id": str(run.id),
        "workflow_id": str(run.workflow_id),
        "workflow_name": definition.name,
        "status": run.status.value,
        "output": run.output,
        "error_code": run.error_code,
    }


def _error_result(code: str) -> types.CallToolResult:
    return types.CallToolResult(
        content=[types.TextContent(type="text", text=_stable_error_code(code))],
        isError=True,
    )


def _error_code(content: Sequence[types.ContentBlock]) -> str:
    if len(content) == 1 and isinstance(content[0], types.TextContent):
        return _stable_error_code(content[0].text)
    return ToolCallErrorCode.PROTOCOL_ERROR.value


def _stable_error_code(value: str) -> str:
    if _ERROR_CODE_PATTERN.fullmatch(value):
        return value
    return ToolCallErrorCode.EXECUTION_FAILED.value


def _request_id(value: str | None) -> UUID:
    try:
        return UUID(value) if value is not None else uuid4()
    except ValueError:
        return uuid4()


__all__ = ["WorkflowMcpRuntime"]
