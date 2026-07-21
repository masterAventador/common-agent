from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.domain.model_configuration import ModelConfiguration
from common_agent.pagination import PageAnchor, PageSlice


class ModelConfigurationAlreadyExists(Exception):
    """Raised when a tenant already owns the same name or remote identifier."""


class ModelConfigurationRepository(Protocol):
    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
        enabled_only: bool,
    ) -> PageSlice[ModelConfiguration]: ...

    async def get(self, model_configuration_id: UUID) -> ModelConfiguration | None: ...

    async def add(self, configuration: ModelConfiguration) -> None: ...

    async def update(self, configuration: ModelConfiguration) -> bool: ...

    async def delete(self, model_configuration_id: UUID) -> bool: ...

    async def count_references(self, model_configuration_id: UUID) -> int: ...


class ModelConfigurationUnitOfWork(Protocol):
    @property
    def model_configurations(self) -> ModelConfigurationRepository: ...

    async def __aenter__(self) -> ModelConfigurationUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class ModelConfigurationUnitOfWorkFactory(Protocol):
    def __call__(self) -> ModelConfigurationUnitOfWork: ...
