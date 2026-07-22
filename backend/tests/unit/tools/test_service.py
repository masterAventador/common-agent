from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from dataclasses import replace
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from common_agent.ports.tools import (
    ToolGrantResolution,
    ToolRepository,
    ToolRuntimeResolution,
)
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolCatalog,
    ToolCollection,
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTarget,
    ToolGrantTargetType,
    ToolRuntimeCapability,
)
from common_agent.tools.service import (
    ToolCapabilityUnavailable,
    ToolCollectionNotFound,
    ToolCollectionResourceNotFound,
    ToolCollectionSourceUnavailable,
    ToolGrantTargetNotFound,
    ToolService,
)


class _Repository(ToolRepository):
    def __init__(self) -> None:
        self.employee_id = uuid4()
        self.conversation_id = uuid4()
        self.source = McpSource.create(
            name="业务系统",
            source_type=McpSourceType.MANAGED_HTTP,
            endpoint_url="https://business.example.com",
            status=McpSourceStatus.READY,
        )
        self.first = ToolCapability.create(
            source_id=self.source.id,
            remote_name="read",
            display_name="读取",
            input_schema={"type": "object"},
        )
        self.capabilities = [self.first]
        self.external_source = McpSource.create(
            name="外部支付",
            source_type=McpSourceType.EXTERNAL,
            endpoint_url="https://mcp.partner.example/mcp",
            status=McpSourceStatus.DRAFT,
        )
        self.sources = [self.source, self.external_source]
        self.collection = ToolCollection.create(
            name="业务工具集",
            source_ids=(self.source.id,),
        )
        self.snapshots: dict[tuple[ToolGrantTargetType, UUID], ToolGrantSnapshot] = {}

    async def catalog(self) -> ToolCatalog:
        return ToolCatalog(
            sources=tuple(self.sources),
            capabilities=tuple(self.capabilities),
            collections=(self.collection,),
        )

    async def get_collection(self, collection_id: UUID) -> ToolCollection | None:
        return self.collection if self.collection.id == collection_id else None

    async def collection_name_exists(
        self,
        name: str,
        excluding: UUID | None = None,
    ) -> bool:
        return self.collection.name == name and self.collection.id != excluding

    async def selectable_source_ids(self, source_ids: tuple[UUID, ...]) -> tuple[UUID, ...]:
        known = {
            source.id
            for source in self.sources
            if source.source_type is not McpSourceType.PLATFORM
        }
        return tuple(source_id for source_id in source_ids if source_id in known)

    async def add_collection(self, collection: ToolCollection) -> None:
        self.collection = collection

    async def update_collection(self, collection: ToolCollection) -> None:
        self.collection = collection

    async def delete_collection(self, collection_id: UUID) -> None:
        if self.collection.id == collection_id:
            self.collection = replace(
                self.collection,
                id=uuid4(),
                name="deleted-placeholder",
            )

    async def target_exists(self, target_type: ToolGrantTargetType, target_id: UUID) -> bool:
        expected = (
            self.employee_id
            if target_type is ToolGrantTargetType.EMPLOYEE
            else self.conversation_id
        )
        return target_id == expected

    async def grants(
        self, target_type: ToolGrantTargetType, target_id: UUID
    ) -> ToolGrantSnapshot:
        return self.snapshots.get(
            (target_type, target_id),
            ToolGrantSnapshot(target_type=target_type, target_id=target_id),
        )

    async def resolve(self, selection: ToolGrantSelection) -> ToolGrantResolution:
        known_collections = {self.collection.id}
        missing_collections = tuple(
            value for value in selection.collection_ids if value not in known_collections
        )
        known_capabilities = {value.id for value in self.capabilities}
        missing_capabilities = tuple(
            value for value in selection.capability_ids if value not in known_capabilities
        )
        expanded = {
            value.id
            for value in self.capabilities
            if self.collection.id in selection.collection_ids
            and value.source_id in self.collection.source_ids
        }
        expanded.update(value for value in selection.capability_ids if value in known_capabilities)
        return ToolGrantResolution(
            capability_ids=tuple(sorted(expanded, key=str)),
            missing_collection_ids=missing_collections,
            unavailable_capability_ids=missing_capabilities,
        )

    async def replace_grants(self, snapshot: ToolGrantSnapshot) -> None:
        self.snapshots[(snapshot.target_type, snapshot.target_id)] = snapshot

    async def runtime_capabilities(
        self,
        target: ToolGrantTarget,
        capability_ids: tuple[UUID, ...],
    ) -> ToolRuntimeResolution:
        if not await self.target_exists(target.target_type, target.target_id):
            return ToolRuntimeResolution((), capability_ids)
        by_id = {capability.id: capability for capability in self.capabilities}
        resolved = tuple(
            ToolRuntimeCapability(self.source, by_id[capability_id])
            for capability_id in capability_ids
            if capability_id in by_id
        )
        missing = tuple(
            capability_id for capability_id in capability_ids if capability_id not in by_id
        )
        return ToolRuntimeResolution(resolved, missing)


class _UnitOfWork(AbstractAsyncContextManager["_UnitOfWork"]):
    def __init__(self, repository: _Repository) -> None:
        self.tools: ToolRepository = repository
        self.committed = False

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.committed = True


