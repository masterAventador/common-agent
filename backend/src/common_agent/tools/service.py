from __future__ import annotations

from uuid import UUID

from common_agent.ports.tools import ToolUnitOfWorkFactory
from common_agent.tools.models import (
    ToolCatalog,
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTargetType,
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


class ToolCapabilityUnavailable(ToolServiceError):
    code = "tool_capability_unavailable"
    message = "所选工具能力不存在、已停用或来源不可用"


class ToolService:
    def __init__(self, unit_of_work_factory: ToolUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def catalog(self) -> ToolCatalog:
        async with self._unit_of_work_factory() as unit_of_work:
            return await unit_of_work.tools.catalog()

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


__all__ = [
    "ToolCapabilityUnavailable",
    "ToolCollectionNotFound",
    "ToolGrantTargetNotFound",
    "ToolService",
    "ToolServiceError",
]
