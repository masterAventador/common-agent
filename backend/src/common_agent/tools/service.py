from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

from common_agent.ports.tools import (
    ToolRepository,
    ToolRepositoryConflict,
    ToolUnitOfWorkFactory,
)
from common_agent.tools.models import (
    ToolCatalog,
    ToolCollection,
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTarget,
    ToolGrantTargetType,
    ToolRuntimeCapability,
    ToolValidationError,
)


class ToolServiceError(Exception):
    code: str
    message: str
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


class ToolGrantTargetNotFound(ToolServiceError):
    code = "tool_grant_target_not_found"
    message = "工具授权目标不存在"


class ToolCollectionNotFound(ToolServiceError):
    code = "tool_collection_not_found"
    message = "所选业务工具集不存在"


class ToolCollectionResourceNotFound(ToolServiceError):
    code = "tool_collection_not_found"
    message = "业务工具集不存在"


class ToolCollectionConflict(ToolServiceError):
    code = "tool_collection_conflict"
    message = "业务工具集名称重复或状态已变化"


class ToolCollectionSourceUnavailable(ToolServiceError):
    code = "tool_collection_source_unavailable"
    message = "业务工具集包含不存在或不支持的 MCP 来源"


class ToolCapabilityUnavailable(ToolServiceError):
    code = "tool_capability_unavailable"
    message = "所选工具能力不存在、已停用或来源不可用"


class ToolService:
    def __init__(
        self,
        unit_of_work_factory: ToolUnitOfWorkFactory,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def catalog(self) -> ToolCatalog:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.tools.catalog()

    async def create_collection(
        self,
        *,
        name: str,
        description: str,
        source_ids: tuple[UUID, ...],
    ) -> ToolCollection:
        if not source_ids:
            raise ToolValidationError("source_ids", "必须至少包含一项")
        collection = ToolCollection.create(
            name=name,
            description=description,
            source_ids=source_ids,
            now=self._clock(),
        )
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                if await unit_of_work.tools.collection_name_exists(collection.name):
                    raise ToolCollectionConflict
                await self._require_collection_sources(unit_of_work.tools, source_ids)
                await unit_of_work.tools.add_collection(collection)
                await unit_of_work.commit()
        except ToolRepositoryConflict:
            raise ToolCollectionConflict from None
        return collection

    async def update_collection(
        self,
        collection_id: UUID,
        *,
        name: str,
        description: str,
        source_ids: tuple[UUID, ...],
    ) -> ToolCollection:
        if not source_ids:
            raise ToolValidationError("source_ids", "必须至少包含一项")
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                current = await unit_of_work.tools.get_collection(collection_id)
                if current is None:
                    raise ToolCollectionResourceNotFound
                candidate = ToolCollection.create(
                    name=name,
                    description=description,
                    source_ids=source_ids,
                    collection_id=current.id,
                    now=self._clock(),
                )
                collection = replace(candidate, created_at=current.created_at)
                if await unit_of_work.tools.collection_name_exists(
                    collection.name,
                    collection.id,
                ):
                    raise ToolCollectionConflict
                await self._require_collection_sources(unit_of_work.tools, source_ids)
                await unit_of_work.tools.update_collection(collection)
                await unit_of_work.commit()
        except ToolRepositoryConflict:
            raise ToolCollectionConflict from None
        return collection

    async def delete_collection(self, collection_id: UUID) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                if await unit_of_work.tools.get_collection(collection_id) is None:
                    raise ToolCollectionResourceNotFound
                await unit_of_work.tools.delete_collection(collection_id)
                await unit_of_work.commit()
        except ToolRepositoryConflict:
            raise ToolCollectionConflict from None

    async def employee_grants(self, employee_id: UUID) -> ToolGrantSnapshot:
        return await self._grants(ToolGrantTargetType.EMPLOYEE, employee_id)

    async def conversation_grants(self, conversation_id: UUID) -> ToolGrantSnapshot:
        return await self._grants(ToolGrantTargetType.CONVERSATION, conversation_id)

    async def replace_employee_grants(
        self,
        employee_id: UUID,
        selection: ToolGrantSelection,
    ) -> ToolGrantSnapshot:
        return await self._replace_grants(
            ToolGrantTargetType.EMPLOYEE,
            employee_id,
            selection,
        )

    async def replace_conversation_grants(
        self,
        conversation_id: UUID,
        selection: ToolGrantSelection,
    ) -> ToolGrantSnapshot:
        return await self._replace_grants(
            ToolGrantTargetType.CONVERSATION,
            conversation_id,
            selection,
        )

    async def authorized_runtime_capabilities(
        self,
        target: ToolGrantTarget,
        capability_ids: tuple[UUID, ...],
    ) -> tuple[ToolRuntimeCapability, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            resolution = await unit_of_work.tools.runtime_capabilities(target, capability_ids)
        if resolution.missing_capability_ids:
            raise ToolCapabilityUnavailable
        return resolution.capabilities

    async def _grants(
        self,
        target_type: ToolGrantTargetType,
        target_id: UUID,
    ) -> ToolGrantSnapshot:
        async with self._unit_of_work_factory() as unit_of_work:
            if not await unit_of_work.tools.target_exists(target_type, target_id):
                raise ToolGrantTargetNotFound
            return await unit_of_work.tools.grants(target_type, target_id)

    async def _replace_grants(
        self,
        target_type: ToolGrantTargetType,
        target_id: UUID,
        selection: ToolGrantSelection,
    ) -> ToolGrantSnapshot:
        async with self._unit_of_work_factory() as unit_of_work:
            if not await unit_of_work.tools.target_exists(target_type, target_id):
                raise ToolGrantTargetNotFound
            resolved = await unit_of_work.tools.resolve(selection)
            if resolved.missing_collection_ids:
                raise ToolCollectionNotFound
            if resolved.unavailable_capability_ids:
                raise ToolCapabilityUnavailable
            snapshot = ToolGrantSnapshot(
                target_type=target_type,
                target_id=target_id,
                collection_ids=selection.collection_ids,
                capability_ids=resolved.capability_ids,
            )
            await unit_of_work.tools.replace_grants(snapshot)
            await unit_of_work.commit()
            return snapshot

    @staticmethod
    async def _require_collection_sources(
        repository: ToolRepository,
        source_ids: tuple[UUID, ...],
    ) -> None:
        found = await repository.selectable_source_ids(source_ids)
        if set(found) != set(source_ids):
            raise ToolCollectionSourceUnavailable


__all__ = [
    "ToolCapabilityUnavailable",
    "ToolCollectionConflict",
    "ToolCollectionNotFound",
    "ToolCollectionResourceNotFound",
    "ToolCollectionSourceUnavailable",
    "ToolGrantTargetNotFound",
    "ToolService",
    "ToolServiceError",
]
