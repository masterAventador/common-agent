from __future__ import annotations

import asyncio
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from uuid import UUID, uuid4

import pytest

from common_agent.ports.managed_http import (
    ManagedHttpRepository,
    ManagedHttpRepositoryConflict,
)
from common_agent.tools.managed_http import (
    ManagedHttpCapability,
    ManagedHttpCapabilityCommand,
    ManagedHttpParameterBinding,
    ManagedHttpParameterLocation,
    ManagedHttpRuntimeSnapshot,
    ManagedHttpSourceCommand,
    ManagedHttpValidationError,
)
from common_agent.tools.managed_http_service import (
    ManagedHttpCapabilityNotFound,
    ManagedHttpConflict,
    ManagedHttpService,
    ManagedHttpSourceNotFound,
)
from common_agent.tools.models import McpSource, McpSourceStatus, ToolCapabilityStatus


def _capability_command(name: str = "orders.get") -> ManagedHttpCapabilityCommand:
    return ManagedHttpCapabilityCommand(
        remote_name=name,
        display_name="查询订单",
        description="按订单号查询订单。",
        input_schema={
            "type": "object",
            "properties": {
                "order_id": {"type": "string", "description": "订单编号"},
            },
            "required": ["order_id"],
            "additionalProperties": False,
        },
        method="GET",
        path_template="/orders/{order_id}",
        parameter_bindings=(
            ManagedHttpParameterBinding(
                argument_name="order_id",
                location=ManagedHttpParameterLocation.PATH,
                target_name="order_id",
            ),
        ),
        timeout_seconds=10,
        response_json_pointer="/data",
        enabled=True,
    )


class _Repository:
    def __init__(self) -> None:
        self.sources: dict[UUID, McpSource] = {}
        self.capabilities: dict[UUID, ManagedHttpCapability] = {}
        self.source_in_use = False
        self.capability_in_use = False
        self.write_conflict = False

    async def list_sources(self) -> tuple[ManagedHttpRuntimeSnapshot, ...]:
        snapshots = [
            await self.snapshot(source_id) for source_id in sorted(self.sources, key=str)
        ]
        return tuple(snapshot for snapshot in snapshots if snapshot is not None)

    async def snapshot(self, source_id: UUID) -> ManagedHttpRuntimeSnapshot | None:
        source = self.sources.get(source_id)
        if source is None:
            return None
        return ManagedHttpRuntimeSnapshot(
            source,
            tuple(
                item
                for item in self.capabilities.values()
                if item.capability.source_id == source_id
            ),
        )

    async def source_name_exists(self, name: str, excluding: UUID | None = None) -> bool:
        return any(
            source.name == name and source.id != excluding
            for source in self.sources.values()
        )

    async def capability_name_exists(
        self,
        source_id: UUID,
        name: str,
        excluding: UUID | None = None,
    ) -> bool:
        return any(
            item.capability.source_id == source_id
            and item.capability.remote_name == name
            and item.capability.id != excluding
            for item in self.capabilities.values()
        )

    async def add_source(self, source: McpSource) -> None:
        if self.write_conflict:
            raise ManagedHttpRepositoryConflict
        self.sources[source.id] = source

    async def update_source(self, source: McpSource) -> None:
        if self.write_conflict:
            raise ManagedHttpRepositoryConflict
        self.sources[source.id] = source

    async def delete_source(self, source_id: UUID) -> bool:
        if self.source_in_use:
            return False
        del self.sources[source_id]
        self.capabilities = {
            key: value
            for key, value in self.capabilities.items()
            if value.capability.source_id != source_id
        }
        return True

    async def add_capability(self, capability: ManagedHttpCapability) -> None:
        if self.write_conflict:
            raise ManagedHttpRepositoryConflict
        self.capabilities[capability.capability.id] = capability

    async def add_capabilities(
        self,
        capabilities: tuple[ManagedHttpCapability, ...],
    ) -> None:
        if self.write_conflict:
            raise ManagedHttpRepositoryConflict
        self.capabilities.update(
            {capability.capability.id: capability for capability in capabilities}
        )

    async def update_capability(self, capability: ManagedHttpCapability) -> None:
        if self.write_conflict:
            raise ManagedHttpRepositoryConflict
        self.capabilities[capability.capability.id] = capability

    async def delete_capability(self, source_id: UUID, capability_id: UUID) -> bool:
        del source_id
        if self.capability_in_use:
            return False
        del self.capabilities[capability_id]
        return True


