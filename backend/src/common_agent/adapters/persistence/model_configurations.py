from __future__ import annotations

from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, delete, func, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ModelConfigurationReferenceRow,
    ModelConfigurationRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.domain.model_configuration import ModelConfiguration, ModelProvider
from common_agent.pagination import PageAnchor, PageSlice, canonical_uuid_search
from common_agent.ports.model_configurations import (
    ModelConfigurationAlreadyExists,
    ModelConfigurationRepository,
)
from common_agent.tenancy.context import current_tenant


class SqlAlchemyModelConfigurationRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID) -> None:
        self._session = session
        self._tenant_id = str(tenant_id)

    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
        enabled_only: bool,
    ) -> PageSlice[ModelConfiguration]:
        statement = select(ModelConfigurationRow).where(
            ModelConfigurationRow.tenant_id == self._tenant_id
        )
        if enabled_only:
            statement = statement.where(ModelConfigurationRow.enabled.is_(True))
        if search:
            searched_id = canonical_uuid_search(search)
            statement = statement.where(
                ModelConfigurationRow.id == searched_id
                if searched_id is not None
                else or_(
                    ModelConfigurationRow.display_name.startswith(search, autoescape=True),
                    ModelConfigurationRow.model_identifier.startswith(search, autoescape=True),
                )
            )
        if after is not None:
            after_time = to_database_datetime(after.created_at)
            statement = statement.where(
                or_(
                    ModelConfigurationRow.created_at < after_time,
                    and_(
                        ModelConfigurationRow.created_at == after_time,
                        ModelConfigurationRow.id < after.id,
                    ),
                )
            )
        rows = tuple(
            await self._session.scalars(
                statement.order_by(
                    ModelConfigurationRow.created_at.desc(),
                    ModelConfigurationRow.id.desc(),
                ).limit(limit + 1)
            )
        )
        return PageSlice(
            items=tuple(_to_domain(row) for row in rows[:limit]),
            has_more=len(rows) > limit,
        )

    async def get(self, model_configuration_id: UUID) -> ModelConfiguration | None:
        row = await self._session.scalar(
            select(ModelConfigurationRow).where(
                ModelConfigurationRow.id == str(model_configuration_id),
                ModelConfigurationRow.tenant_id == self._tenant_id,
            )
        )
        return None if row is None else _to_domain(row)

    async def add(self, configuration: ModelConfiguration) -> None:
        self._session.add(
            ModelConfigurationRow(
                tenant_id=self._tenant_id,
                **_to_values(configuration),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            raise ModelConfigurationAlreadyExists from None

    async def update(self, configuration: ModelConfiguration) -> bool:
        try:
            result = cast(
                CursorResult[Any],
                await self._session.execute(
                    update(ModelConfigurationRow)
                    .where(
                        ModelConfigurationRow.id == str(configuration.id),
                        ModelConfigurationRow.tenant_id == self._tenant_id,
                    )
                    .values(**_to_values(configuration))
                ),
            )
            await self._session.flush()
        except IntegrityError:
            raise ModelConfigurationAlreadyExists from None
        return bool(result.rowcount)

    async def delete(self, model_configuration_id: UUID) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(ModelConfigurationRow).where(
                    ModelConfigurationRow.id == str(model_configuration_id),
                    ModelConfigurationRow.tenant_id == self._tenant_id,
                )
            ),
        )
        return bool(result.rowcount)

    async def count_references(self, model_configuration_id: UUID) -> int:
        count = await self._session.scalar(
            select(func.count())
            .select_from(ModelConfigurationReferenceRow)
            .where(
                ModelConfigurationReferenceRow.tenant_id == self._tenant_id,
                ModelConfigurationReferenceRow.model_configuration_id
                == str(model_configuration_id),
            )
        )
        return int(count or 0)


class SqlAlchemyModelConfigurationUnitOfWork:
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._repository: ModelConfigurationRepository | None = None

    @property
    def model_configurations(self) -> ModelConfigurationRepository:
        if self._repository is None:
            raise RuntimeError("模型配置事务尚未开始")
        return self._repository

    async def __aenter__(self) -> SqlAlchemyModelConfigurationUnitOfWork:
        if self._context is not None:
            raise RuntimeError("模型配置事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._repository = SqlAlchemyModelConfigurationRepository(session, self._tenant_id)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._context
        self._context = None
        self._session = None
        self._repository = None
        if context is None:
            raise RuntimeError("模型配置事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("模型配置事务尚未开始")
        await self._session.commit()


class SqlAlchemyModelConfigurationUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyModelConfigurationUnitOfWork:
        return SqlAlchemyModelConfigurationUnitOfWork(
            self._database,
            self._tenant_id_provider(),
        )


def _to_values(configuration: ModelConfiguration) -> dict[str, object]:
    return {
        "id": str(configuration.id),
        "display_name": configuration.display_name,
        "provider": configuration.provider.value,
        "model_identifier": configuration.model_identifier,
        "enabled": configuration.enabled,
        "created_at": to_database_datetime(configuration.created_at),
        "updated_at": to_database_datetime(configuration.updated_at),
    }


def _to_domain(row: ModelConfigurationRow) -> ModelConfiguration:
    return ModelConfiguration(
        id=UUID(row.id),
        display_name=row.display_name,
        provider=ModelProvider(row.provider),
        model_identifier=row.model_identifier,
        enabled=row.enabled,
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )
