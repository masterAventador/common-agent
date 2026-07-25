from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import UTC, datetime
from uuid import UUID

from common_agent.domain.model_configuration import (
    ModelConfiguration,
    ModelConfigurationInput,
    ModelProvider,
)
from common_agent.model_configurations.seeds import (
    COMMON_MODEL_CONFIGURATION_SEEDS,
    seed_common_model_configurations,
    seed_common_model_configurations_for_tenants,
)
from tests.unit.model_configurations.support import (
    TenantAwareRepositoryHub,
    build_service,
    build_tenant_scoped_service,
)

WORKSPACE_A = UUID("30000000-0000-4000-8000-000000000001")
WORKSPACE_B = UUID("30000000-0000-4000-8000-000000000002")
NEW_WORKSPACE = UUID("30000000-0000-4000-8000-000000000003")

_EXPECTED_IDENTIFIERS = {
    "qwen-plus",
    "qwen-turbo",
    "qwen-long",
    "deepseek-r1",
    "deepseek-v3",
}


def _identifiers(items: Iterable[ModelConfiguration]) -> set[str]:
    return {item.model_identifier for item in items}


def test_common_seed_catalog_only_lists_bailian_first_party_identifiers() -> None:
    assert COMMON_MODEL_CONFIGURATION_SEEDS
    for seed in COMMON_MODEL_CONFIGURATION_SEEDS:
        assert isinstance(seed, ModelConfigurationInput)
        # 百炼一方模型标识不含供应商前缀斜杠, 且默认启用, 保证真实可调通
        assert "/" not in seed.model_identifier
        assert seed.enabled is True
    identifiers = {seed.model_identifier for seed in COMMON_MODEL_CONFIGURATION_SEEDS}
    assert identifiers == _EXPECTED_IDENTIFIERS


def test_seed_creates_all_common_models_enabled_and_bailian() -> None:
    async def exercise() -> None:
        service, repository, _ = build_service()

        created = await seed_common_model_configurations(service)

        assert _identifiers(repository.items.values()) == _EXPECTED_IDENTIFIERS
        assert _identifiers(created) == _EXPECTED_IDENTIFIERS
        for item in repository.items.values():
            assert item.provider is ModelProvider.BAILIAN
            assert item.enabled is True

    asyncio.run(exercise())


def test_seed_is_idempotent_and_preserves_existing_default() -> None:
    async def exercise() -> None:
        service, repository, _ = build_service()
        existing = ModelConfiguration.create(
            configuration=ModelConfigurationInput(
                display_name="平台默认模型",
                model_identifier="qwen-plus",
                enabled=True,
            ),
            model_configuration_id=UUID("10000000-0000-4000-8000-000000000001"),
            now=datetime(2026, 7, 22, tzinfo=UTC),
        )
        await repository.add(existing)

        await seed_common_model_configurations(service)
        count_after_first = len(repository.items)
        await seed_common_model_configurations(service)

        assert count_after_first == len(_EXPECTED_IDENTIFIERS)
        assert len(repository.items) == len(_EXPECTED_IDENTIFIERS)
        preserved = await repository.get_by_identifier("qwen-plus")
        assert preserved is not None
        assert preserved.id == existing.id
        assert preserved.display_name == "平台默认模型"

    asyncio.run(exercise())


def test_ensure_returns_existing_without_duplicate_or_extra_commit() -> None:
    async def exercise() -> None:
        service, repository, unit_of_work = build_service()

        first = await service.ensure(
            ModelConfigurationInput(
                display_name="通义千问-Plus",
                model_identifier="qwen-plus",
                enabled=True,
            )
        )
        commits_after_first = unit_of_work.commits

        second = await service.ensure(
            ModelConfigurationInput(
                display_name="重复别名",
                model_identifier="qwen-plus",
                enabled=False,
            )
        )

        assert second.id == first.id
        assert second.display_name == "通义千问-Plus"
        assert second.enabled is True
        assert len(repository.items) == 1
        assert unit_of_work.commits == commits_after_first

    asyncio.run(exercise())


def test_seed_across_tenants_gives_each_workspace_full_catalog() -> None:
    async def exercise() -> None:
        hub = TenantAwareRepositoryHub()
        service = build_tenant_scoped_service(hub)

        await seed_common_model_configurations_for_tenants(service, (WORKSPACE_A, WORKSPACE_B))

        assert _identifiers(hub.repository_for(WORKSPACE_A).items.values()) == _EXPECTED_IDENTIFIERS
        assert _identifiers(hub.repository_for(WORKSPACE_B).items.values()) == _EXPECTED_IDENTIFIERS

    asyncio.run(exercise())


def test_seed_across_tenants_is_idempotent_per_workspace() -> None:
    async def exercise() -> None:
        hub = TenantAwareRepositoryHub()
        service = build_tenant_scoped_service(hub)

        await seed_common_model_configurations_for_tenants(service, (WORKSPACE_A, WORKSPACE_B))
        await seed_common_model_configurations_for_tenants(service, (WORKSPACE_A, WORKSPACE_B))

        assert len(hub.repository_for(WORKSPACE_A).items) == len(_EXPECTED_IDENTIFIERS)
        assert len(hub.repository_for(WORKSPACE_B).items) == len(_EXPECTED_IDENTIFIERS)

    asyncio.run(exercise())


def test_seed_for_single_new_workspace_gives_full_catalog() -> None:
    async def exercise() -> None:
        hub = TenantAwareRepositoryHub()
        service = build_tenant_scoped_service(hub)

        await seed_common_model_configurations_for_tenants(service, (NEW_WORKSPACE,))

        assert (
            _identifiers(hub.repository_for(NEW_WORKSPACE).items.values()) == _EXPECTED_IDENTIFIERS
        )

    asyncio.run(exercise())


def test_ensure_creates_when_absent() -> None:
    async def exercise() -> None:
        service, repository, _ = build_service()

        created = await service.ensure(
            ModelConfigurationInput(
                display_name="DeepSeek-R1",
                model_identifier="deepseek-r1",
                enabled=True,
            )
        )

        assert created.model_identifier == "deepseek-r1"
        assert created.provider is ModelProvider.BAILIAN
        assert created.enabled is True
        assert len(repository.items) == 1

    asyncio.run(exercise())