def test_collection_selection_is_expanded_once_and_new_capabilities_do_not_auto_grant() -> None:
    repository = _Repository()
    units: list[_UnitOfWork] = []

    def factory() -> _UnitOfWork:
        unit = _UnitOfWork(repository)
        units.append(unit)
        return unit

    service = ToolService(factory)

    async def exercise() -> None:
        prepared = await service.prepare_conversation_grants(
            uuid4(),
            ToolGrantSelection(collection_ids=(repository.collection.id,)),
        )
        assert prepared.capability_ids == (repository.first.id,)
        assert repository.snapshots == {}

        saved = await service.replace_employee_grants(
            repository.employee_id,
            ToolGrantSelection(collection_ids=(repository.collection.id,)),
        )
        assert saved.capability_ids == (repository.first.id,)
        assert saved.collection_ids == (repository.collection.id,)

        second = ToolCapability.create(
            source_id=repository.source.id,
            remote_name="delete",
            display_name="删除",
            input_schema={"type": "object"},
        )
        repository.capabilities.append(second)

        restored = await service.employee_grants(repository.employee_id)
        assert restored.capability_ids == (repository.first.id,)
        assert second.id not in restored.capability_ids

        refreshed = await service.replace_employee_grants(
            repository.employee_id,
            ToolGrantSelection(collection_ids=(repository.collection.id,)),
        )
        assert set(refreshed.capability_ids) == {repository.first.id, second.id}

    asyncio.run(exercise())
    assert not units[0].committed
    assert all(unit.committed for unit in (units[1], units[-1]))


def test_conversation_grants_and_invalid_selection_fail_closed() -> None:
    repository = _Repository()
    service = ToolService(lambda: _UnitOfWork(repository))

    async def exercise() -> None:
        saved = await service.replace_conversation_grants(
            repository.conversation_id,
            ToolGrantSelection(capability_ids=(repository.first.id,)),
        )
        assert saved.target_type is ToolGrantTargetType.CONVERSATION
        assert saved.capability_ids == (repository.first.id,)

        with pytest.raises(ToolGrantTargetNotFound):
            await service.employee_grants(uuid4())
        with pytest.raises(ToolCollectionNotFound):
            await service.replace_employee_grants(
                repository.employee_id,
                ToolGrantSelection(collection_ids=(uuid4(),)),
            )
        with pytest.raises(ToolCapabilityUnavailable):
            await service.replace_employee_grants(
                repository.employee_id,
                ToolGrantSelection(capability_ids=(uuid4(),)),
            )

    asyncio.run(exercise())


def test_existing_unavailable_grant_can_be_preserved_or_explicitly_revoked() -> None:
    repository = _Repository()
    service = ToolService(lambda: _UnitOfWork(repository))

    async def exercise() -> None:
        await service.replace_employee_grants(
            repository.employee_id,
            ToolGrantSelection(capability_ids=(repository.first.id,)),
        )
        repository.capabilities.clear()

        preserved = await service.replace_employee_grants(
            repository.employee_id,
            ToolGrantSelection(capability_ids=(repository.first.id,)),
        )
        assert preserved.capability_ids == (repository.first.id,)

        revoked = await service.replace_employee_grants(
            repository.employee_id,
            ToolGrantSelection(),
        )
        assert revoked.capability_ids == ()

        with pytest.raises(ToolCapabilityUnavailable):
            await service.replace_employee_grants(
                repository.employee_id,
                ToolGrantSelection(capability_ids=(uuid4(),)),
            )

    asyncio.run(exercise())


def test_collection_management_aggregates_multiple_sources_without_rewriting_saved_grants() -> None:
    repository = _Repository()
    service = ToolService(lambda: _UnitOfWork(repository))

    async def exercise() -> None:
        saved = await service.replace_employee_grants(
            repository.employee_id,
            ToolGrantSelection(capability_ids=(repository.first.id,)),
        )
        collection = await service.create_collection(
            name="订单与支付",
            description="聚合平台托管与外部 MCP",
            source_ids=(repository.source.id, repository.external_source.id),
        )
        assert collection.source_ids == (
            repository.source.id,
            repository.external_source.id,
        )

        updated = await service.update_collection(
            collection.id,
            name="核心业务工具",
            description="只保留外部支付来源",
            source_ids=(repository.external_source.id,),
        )
        assert updated.id == collection.id
        assert updated.created_at == collection.created_at
        assert updated.source_ids == (repository.external_source.id,)
        assert await service.employee_grants(repository.employee_id) == saved

        with pytest.raises(ToolCollectionSourceUnavailable):
            await service.update_collection(
                collection.id,
                name="非法来源",
                description="",
                source_ids=(uuid4(),),
            )

        missing_id = uuid4()
        with pytest.raises(ToolCollectionResourceNotFound):
            await service.update_collection(
                missing_id,
                name="不存在",
                description="",
                source_ids=(repository.source.id,),
            )
        with pytest.raises(ToolCollectionResourceNotFound):
            await service.delete_collection(missing_id)

    asyncio.run(exercise())
