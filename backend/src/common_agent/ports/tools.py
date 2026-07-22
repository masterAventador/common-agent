from __future__ import annotations

from dataclasses import dataclass
from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.tools.models import (
    ToolCatalog,
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTargetType,
)


@dataclass(frozen=True, slots=True)
class ToolGrantResolution:
    capability_ids: tuple[UUID, ...]
    missing_collection_ids: tuple[UUID, ...] = ()
    unavailable_capability_ids: tuple[UUID, ...] = ()


class ToolRepository(Protocol):
    async def catalog(self) -> ToolCatalog: ...

    async def target_exists(self, target_type: ToolGrantTargetType, target_id: UUID) -> bool: ...

    async def grants(
        self,
        target_type: ToolGrantTargetType,
        target_id: UUID,
    ) -> ToolGrantSnapshot: ...

    async def resolve(self, selection: ToolGrantSelection) -> ToolGrantResolution: ...

    async def replace_grants(self, snapshot: ToolGrantSnapshot) -> None: ...


class ToolUnitOfWork(Protocol):
    @property
    def tools(self) -> ToolRepository: ...

    async def __aenter__(self) -> ToolUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class ToolUnitOfWorkFactory(Protocol):
    def __call__(self) -> ToolUnitOfWork: ...


__all__ = [
    "ToolGrantResolution",
    "ToolRepository",
    "ToolUnitOfWork",
    "ToolUnitOfWorkFactory",
]
