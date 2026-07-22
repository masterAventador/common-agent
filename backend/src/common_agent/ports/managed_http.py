from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpRuntimeSnapshot,
)
from common_agent.tools.models import McpSource


class ManagedHttpRepositoryConflict(Exception):
    """Raised when a concurrent write violates a managed MCP constraint."""


class ManagedHttpRepository(Protocol):
    async def list_sources(self) -> tuple[ManagedHttpRuntimeSnapshot, ...]: ...

    async def snapshot(self, source_id: UUID) -> ManagedHttpRuntimeSnapshot | None: ...

    async def source_name_exists(self, name: str, excluding: UUID | None = None) -> bool: ...

    async def capability_name_exists(
        self,
        source_id: UUID,
        name: str,
        excluding: UUID | None = None,
    ) -> bool: ...

    async def add_source(self, source: McpSource) -> None: ...

    async def update_source(self, source: McpSource) -> None: ...

    async def delete_source(self, source_id: UUID) -> bool: ...

    async def add_capability(self, capability: ManagedHttpCapability) -> None: ...

    async def add_capabilities(
        self,
        capabilities: tuple[ManagedHttpCapability, ...],
    ) -> None: ...

    async def update_capability(self, capability: ManagedHttpCapability) -> None: ...

    async def delete_capability(self, source_id: UUID, capability_id: UUID) -> bool: ...


class ManagedHttpUnitOfWork(Protocol):
    @property
    def managed_http(self) -> ManagedHttpRepository: ...

    async def __aenter__(self) -> ManagedHttpUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class ManagedHttpUnitOfWorkFactory(Protocol):
    def __call__(self) -> ManagedHttpUnitOfWork: ...


__all__ = [
    "ManagedHttpRepository",
    "ManagedHttpRepositoryConflict",
    "ManagedHttpUnitOfWork",
    "ManagedHttpUnitOfWorkFactory",
]
