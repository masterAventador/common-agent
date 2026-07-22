from __future__ import annotations

import json
import secrets
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Annotated, Protocol
from uuid import UUID, uuid4

from langchain_core.tools import BaseTool, StructuredTool, ToolException
from pydantic import BaseModel, ConfigDict, Field

from common_agent.adapters.agent.deep_agents import RuntimeCapabilityUnavailable
from common_agent.adapters.agent.tool_metadata import (
    TOOL_METADATA_CAPABILITY_ID,
    TOOL_METADATA_CAPABILITY_NAME,
)
from common_agent.audit import (
    AuditAction,
    AuditEntry,
    AuditOutcome,
    AuditResourceType,
    AuditService,
)
from common_agent.observability import current_observation_context
from common_agent.ports.mcp import (
    ExternalMcpToolClient,
    ManagedMcpToolClient,
    McpToolCallError,
    McpToolClient,
    McpToolDescriptor,
)
from common_agent.tenancy import current_tenant
from common_agent.tools.models import (
    McpSourceType,
    ToolGrantTarget,
    ToolRuntimeCapability,
    normalize_input_schema,
)
from common_agent.tools.platform import CURRENT_TIME_TOOL_NAME
from common_agent.tools.service import ToolCapabilityUnavailable


class ToolRuntimeDirectory(Protocol):
    async def authorized_runtime_capabilities(
        self,
        target: ToolGrantTarget,
        capability_ids: tuple[UUID, ...],
    ) -> tuple[ToolRuntimeCapability, ...]: ...


class _CurrentTimeArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    utc_offset: Annotated[
        str,
        Field(pattern=r"^[+-](?:0\d|1[0-4]):[0-5]\d$"),
    ] = "+08:00"


