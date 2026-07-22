from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol, runtime_checkable
from uuid import UUID

if TYPE_CHECKING:
    from common_agent.tools.models import McpSource


@dataclass(frozen=True, slots=True)
class McpToolDescriptor:
    name: str
    display_name: str
    description: str
    input_schema: dict[str, object]

    def __post_init__(self) -> None:
        if not self.name or self.name != self.name.strip():
            raise ValueError("MCP 工具名称不合法")
        if not self.display_name or self.display_name != self.display_name.strip():
            raise ValueError("MCP 工具显示名不合法")
        if not isinstance(self.description, str):
            raise ValueError("MCP 工具描述不合法")
        if not isinstance(self.input_schema, dict):
            raise ValueError("MCP 工具输入 Schema 不合法")
        object.__setattr__(self, "input_schema", deepcopy(self.input_schema))


@dataclass(frozen=True, slots=True)
class McpToolCallResponse:
    output: dict[str, object] = field(repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.output, dict):
            raise ValueError("MCP 工具输出不合法")
        object.__setattr__(self, "output", deepcopy(self.output))


class McpToolCallError(RuntimeError):
    def __init__(self, code: str, *, retryable: bool = False) -> None:
        self.code = code
        self.retryable = retryable
        super().__init__(code)


class McpToolClient(Protocol):
    async def list_tools(self) -> Sequence[McpToolDescriptor]: ...

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse: ...


@runtime_checkable
class ManagedMcpToolClient(Protocol):
    async def list_tools(self, source_id: UUID) -> Sequence[McpToolDescriptor]: ...

    async def call_tool(
        self,
        source_id: UUID,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse: ...


@runtime_checkable
class ExternalMcpToolClient(Protocol):
    async def list_tools(self, source: McpSource) -> Sequence[McpToolDescriptor]: ...

    async def call_tool(
        self,
        source: McpSource,
        name: str,
        arguments: Mapping[str, object],
    ) -> McpToolCallResponse: ...


__all__ = [
    "ExternalMcpToolClient",
    "ManagedMcpToolClient",
    "McpToolCallError",
    "McpToolCallResponse",
    "McpToolClient",
    "McpToolDescriptor",
]
