from __future__ import annotations

from uuid import UUID

from common_agent.ports.managed_http import (
    ManagedHttpRepositoryConflict,
    ManagedHttpUnitOfWorkFactory,
)
from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpCapabilityCommand,
    ManagedHttpRuntimeSnapshot,
    ManagedHttpSourceCommand,
)


class ManagedHttpServiceError(Exception):
    code: str
    message: str
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


class ManagedHttpSourceNotFound(ManagedHttpServiceError):
    code = "managed_mcp_source_not_found"
    message = "托管 MCP 来源不存在"


class ManagedHttpCapabilityNotFound(ManagedHttpServiceError):
    code = "managed_mcp_capability_not_found"
    message = "托管 MCP 能力不存在"


class ManagedHttpConflict(ManagedHttpServiceError):
    code = "managed_mcp_conflict"
    message = "托管 MCP 名称重复或资源仍被引用"


class ManagedHttpService:
    def __init__(self, unit_of_work_factory: ManagedHttpUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def list_sources(self) -> tuple[ManagedHttpRuntimeSnapshot, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.managed_http.list_sources()

    async def snapshot(self, source_id: UUID) -> ManagedHttpRuntimeSnapshot:
        async with self._unit_of_work_factory() as unit_of_work:
            snapshot = await unit_of_work.managed_http.snapshot(source_id)
        if snapshot is None:
            raise ManagedHttpSourceNotFound
        return snapshot

    async def create_source(
        self,
        command: ManagedHttpSourceCommand,
    ) -> ManagedHttpRuntimeSnapshot:
        source = command.create()
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                if await unit_of_work.managed_http.source_name_exists(source.name):
                    raise ManagedHttpConflict
                await unit_of_work.managed_http.add_source(source)
                await unit_of_work.commit()
        except ManagedHttpRepositoryConflict:
            raise ManagedHttpConflict from None
        return ManagedHttpRuntimeSnapshot(source, ())

    async def update_source(
        self,
        source_id: UUID,
        command: ManagedHttpSourceCommand,
    ) -> ManagedHttpRuntimeSnapshot:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                snapshot = await unit_of_work.managed_http.snapshot(source_id)
                if snapshot is None:
                    raise ManagedHttpSourceNotFound
                source = command.replace(snapshot.source)
                if await unit_of_work.managed_http.source_name_exists(source.name, source.id):
                    raise ManagedHttpConflict
                await unit_of_work.managed_http.update_source(source)
                await unit_of_work.commit()
        except ManagedHttpRepositoryConflict:
            raise ManagedHttpConflict from None
        return ManagedHttpRuntimeSnapshot(source, snapshot.capabilities)

    async def delete_source(self, source_id: UUID) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                if await unit_of_work.managed_http.snapshot(source_id) is None:
                    raise ManagedHttpSourceNotFound
                if not await unit_of_work.managed_http.delete_source(source_id):
                    raise ManagedHttpConflict
                await unit_of_work.commit()
        except ManagedHttpRepositoryConflict:
            raise ManagedHttpConflict from None

    async def add_capability(
        self,
        source_id: UUID,
        command: ManagedHttpCapabilityCommand,
    ) -> ManagedHttpCapability:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                if await unit_of_work.managed_http.snapshot(source_id) is None:
                    raise ManagedHttpSourceNotFound
                capability = command.create(source_id)
                if await unit_of_work.managed_http.capability_name_exists(
                    source_id,
                    capability.capability.remote_name,
                ):
                    raise ManagedHttpConflict
                await unit_of_work.managed_http.add_capability(capability)
                await unit_of_work.commit()
        except ManagedHttpRepositoryConflict:
            raise ManagedHttpConflict from None
        return capability

    async def update_capability(
        self,
        source_id: UUID,
        capability_id: UUID,
        command: ManagedHttpCapabilityCommand,
    ) -> ManagedHttpCapability:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                snapshot = await unit_of_work.managed_http.snapshot(source_id)
                if snapshot is None:
                    raise ManagedHttpSourceNotFound
                existing = next(
                    (
                        item
                        for item in snapshot.capabilities
                        if item.capability.id == capability_id
                    ),
                    None,
                )
                if existing is None:
                    raise ManagedHttpCapabilityNotFound
                capability = command.replace(existing)
                if await unit_of_work.managed_http.capability_name_exists(
                    source_id,
                    capability.capability.remote_name,
                    capability_id,
                ):
                    raise ManagedHttpConflict
                await unit_of_work.managed_http.update_capability(capability)
                await unit_of_work.commit()
        except ManagedHttpRepositoryConflict:
            raise ManagedHttpConflict from None
        return capability

    async def delete_capability(self, source_id: UUID, capability_id: UUID) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                snapshot = await unit_of_work.managed_http.snapshot(source_id)
                if snapshot is None:
                    raise ManagedHttpSourceNotFound
                if all(item.capability.id != capability_id for item in snapshot.capabilities):
                    raise ManagedHttpCapabilityNotFound
                if not await unit_of_work.managed_http.delete_capability(
                    source_id,
                    capability_id,
                ):
                    raise ManagedHttpConflict
                await unit_of_work.commit()
        except ManagedHttpRepositoryConflict:
            raise ManagedHttpConflict from None


__all__ = [
    "ManagedHttpCapabilityNotFound",
    "ManagedHttpConflict",
    "ManagedHttpService",
    "ManagedHttpServiceError",
    "ManagedHttpSourceNotFound",
]