class PlatformMcpToolRegistry:
    def __init__(
        self,
        tools: ToolRuntimeDirectory,
        mcp: McpToolClient,
        *,
        managed_mcp: ManagedMcpToolClient | None = None,
        external_mcp: ExternalMcpToolClient | None = None,
        audit: AuditService | None = None,
    ) -> None:
        self._tools = tools
        self._mcp = mcp
        self._managed_mcp = managed_mcp
        self._external_mcp = external_mcp
        self._audit = audit

    async def resolve(
        self,
        capability_ids: Sequence[UUID],
        *,
        target: ToolGrantTarget | None,
    ) -> tuple[BaseTool, ...]:
        requested = tuple(capability_ids)
        if not requested:
            return ()
        if target is None:
            raise RuntimeCapabilityUnavailable
        try:
            capabilities = await self._tools.authorized_runtime_capabilities(target, requested)
        except ToolCapabilityUnavailable:
            raise RuntimeCapabilityUnavailable from None
        platform_descriptors: dict[str, McpToolDescriptor] = {}
        if any(item.source.source_type is McpSourceType.PLATFORM for item in capabilities):
            platform_descriptors = {tool.name: tool for tool in await self._mcp.list_tools()}
        managed_descriptors: dict[UUID, dict[str, McpToolDescriptor]] = {}
        managed_source_ids = {
            item.source.id
            for item in capabilities
            if item.source.source_type is McpSourceType.MANAGED_HTTP
        }
        if managed_source_ids:
            if self._managed_mcp is None:
                raise RuntimeCapabilityUnavailable
            for source_id in managed_source_ids:
                managed_descriptors[source_id] = {
                    tool.name: tool
                    for tool in await self._managed_mcp.list_tools(source_id)
                }
        external_descriptors: dict[UUID, dict[str, McpToolDescriptor]] = {}
        external_sources = {
            item.source.id: item.source
            for item in capabilities
            if item.source.source_type is McpSourceType.EXTERNAL
        }
        if external_sources:
            if self._external_mcp is None:
                raise RuntimeCapabilityUnavailable
            for source_id, source in external_sources.items():
                external_descriptors[source_id] = {
                    tool.name: tool for tool in await self._external_mcp.list_tools(source)
                }
        return tuple(
            self._tool(
                item,
                target,
                platform_descriptors,
                managed_descriptors,
                external_descriptors,
            )
            for item in capabilities
        )

    def _tool(
        self,
        item: ToolRuntimeCapability,
        target: ToolGrantTarget,
        platform_descriptors: dict[str, McpToolDescriptor],
        managed_descriptors: dict[UUID, dict[str, McpToolDescriptor]],
        external_descriptors: dict[UUID, dict[str, McpToolDescriptor]],
    ) -> BaseTool:
        source = item.source
        capability = item.capability
        if source.source_type is McpSourceType.PLATFORM:
            descriptor = platform_descriptors.get(capability.remote_name)
        elif source.source_type is McpSourceType.MANAGED_HTTP:
            descriptor = managed_descriptors.get(source.id, {}).get(capability.remote_name)
        elif source.source_type is McpSourceType.EXTERNAL:
            descriptor = external_descriptors.get(source.id, {}).get(capability.remote_name)
        else:
            raise RuntimeCapabilityUnavailable
        if descriptor is None:
            raise RuntimeCapabilityUnavailable
        _, fingerprint = normalize_input_schema(descriptor.input_schema)
        if fingerprint != capability.schema_fingerprint:
            raise RuntimeCapabilityUnavailable
        if source.source_type in {McpSourceType.MANAGED_HTTP, McpSourceType.EXTERNAL}:
            return self._remote_tool(item, target, descriptor)
        if descriptor.name != CURRENT_TIME_TOOL_NAME:
            raise RuntimeCapabilityUnavailable

        async def call_current_time(utc_offset: str = "+08:00") -> str:
            await self._record(capability.id, AuditOutcome.STARTED)
            try:
                current = await self._tools.authorized_runtime_capabilities(
                    target,
                    (capability.id,),
                )
                if len(current) != 1 or current[0].capability.remote_name != descriptor.name:
                    raise ToolCapabilityUnavailable
                result = await self._mcp.call_tool(
                    descriptor.name,
                    {"utc_offset": utc_offset},
                )
            except ToolCapabilityUnavailable:
                await self._record(
                    capability.id,
                    AuditOutcome.DENIED,
                    error_code="tool_unauthorized",
                )
                raise ToolException("工具调用失败,错误码:tool_unauthorized") from None
            except McpToolCallError as error:
                await self._record(
                    capability.id,
                    AuditOutcome.FAILED,
                    error_code=error.code,
                )
                raise ToolException(f"工具调用失败,错误码:{error.code}") from None
            except Exception:
                await self._record(
                    capability.id,
                    AuditOutcome.FAILED,
                    error_code="tool_execution_failed",
                )
                raise ToolException("工具调用失败,错误码:tool_execution_failed") from None
            await self._record(capability.id, AuditOutcome.SUCCEEDED)
            return json.dumps(result.output, ensure_ascii=False, separators=(",", ":"))

        return StructuredTool.from_function(
            coroutine=call_current_time,
            name=descriptor.name,
            description=descriptor.description,
            args_schema=_CurrentTimeArguments,
            handle_tool_error=True,
            metadata={
                TOOL_METADATA_CAPABILITY_ID: str(capability.id),
                TOOL_METADATA_CAPABILITY_NAME: capability.display_name,
            },
        )

    def _remote_tool(
        self,
        item: ToolRuntimeCapability,
        target: ToolGrantTarget,
        descriptor: McpToolDescriptor,
    ) -> BaseTool:
        source = item.source
        capability = item.capability

        async def call_remote(**arguments: object) -> str:
            await self._record(capability.id, AuditOutcome.STARTED)
            try:
                current = await self._tools.authorized_runtime_capabilities(
                    target,
                    (capability.id,),
                )
                if (
                    len(current) != 1
                    or current[0].source.id != source.id
                    or current[0].source.source_type is not source.source_type
                    or current[0].capability.remote_name != descriptor.name
                    or current[0].capability.schema_fingerprint
                    != capability.schema_fingerprint
                ):
                    raise ToolCapabilityUnavailable
                if source.source_type is McpSourceType.MANAGED_HTTP:
                    if self._managed_mcp is None:
                        raise ToolCapabilityUnavailable
                    result = await self._managed_mcp.call_tool(
                        source.id,
                        descriptor.name,
                        arguments,
                    )
                else:
                    if self._external_mcp is None:
                        raise ToolCapabilityUnavailable
                    result = await self._external_mcp.call_tool(
                        current[0].source,
                        descriptor.name,
                        arguments,
                    )
                output = result.output
            except ToolCapabilityUnavailable:
                await self._record(
                    capability.id,
                    AuditOutcome.DENIED,
                    error_code="tool_unauthorized",
                )
                raise ToolException("工具调用失败,错误码:tool_unauthorized") from None
            except McpToolCallError as error:
                await self._record(
                    capability.id,
                    AuditOutcome.FAILED,
                    error_code=error.code,
                )
                raise ToolException(f"工具调用失败,错误码:{error.code}") from None
            except Exception:
                await self._record(
                    capability.id,
                    AuditOutcome.FAILED,
                    error_code="tool_execution_failed",
                )
                raise ToolException("工具调用失败,错误码:tool_execution_failed") from None
            await self._record(capability.id, AuditOutcome.SUCCEEDED)
            return json.dumps(output, ensure_ascii=False, separators=(",", ":"))

        return StructuredTool.from_function(
            coroutine=call_remote,
            name=f"{capability.remote_name[:80]}__{capability.id.hex[:12]}",
            description=descriptor.description,
            args_schema=descriptor.input_schema,
            handle_tool_error=True,
            metadata={
                TOOL_METADATA_CAPABILITY_ID: str(capability.id),
                TOOL_METADATA_CAPABILITY_NAME: capability.display_name,
            },
        )

    async def _record(
        self,
        capability_id: UUID,
        outcome: AuditOutcome,
        *,
        error_code: str | None = None,
    ) -> None:
        if self._audit is None:
            return
        access = current_tenant()
        context = current_observation_context()
        await self._audit.record(
            AuditEntry(
                tenant_id=access.tenant_id,
                actor_user_id=access.user_id,
                action=AuditAction.TOOL_CALLED,
                outcome=outcome,
                request_id=_request_id(context.request_id if context is not None else None),
                trace_id=context.trace_id if context is not None else secrets.token_hex(16),
                resource_type=AuditResourceType.TOOL_CAPABILITY,
                resource_id=str(capability_id),
                error_code=error_code,
                occurred_at=datetime.now(UTC),
            )
        )


def _request_id(value: str | None) -> UUID:
    try:
        return UUID(value) if value is not None else uuid4()
    except ValueError:
        return uuid4()


__all__ = [
    "TOOL_METADATA_CAPABILITY_ID",
    "TOOL_METADATA_CAPABILITY_NAME",
    "ManagedMcpToolClient",
    "PlatformMcpToolRegistry",
    "ToolRuntimeDirectory",
]