class _UnitOfWork(AbstractAsyncContextManager["_UnitOfWork"]):
    def __init__(self, repository: _Repository) -> None:
        self.managed_http: ManagedHttpRepository = repository
        self.commits = 0

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1


def test_service_crud_preserves_stable_ids_and_builds_runtime_snapshot() -> None:
    repository = _Repository()
    units: list[_UnitOfWork] = []

    def factory() -> _UnitOfWork:
        unit = _UnitOfWork(repository)
        units.append(unit)
        return unit

    service = ManagedHttpService(factory)

    async def exercise() -> None:
        created = await service.create_source(
            ManagedHttpSourceCommand(
                name="订单系统",
                description="业务订单接口",
                base_url="https://business.example/api",
                enabled=True,
            )
        )
        assert created.source.status is McpSourceStatus.READY
        assert created.capabilities == ()

        added = await service.add_capability(created.source.id, _capability_command())
        snapshot = await service.snapshot(created.source.id)
        assert snapshot.capabilities == (added,)
        assert added.capability.status is ToolCapabilityStatus.ACTIVE

        changed = await service.update_capability(
            created.source.id,
            added.capability.id,
            _capability_command(),
        )
        assert changed.capability.id == added.capability.id
        assert changed.capability.created_at == added.capability.created_at

        updated = await service.update_source(
            created.source.id,
            ManagedHttpSourceCommand(
                name="订单中心",
                description="更新后的说明",
                base_url="https://business.example/v2",
                enabled=False,
            ),
        )
        assert updated.source.id == created.source.id
        assert updated.source.created_at == created.source.created_at
        assert updated.source.status is McpSourceStatus.DISABLED

        await service.delete_capability(created.source.id, added.capability.id)
        await service.delete_source(created.source.id)
        assert await service.list_sources() == ()

    asyncio.run(exercise())
    assert all(unit.commits == 1 for unit in units if unit.commits)


def test_service_rejects_missing_conflicting_and_referenced_resources() -> None:
    repository = _Repository()
    service = ManagedHttpService(lambda: _UnitOfWork(repository))

    async def exercise() -> None:
        source = await service.create_source(
            ManagedHttpSourceCommand(
                name="订单系统",
                description="",
                base_url="https://business.example/api",
                enabled=True,
            )
        )
        with pytest.raises(ManagedHttpConflict):
            await service.create_source(
                ManagedHttpSourceCommand(
                    name="订单系统",
                    description="重复",
                    base_url="https://other.example/api",
                    enabled=True,
                )
            )
        capability = await service.add_capability(
            source.source.id,
            _capability_command(),
        )
        with pytest.raises(ManagedHttpConflict):
            await service.add_capability(source.source.id, _capability_command())

        repository.capability_in_use = True
        with pytest.raises(ManagedHttpConflict):
            await service.delete_capability(source.source.id, capability.capability.id)
        repository.source_in_use = True
        with pytest.raises(ManagedHttpConflict):
            await service.delete_source(source.source.id)

        with pytest.raises(ManagedHttpSourceNotFound):
            await service.snapshot(uuid4())
        with pytest.raises(ManagedHttpCapabilityNotFound):
            await service.update_capability(source.source.id, uuid4(), _capability_command())

    asyncio.run(exercise())


