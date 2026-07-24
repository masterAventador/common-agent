from __future__ import annotations

from types import TracebackType
from uuid import UUID

from common_agent.domain.model_configuration import ModelConfiguration, ModelProvider
from common_agent.model_configurations.service import ModelConfigurationService
from common_agent.pagination import PageAnchor, PageSlice
from common_agent.ports.model_configurations import ModelConfigurationAlreadyExists
from common_agent.tenancy import current_tenant


class FakeRepository:
    def __init__(self) -> None:
        self.items: dict[UUID, ModelConfiguration] = {}
        self.references: set[UUID] = set()
        self.streaming_compatibilities: set[tuple[ModelProvider, str]] = set()

    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
        enabled_only: bool,
    ) -> PageSlice[ModelConfiguration]:
        del limit, search, after, enabled_only
        return PageSlice(items=(), has_more=False)

    async def get(self, configuration_id: UUID) -> ModelConfiguration | None:
        return self.items.get(configuration_id)

    async def get_by_identifier(self, model_identifier: str) -> ModelConfiguration | None:
        return next(
            (item for item in self.items.values() if item.model_identifier == model_identifier),
            None,
        )

    async def streaming_breaks_tool_calls(
        self,
        provider: ModelProvider,
        model_identifier: str,
    ) -> bool:
        return (provider, model_identifier) in self.streaming_compatibilities

    async def add(self, configuration: ModelConfiguration) -> None:
        already = await self.get_by_identifier(configuration.model_identifier)
        if already is not None:
            raise ModelConfigurationAlreadyExists
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
    async def verify(self, model_identifier: str) -> str:
        return model_identifier


def build_service() -> tuple[ModelConfigurationService, FakeRepository, FakeUnitOfWork]:
    repository = FakeRepository()
    unit_of_work = FakeUnitOfWork(repository)
    service = ModelConfigurationService(lambda: unit_of_work, verifier=FakeVerifier())
    return service, repository, unit_of_work


class TenantAwareRepositoryHub:
    """按租户隔离的 Fake 仓储集合, 复刻正式服务凭 current_tenant() 分租户读写的语义。"""

    def __init__(self) -> None:
        self.repositories: dict[UUID, FakeRepository] = {}

    def repository_for(self, tenant_id: UUID) -> FakeRepository:
        return self.repositories.setdefault(tenant_id, FakeRepository())


def build_tenant_scoped_service(hub: TenantAwareRepositoryHub) -> ModelConfigurationService:
    """构造一个按当前绑定租户上下文路由到对应 Fake 仓储的模型配置服务。"""

    def factory() -> FakeUnitOfWork:
        return FakeUnitOfWork(hub.repository_for(current_tenant().tenant_id))

    return ModelConfigurationService(factory, verifier=FakeVerifier())
