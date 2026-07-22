from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import UUID

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from common_agent.ports.mcp import McpToolDescriptor
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolCapabilityStatus,
    ToolValidationError,
)

EXTERNAL_MCP_MAX_TOOLS = 500


class ExternalMcpValidationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ExternalMcpSourceCommand:
    name: str
    endpoint_url: str
    description: str = ""

    def create(
        self,
        *,
        source_id: UUID | None = None,
        now: datetime | None = None,
    ) -> McpSource:
        return McpSource.create(
            name=self.name,
            description=self.description,
            source_type=McpSourceType.EXTERNAL,
            endpoint_url=self.endpoint_url,
            status=McpSourceStatus.DRAFT,
            source_id=source_id,
            now=now,
        )

    def replace(self, source: McpSource, *, now: datetime | None = None) -> McpSource:
        if source.source_type is not McpSourceType.EXTERNAL:
            raise ExternalMcpValidationError("只能修改外部 MCP 来源")
        candidate = self.create(source_id=source.id, now=now)
        return replace(
            candidate,
            status=(
                source.status
                if candidate.endpoint_url == source.endpoint_url
                else McpSourceStatus.DRAFT
            ),
            created_at=source.created_at,
        )


@dataclass(frozen=True, slots=True)
class ExternalMcpSnapshot:
    source: McpSource
    capabilities: tuple[ToolCapability, ...]

    def __post_init__(self) -> None:
        if self.source.source_type is not McpSourceType.EXTERNAL:
            raise ExternalMcpValidationError("快照来源不是外部 MCP")
        if any(item.source_id != self.source.id for item in self.capabilities):
            raise ExternalMcpValidationError("外部 MCP 能力与来源不匹配")


@dataclass(frozen=True, slots=True)
class ExternalMcpSyncResult(ExternalMcpSnapshot):
    added: int = 0
    updated: int = 0
    schema_changed: int = 0
    removed: int = 0
    reactivated: int = 0


def reconcile_external_capabilities(
    source: McpSource,
    existing: tuple[ToolCapability, ...],
    discovered: tuple[McpToolDescriptor, ...],
    *,
    now: datetime | None = None,
) -> ExternalMcpSyncResult:
    if source.source_type is not McpSourceType.EXTERNAL:
        raise ExternalMcpValidationError("只能同步外部 MCP 来源")
    if len(discovered) > EXTERNAL_MCP_MAX_TOOLS:
        raise ExternalMcpValidationError(
            f"外部 MCP 工具不能超过 {EXTERNAL_MCP_MAX_TOOLS} 项"
        )
    names = tuple(item.name for item in discovered)
    if len(set(names)) != len(names):
        raise ExternalMcpValidationError("外部 MCP 返回了重复工具名称")
    existing_by_name: dict[str, ToolCapability] = {}
    for capability in existing:
        if capability.source_id != source.id:
            raise ExternalMcpValidationError("外部 MCP 能力与来源不匹配")
        if capability.remote_name in existing_by_name:
            raise ExternalMcpValidationError("已有外部 MCP 工具名称重复")
        existing_by_name[capability.remote_name] = capability

    synchronized_at = now or datetime.now(UTC)
    capabilities: list[ToolCapability] = []
    added = updated = schema_changed = removed = reactivated = 0
    seen: set[str] = set()
    for descriptor in discovered:
        seen.add(descriptor.name)
        try:
            Draft202012Validator.check_schema(descriptor.input_schema)
        except SchemaError as error:
            raise ExternalMcpValidationError("外部 MCP 工具输入 Schema 不合法") from error
        if descriptor.input_schema.get("type") != "object":
            raise ExternalMcpValidationError("外部 MCP 工具输入 Schema 必须描述对象")
        try:
            candidate = ToolCapability.create(
                source_id=source.id,
                remote_name=descriptor.name,
                display_name=descriptor.display_name,
                description=descriptor.description,
                input_schema=descriptor.input_schema,
                now=synchronized_at,
            )
        except ToolValidationError as error:
            raise ExternalMcpValidationError("外部 MCP 工具定义不合法") from error
        current = existing_by_name.get(descriptor.name)
        if current is None:
            capabilities.append(candidate)
            added += 1
            continue
        if current.schema_fingerprint != candidate.schema_fingerprint:
            capabilities.append(
                replace(
                    candidate,
                    id=current.id,
                    status=ToolCapabilityStatus.UNAVAILABLE,
                    created_at=current.created_at,
                )
            )
            schema_changed += 1
            continue
        metadata_changed = (
            current.display_name != candidate.display_name
            or current.description != candidate.description
        )
        was_unavailable = current.status is ToolCapabilityStatus.UNAVAILABLE
        capabilities.append(
            replace(
                candidate,
                id=current.id,
                created_at=current.created_at,
            )
        )
        updated += int(metadata_changed)
        reactivated += int(was_unavailable)

    for current in existing:
        if current.remote_name in seen:
            continue
        capabilities.append(
            replace(
                current,
                status=ToolCapabilityStatus.UNAVAILABLE,
                updated_at=(
                    synchronized_at
                    if current.status is not ToolCapabilityStatus.UNAVAILABLE
                    else current.updated_at
                ),
            )
        )
        removed += int(current.status is not ToolCapabilityStatus.UNAVAILABLE)

    return ExternalMcpSyncResult(
        source=replace(
            source,
            status=McpSourceStatus.READY,
            updated_at=synchronized_at,
        ),
        capabilities=tuple(capabilities),
        added=added,
        updated=updated,
        schema_changed=schema_changed,
        removed=removed,
        reactivated=reactivated,
    )


__all__ = [
    "EXTERNAL_MCP_MAX_TOOLS",
    "ExternalMcpSnapshot",
    "ExternalMcpSourceCommand",
    "ExternalMcpSyncResult",
    "ExternalMcpValidationError",
    "reconcile_external_capabilities",
]