def test_service_atomically_imports_a_validated_capability_batch_in_one_commit() -> None:
    repository = _Repository()
    units: list[_UnitOfWork] = []

    def factory() -> _UnitOfWork:
        unit = _UnitOfWork(repository)
        units.append(unit)
        return unit

    service = ManagedHttpService(factory)

    async def exercise() -> None:
        source = await service.create_source(
            ManagedHttpSourceCommand(
                name="订单系统",
                description="",
                base_url="https://business.example/api",
                enabled=True,
            )
        )
        units.clear()
        imported = await service.import_capabilities(
            source.source.id,
            (_capability_command("orders.get"), _capability_command("orders.list")),
        )

        assert [item.capability.remote_name for item in imported] == [
            "orders.get",
            "orders.list",
        ]
        assert len(repository.capabilities) == 2
        assert len(units) == 1
        assert units[0].commits == 1

    asyncio.run(exercise())


def test_service_validates_the_whole_import_before_writing_any_capability() -> None:
    repository = _Repository()
    service = ManagedHttpService(lambda: _UnitOfWork(repository))
    invalid = ManagedHttpCapabilityCommand(
        remote_name="orders.invalid",
        display_name="非法能力",
        description="描述",
        input_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
        method="GET",
        path_template="/orders/{order_id}",
        parameter_bindings=(
            ManagedHttpParameterBinding(
                argument_name="order_id",
                location=ManagedHttpParameterLocation.PATH,
                target_name="order_id",
            ),
        ),
        timeout_seconds=10,
        response_json_pointer=None,
        enabled=True,
    )

    async def exercise() -> None:
        source = await service.create_source(
            ManagedHttpSourceCommand(
                name="订单系统",
                description="",
                base_url="https://business.example/api",
                enabled=True,
            )
        )
        with pytest.raises(ManagedHttpValidationError):
            await service.import_capabilities(
                source.source.id,
                (_capability_command("orders.get"), invalid),
            )
        assert repository.capabilities == {}

        with pytest.raises(ManagedHttpConflict):
            await service.import_capabilities(
                source.source.id,
                (_capability_command("orders.get"), _capability_command("orders.get")),
            )
        assert repository.capabilities == {}

        await service.add_capability(source.source.id, _capability_command("orders.get"))
        with pytest.raises(ManagedHttpConflict):
            await service.import_capabilities(
                source.source.id,
                (_capability_command("orders.list"), _capability_command("orders.get")),
            )
        assert len(repository.capabilities) == 1

    asyncio.run(exercise())


def test_service_rejects_selected_openapi_capabilities_with_nested_missing_descriptions() -> None:
    repository = _Repository()
    service = ManagedHttpService(lambda: _UnitOfWork(repository))
    nested_missing = ManagedHttpCapabilityCommand(
        remote_name="orders.create",
        display_name="创建订单",
        description="创建订单。",
        input_schema={
            "type": "object",
            "properties": {
                "detail": {
                    "type": "object",
                    "description": "订单明细",
                    "properties": {"sku": {"type": "string"}},
                }
            },
        },
        method="POST",
        path_template="/orders",
        parameter_bindings=(
            ManagedHttpParameterBinding(
                argument_name="detail",
                location=ManagedHttpParameterLocation.BODY,
                target_name="detail",
            ),
        ),
        timeout_seconds=10,
        response_json_pointer=None,
        enabled=True,
    )

    async def exercise() -> None:
        source = await service.create_source(
            ManagedHttpSourceCommand(
                name="订单系统",
                description="",
                base_url="https://business.example/api",
                enabled=True,
            )
        )
        with pytest.raises(ManagedHttpValidationError, match="sku"):
            await service.import_capabilities(source.source.id, (nested_missing,))
        assert repository.capabilities == {}

    asyncio.run(exercise())


def test_service_maps_storage_races_and_checks_source_before_capability_shape() -> None:
    repository = _Repository()
    service = ManagedHttpService(lambda: _UnitOfWork(repository))

    async def exercise() -> None:
        invalid = _capability_command()
        object.__setattr__(invalid, "method", "TRACE")
        with pytest.raises(ManagedHttpSourceNotFound):
            await service.add_capability(uuid4(), invalid)

        repository.write_conflict = True
        with pytest.raises(ManagedHttpConflict):
            await service.create_source(
                ManagedHttpSourceCommand(
                    name="订单系统",
                    description="",
                    base_url="https://business.example/api",
                    enabled=True,
                )
            )

    asyncio.run(exercise())
