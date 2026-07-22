from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.tools.external_mcp import (
    ExternalMcpSnapshot,
    ExternalMcpSyncResult,
)
from common_agent.tools.models import McpSource


class ExternalMcpRepositoryConflict(Exception):
    """Raised when an external MCP catalog write loses a concurrent race."""


class ExternalMcpRepository(Protocol):
    async def list_sources(self) -> tuple[ExternalMcpSnapshot, ...]: ...

    async def snapshot(
        self,
        source_id: UUID,
        *,
        for_update: bool = False,
    ) -> ExternalMcpSnapshot | None: ...

    async def source_name_exists(self, name: str, excluding: UUID | None = None) -> bool: ...

    async def add_source(self, source: McpSource) -> None: ...

    async def update_source(self, source: McpSource) -> None: ...

    async def clear_credential(self, source_id: UUID) -> None: ...

    async def apply_sync(self, result: ExternalMcpSyncResult) -> None: ...

    async def delete_source(self, source_id: UUID) -> bool: ...


class ExternalMcpUnitOfWork(Protocol):
    @property
    def external_mcp(self) -> ExternalMcpRepository: ...

    async def __aenter__(self) -> ExternalMcpUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class ExternalMcpUnitOfWorkFactory(Protocol):
    def __call__(self) -> ExternalMcpUnitOfWork: ...


__all__ = [
    "ExternalMcpRepository",
    "ExternalMcpRepositoryConflict",
    "ExternalMcpUnitOfWork",
    "ExternalMcpUnitOfWorkFactory",
]
