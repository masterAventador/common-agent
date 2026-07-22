from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from common_agent.ports.tools import ToolGrantResolution, ToolRepository
from common_agent.tools.models import (
    McpSource,
    McpSourceStatus,
    McpSourceType,
    ToolCapability,
    ToolCatalog,
    ToolCollection,
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTargetType,
)
from common_agent.tools.service import (
    ToolCapabilityUnavailable,
    ToolCollectionNotFound,
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
        self.collection = ToolCollection.create(
            name="业务工具集",
            source_ids=(self.source.id,),
        )
        self.snapshots: dict[tuple[ToolGrantTargetType, UUID], ToolGrantSnapshot] = {}

    async def catalog(self) -> ToolCatalog:
        return ToolCatalog(
            sources=(self.source,),
            capabilities=tuple(self.capabilities),
            collections=(self.collection,),
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
    assert all(unit.committed for unit in (units[0], units[-1]))


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
