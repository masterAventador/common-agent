from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import TracebackType
from uuid import UUID

import pytest

from common_agent.domain.model_configuration import (
    ModelConfiguration,
    ModelConfigurationInput,
)
from common_agent.model_configurations.service import (
    ModelConfigurationInUse,
    ModelConfigurationNotFound,
    ModelConfigurationService,
)
from common_agent.pagination import ListPageRequest, PageAnchor, PageSlice


def _input(*, enabled: bool = True) -> ModelConfigurationInput:
    return ModelConfigurationInput(
        display_name="Qwen Plus",
        model_identifier="qwen-plus",
        enabled=enabled,
    )


def _configuration(
    value: int,
    *,
    enabled: bool = True,
) -> ModelConfiguration:
    return ModelConfiguration.create(
        configuration=ModelConfigurationInput(
            display_name=f"Qwen {value}",
            model_identifier=f"qwen-{value}",
            enabled=enabled,
        ),
        model_configuration_id=UUID(f"10000000-0000-4000-8000-{value:012d}"),
        now=datetime(2026, 7, 22, tzinfo=UTC) + timedelta(seconds=value),
    )


class FakeRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ModelConfiguration] = {}
        self.references: set[UUID] = set()
        self.page_results: list[PageSlice[ModelConfiguration]] = []
        self.last_after: PageAnchor | None = None
        self.last_enabled_only = False

    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
        enabled_only: bool,
    ) -> PageSlice[ModelConfiguration]:
        del limit, search
        self.last_after = after
        self.last_enabled_only = enabled_only
        if self.page_results:
            return self.page_results.pop(0)
        return PageSlice(items=(), has_more=False)

    async def get(self, configuration_id: UUID) -> ModelConfiguration | None:
        return self.items.get(configuration_id)

    async def add(self, configuration: ModelConfiguration) -> None:
        self.items[configuration.id] = configuration

    async def update(self, configuration: ModelConfiguration) -> bool:
        if configuration.id not in self.items:
            return False
        self.items[configuration.id] = configuration
        return True

    async def delete(self, configuration_id: UUID) -> bool:
        return self.items.pop(configuration_id, None) is not None

    async def count_references(self, configuration_id: UUID) -> int:
        return int(configuration_id in self.references)


class FakeUnitOfWork:
    def __init__(self, repository: FakeRepository) -> None:
        self.model_configurations = repository
        self.commits = 0

    async def __aenter__(self) -> FakeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    async def commit(self) -> None:
        self.commits += 1


class FakeVerifier:
    def __init__(self) -> None:
        self.model_identifier: str | None = None

    async def verify(self, model_identifier: str) -> str:
        self.model_identifier = model_identifier
        return f"  {'连接成功' * 80}  "


def _service() -> tuple[
    ModelConfigurationService,
    FakeRepository,
    FakeUnitOfWork,
    FakeVerifier,
]:
    repository = FakeRepository()
    unit_of_work = FakeUnitOfWork(repository)
    verifier = FakeVerifier()
    return (
        ModelConfigurationService(lambda: unit_of_work, verifier=verifier),
        repository,
        unit_of_work,
        verifier,
    )


def test_model_configuration_service_crud_and_verification() -> None:
    async def exercise() -> None:
        service, repository, unit_of_work, verifier = _service()

        created = await service.create(_input())
        assert await service.get(created.id) == created

        updated = await service.update(created.id, _input(enabled=False))
        assert updated.enabled is False
        verification = await service.verify(created.id)
        assert verification.status == "available"
        assert verification.model_identifier == "qwen-plus"
        assert len(verification.response_preview) == 200
        assert verifier.model_identifier == "qwen-plus"

        await service.delete(created.id)
        assert created.id not in repository.items
        assert unit_of_work.commits == 3

    asyncio.run(exercise())


def test_model_configuration_service_fails_closed_for_missing_or_referenced_items() -> None:
    async def exercise() -> None:
        service, repository, _, _ = _service()
        missing_id = UUID("10000000-0000-4000-8000-000000000099")

        with pytest.raises(ModelConfigurationNotFound):
            await service.get(missing_id)
        with pytest.raises(ModelConfigurationNotFound):
            await service.update(missing_id, _input())
        with pytest.raises(ModelConfigurationNotFound):
            await service.delete(missing_id)

        created = await service.create(_input())
        repository.references.add(created.id)
        with pytest.raises(ModelConfigurationInUse):
            await service.delete(created.id)
        assert repository.items[created.id] == created

    asyncio.run(exercise())


def test_model_configuration_page_binds_cursor_to_enabled_filter() -> None:
    async def exercise() -> None:
        service, repository, _, _ = _service()
        first, second = _configuration(1), _configuration(2)
        repository.page_results.extend(
            [
                PageSlice(items=(first, second), has_more=True),
                PageSlice(items=(first,), has_more=False),
            ]
        )

        first_page = await service.page(ListPageRequest(limit=2, search="Qwen"), enabled_only=True)
        assert first_page.items == (first, second)
        assert first_page.next_cursor is not None
        assert repository.last_enabled_only is True

        second_page = await service.page(
            ListPageRequest(limit=2, search="Qwen", cursor=first_page.next_cursor),
            enabled_only=True,
        )
        assert second_page.next_cursor is None
        assert repository.last_after == PageAnchor(
            created_at=second.created_at,
            id=str(second.id),
        )

    asyncio.run(exercise())
