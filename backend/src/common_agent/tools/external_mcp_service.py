from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from jsonschema import Draft202012Validator

from common_agent.ports.external_mcp import (
    ExternalMcpRepositoryConflict,
    ExternalMcpUnitOfWorkFactory,
)
from common_agent.ports.mcp import (
    ExternalMcpToolClient,
    McpToolCallError,
    McpToolCallResponse,
)
from common_agent.tools.external_mcp import (
    ExternalMcpSnapshot,
    ExternalMcpSourceCommand,
    ExternalMcpSyncResult,
    ExternalMcpValidationError,
    reconcile_external_capabilities,
)
from common_agent.tools.models import McpSourceStatus, ToolCallErrorCode, ToolCapabilityStatus


class ExternalMcpServiceError(Exception):
    code: str
    message: str
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


class ExternalMcpSourceNotFound(ExternalMcpServiceError):
    code = "external_mcp_source_not_found"
    message = "外部 MCP 来源不存在"


class ExternalMcpCapabilityNotFound(ExternalMcpServiceError):
    code = "external_mcp_capability_not_found"
    message = "外部 MCP 能力不存在"


class ExternalMcpConflict(ExternalMcpServiceError):
    code = "external_mcp_conflict"
    message = "外部 MCP 名称重复、同步状态已变化或资源仍被引用"


class ExternalMcpSyncFailed(ExternalMcpServiceError):
    message = "外部 MCP 同步失败"

    def __init__(self, code: str, *, retryable: bool) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__()


class ExternalMcpService:
    def __init__(
        self,
        unit_of_work_factory: ExternalMcpUnitOfWorkFactory,
        client: ExternalMcpToolClient,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._client = client
        self._clock = clock or (lambda: datetime.now(UTC))

    async def list_sources(self) -> tuple[ExternalMcpSnapshot, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.external_mcp.list_sources()

    async def snapshot(self, source_id: UUID) -> ExternalMcpSnapshot:
        async with self._unit_of_work_factory() as unit_of_work:
            snapshot = await unit_of_work.external_mcp.snapshot(source_id)
        if snapshot is None:
            raise ExternalMcpSourceNotFound
        return snapshot

    async def create_source(self, command: ExternalMcpSourceCommand) -> ExternalMcpSnapshot:
        source = command.create(now=self._clock())
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                if await unit_of_work.external_mcp.source_name_exists(source.name):
                    raise ExternalMcpConflict
                await unit_of_work.external_mcp.add_source(source)
                await unit_of_work.commit()
        except ExternalMcpRepositoryConflict:
            raise ExternalMcpConflict from None
        return ExternalMcpSnapshot(source, ())

    async def update_source(
        self,
        source_id: UUID,
        command: ExternalMcpSourceCommand,
    ) -> ExternalMcpSnapshot:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                snapshot = await unit_of_work.external_mcp.snapshot(
                    source_id,
                    for_update=True,
                )
                if snapshot is None:
                    raise ExternalMcpSourceNotFound
                source = command.replace(snapshot.source, now=self._clock())
                if await unit_of_work.external_mcp.source_name_exists(source.name, source.id):
                    raise ExternalMcpConflict
                await unit_of_work.external_mcp.update_source(source)
                if source.endpoint_url != snapshot.source.endpoint_url:
                    await unit_of_work.external_mcp.clear_credential(source.id)
                await unit_of_work.commit()
        except ExternalMcpRepositoryConflict:
            raise ExternalMcpConflict from None
        return ExternalMcpSnapshot(source, snapshot.capabilities)

    async def delete_source(self, source_id: UUID) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                if await unit_of_work.external_mcp.snapshot(
                    source_id,
                    for_update=True,
                ) is None:
                    raise ExternalMcpSourceNotFound
                if not await unit_of_work.external_mcp.delete_source(source_id):
                    raise ExternalMcpConflict
                await unit_of_work.commit()
        except ExternalMcpRepositoryConflict:
            raise ExternalMcpConflict from None

    async def sync_source(self, source_id: UUID) -> ExternalMcpSyncResult:
        before = await self.snapshot(source_id)
        if before.source.status is McpSourceStatus.DISABLED:
            raise ExternalMcpConflict
        try:
            discovered = tuple(await self._client.list_tools(before.source))
        except McpToolCallError as error:
            await self._mark_failed(before)
            raise ExternalMcpSyncFailed(error.code, retryable=error.retryable) from None
        except Exception:
            await self._mark_failed(before)
            raise ExternalMcpSyncFailed(
                ToolCallErrorCode.SOURCE_UNAVAILABLE.value,
                retryable=True,
            ) from None

        try:
            async with self._unit_of_work_factory() as unit_of_work:
                current = await unit_of_work.external_mcp.snapshot(
                    source_id,
                    for_update=True,
                )
                if current is None:
                    raise ExternalMcpSourceNotFound
                if current.source.updated_at != before.source.updated_at:
                    raise ExternalMcpConflict
                result = reconcile_external_capabilities(
                    current.source,
                    current.capabilities,
                    discovered,
                    now=self._clock(),
                )
                await unit_of_work.external_mcp.apply_sync(result)
                await unit_of_work.commit()
                return result
        except ExternalMcpRepositoryConflict:
            raise ExternalMcpConflict from None

    async def call_capability(
        self,
        source_id: UUID,
        capability_id: UUID,
        arguments: dict[str, object],
    ) -> McpToolCallResponse:
        snapshot = await self.snapshot(source_id)
        capability = next(
            (item for item in snapshot.capabilities if item.id == capability_id),
            None,
        )
        if capability is None:
            raise ExternalMcpCapabilityNotFound
        if (
            snapshot.source.status is not McpSourceStatus.READY
            or capability.status is not ToolCapabilityStatus.ACTIVE
        ):
            raise McpToolCallError(ToolCallErrorCode.CAPABILITY_UNAVAILABLE.value)
        try:
            if any(Draft202012Validator(capability.input_schema).iter_errors(arguments)):
                raise McpToolCallError(ToolCallErrorCode.INVALID_ARGUMENTS.value)
        except McpToolCallError:
            raise
        except Exception:
            raise McpToolCallError(ToolCallErrorCode.PROTOCOL_ERROR.value) from None
        return await self._client.call_tool(
            snapshot.source,
            capability.remote_name,
            arguments,
        )

    async def _mark_failed(self, before: ExternalMcpSnapshot) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                current = await unit_of_work.external_mcp.snapshot(
                    before.source.id,
                    for_update=True,
                )
                if current is None:
                    raise ExternalMcpSourceNotFound
                if current.source.updated_at != before.source.updated_at:
                    raise ExternalMcpConflict
                await unit_of_work.external_mcp.update_source(
                    replace(
                        current.source,
                        status=McpSourceStatus.UNAVAILABLE,
                        updated_at=self._clock(),
                    )
                )
                await unit_of_work.commit()
        except ExternalMcpRepositoryConflict:
            raise ExternalMcpConflict from None


__all__ = [
    "ExternalMcpCapabilityNotFound",
    "ExternalMcpConflict",
    "ExternalMcpService",
    "ExternalMcpServiceError",
    "ExternalMcpSourceNotFound",
    "ExternalMcpSyncFailed",
    "ExternalMcpValidationError",
]
