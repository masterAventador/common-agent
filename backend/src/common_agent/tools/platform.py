from __future__ import annotations

from dataclasses import dataclass
from uuid import NAMESPACE_URL, UUID, uuid5

from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
)

PLATFORM_MCP_SOURCE_NAME = "平台内置 MCP"
PLATFORM_MCP_SOURCE_DESCRIPTION = "common-agent 平台维护的零外部依赖 MCP 能力。"
CURRENT_TIME_TOOL_NAME = "current_time"
CURRENT_TIME_DISPLAY_NAME = "当前时间"
CURRENT_TIME_DESCRIPTION = (
    "获取当前真实时间。可传入 UTC 偏移量(例如 +08:00),默认使用 +08:00;"
    "不访问外部服务、文件或收费 API。"
)
CURRENT_TIME_INPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "utc_offset": {
            "type": "string",
            "description": "UTC 偏移量,格式为 +08:00;范围 -14:00 到 +14:00。",
            "default": "+08:00",
            "pattern": r"^[+-](?:0\d|1[0-4]):[0-5]\d$",
        }
    },
    "additionalProperties": False,
}
CURRENT_TIME_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "iso8601": {"type": "string"},
        "unix_timestamp": {"type": "integer"},
        "utc_offset": {"type": "string"},
    },
    "required": ["iso8601", "unix_timestamp", "utc_offset"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class PlatformToolCatalogSeed:
    source: McpSource
    current_time: ToolCapability


def platform_mcp_source_id(tenant_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"common-agent:tenant:{tenant_id}:platform-mcp")


def current_time_capability_id(tenant_id: UUID) -> UUID:
    return uuid5(NAMESPACE_URL, f"common-agent:tenant:{tenant_id}:platform-mcp:current-time")


def platform_tool_catalog_seed(tenant_id: UUID) -> PlatformToolCatalogSeed:
    source = McpSource.create(
        source_id=platform_mcp_source_id(tenant_id),
        name=PLATFORM_MCP_SOURCE_NAME,
        description=PLATFORM_MCP_SOURCE_DESCRIPTION,
        source_type=McpSourceType.PLATFORM,
        status=McpSourceStatus.READY,
    )
    return PlatformToolCatalogSeed(
        source=source,
        current_time=ToolCapability.create(
            capability_id=current_time_capability_id(tenant_id),
            source_id=source.id,
            remote_name=CURRENT_TIME_TOOL_NAME,
            display_name=CURRENT_TIME_DISPLAY_NAME,
            description=CURRENT_TIME_DESCRIPTION,
            input_schema=CURRENT_TIME_INPUT_SCHEMA,
        ),
    )


__all__ = [
    "CURRENT_TIME_DESCRIPTION",
    "CURRENT_TIME_DISPLAY_NAME",
    "CURRENT_TIME_INPUT_SCHEMA",
    "CURRENT_TIME_OUTPUT_SCHEMA",
    "CURRENT_TIME_TOOL_NAME",
    "PLATFORM_MCP_SOURCE_DESCRIPTION",
    "PLATFORM_MCP_SOURCE_NAME",
    "PlatformToolCatalogSeed",
    "current_time_capability_id",
    "platform_mcp_source_id",
    "platform_tool_catalog_seed",
]
