from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from common_agent.application.resource_locks import (
    ResourceMutationGuard,
    model_configuration_resource,
)
from common_agent.domain.model_configuration import (
    ModelConfiguration,
    ModelConfigurationInput,
    ModelProvider,
)
from common_agent.pagination import (
    CursorPage,
    ListPageRequest,
    PageAnchor,
    decode_keyset_cursor,
    encode_keyset_cursor,
)
from common_agent.ports.model_configurations import (
    ModelConfigurationAlreadyExists,
    ModelConfigurationUnitOfWorkFactory,
)


class ModelConfigurationServiceError(Exception):
    code: str
    message: str
    retryable: bool = False

    def __init__(self) -> None:
        super().__init__(self.message)


class ModelConfigurationNotFound(ModelConfigurationServiceError):
    code = "model_configuration_not_found"
    message = "模型配置不存在"


class ModelConfigurationInUse(ModelConfigurationServiceError):
    code = "model_configuration_in_use"
    message = "该模型仍被数字员工或工作流引用，请先解除引用。"  # noqa: RUF001


@dataclass(frozen=True, slots=True)
class ModelConfigurationVerification:
    status: str
    model_identifier: str
    response_preview: str


class ModelConfigurationVerifier(Protocol):
    async def verify(self, model_identifier: str) -> str: ...


class ModelConfigurationService:
    def __init__(
        self,
        unit_of_work_factory: ModelConfigurationUnitOfWorkFactory,
        *,
        verifier: ModelConfigurationVerifier,
        guard: ResourceMutationGuard | None = None,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._verifier = verifier
        self._guard = guard or ResourceMutationGuard()

    async def page(
        self,
        page: ListPageRequest,
        *,
        enabled_only: bool = False,
    ) -> CursorPage[ModelConfiguration]:
        scope = f"model-configurations-{'enabled' if enabled_only else 'all'}"
        after = (
            None
            if page.cursor is None
            else decode_keyset_cursor(
                page.cursor,
                scope=scope,
                search=page.search,
                limit=page.limit,
            )
        )
        async with self._unit_of_work_factory() as unit_of_work:
            result = await unit_of_work.model_configurations.page(
                limit=page.limit,
                search=page.search,
                after=after,
                enabled_only=enabled_only,
            )
        next_cursor = None
        if result.has_more:
            last = result.items[-1]
            next_cursor = encode_keyset_cursor(
                scope=scope,
                search=page.search,
                limit=page.limit,
                anchor=PageAnchor(created_at=last.created_at, id=str(last.id)),
            )
        return CursorPage(items=result.items, next_cursor=next_cursor)

    async def get(self, model_configuration_id: UUID) -> ModelConfiguration:
        async with self._unit_of_work_factory() as unit_of_work:
            result = await unit_of_work.model_configurations.get(model_configuration_id)
        if result is None:
            raise ModelConfigurationNotFound
        return result

    async def get_by_identifier(self, model_identifier: str) -> ModelConfiguration:
        async with self._unit_of_work_factory() as unit_of_work:
            result = await unit_of_work.model_configurations.get_by_identifier(model_identifier)
        if result is None:
            raise ModelConfigurationNotFound
        return result

    async def create(self, value: ModelConfigurationInput) -> ModelConfiguration:
        candidate_id = uuid4()
        async with (
            self._guard.hold(model_configuration_resource(candidate_id)),
            self._unit_of_work_factory() as unit_of_work,
        ):
            streaming_breaks_tool_calls = (
                await unit_of_work.model_configurations.streaming_breaks_tool_calls(
                    ModelProvider.BAILIAN,
                    value.model_identifier,
                )
            )
            candidate = ModelConfiguration.create(
                configuration=value,
                model_configuration_id=candidate_id,
                streaming_breaks_tool_calls=streaming_breaks_tool_calls,
            )
            await unit_of_work.model_configurations.add(candidate)
            await unit_of_work.commit()
        return candidate

    async def ensure(self, value: ModelConfigurationInput) -> ModelConfiguration:
        """幂等地按模型标识预置配置: 已存在则原样返回, 缺失才创建。

        用于默认工作区启动时的常用模型 seed, 重复执行不会重复创建, 也不覆盖
        既有配置的显示名或启用状态。
        """
        async with self._unit_of_work_factory() as unit_of_work:
            existing = await unit_of_work.model_configurations.get_by_identifier(
                value.model_identifier
            )
        if existing is not None:
            return existing
        try:
            return await self.create(value)
        except ModelConfigurationAlreadyExists:
            return await self.get_by_identifier(value.model_identifier)

    async def update(
        self,
        model_configuration_id: UUID,
        value: ModelConfigurationInput,
    ) -> ModelConfiguration:
        async with (
            self._guard.hold(model_configuration_resource(model_configuration_id)),
            self._unit_of_work_factory() as unit_of_work,
        ):
            current = await unit_of_work.model_configurations.get(model_configuration_id)
            if current is None:
                raise ModelConfigurationNotFound
            streaming_breaks_tool_calls = (
                await unit_of_work.model_configurations.streaming_breaks_tool_calls(
                    current.provider,
                    value.model_identifier,
                )
            )
            updated = current.reconfigure(
                value,
                streaming_breaks_tool_calls=streaming_breaks_tool_calls,
            )
            if not await unit_of_work.model_configurations.update(updated):
                raise ModelConfigurationNotFound
            await unit_of_work.commit()
        return updated

    async def delete(self, model_configuration_id: UUID) -> None:
        async with (
            self._guard.hold(model_configuration_resource(model_configuration_id)),
            self._unit_of_work_factory() as unit_of_work,
        ):
            current = await unit_of_work.model_configurations.get(model_configuration_id)
            if current is None:
                raise ModelConfigurationNotFound
            if await unit_of_work.model_configurations.count_references(model_configuration_id):
                raise ModelConfigurationInUse
            if not await unit_of_work.model_configurations.delete(model_configuration_id):
                raise ModelConfigurationNotFound
            await unit_of_work.commit()

    async def verify(
        self,
        model_configuration_id: UUID,
    ) -> ModelConfigurationVerification:
        configuration = await self.get(model_configuration_id)
        preview = (await self._verifier.verify(configuration.model_identifier)).strip()
        return ModelConfigurationVerification(
            status="available",
            model_identifier=configuration.model_identifier,
            response_preview=preview[:200],
        )
