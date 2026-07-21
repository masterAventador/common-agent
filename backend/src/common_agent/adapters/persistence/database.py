from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from common_agent.adapters.persistence.migrations import upgrade_database


class DatabaseStartupError(RuntimeError):
    """Raised when the formal platform database cannot become ready."""


class DatabaseNotStartedError(RuntimeError):
    """Raised when a session is requested before startup completes."""


class Database:
    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._engine: AsyncEngine | None = None
        self._session_factory: async_sessionmaker[AsyncSession] | None = None

    async def start(self) -> None:
        if self._engine is not None:
            return

        engine: AsyncEngine | None = None
        try:
            await asyncio.to_thread(upgrade_database, self._database_url)
            engine = create_async_engine(
                self._database_url,
                pool_pre_ping=True,
                pool_recycle=1800,
            )
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            self._engine = engine
            self._session_factory = async_sessionmaker(engine, expire_on_commit=False)
        except Exception:
            if engine is not None:
                await engine.dispose()
            raise DatabaseStartupError("无法初始化平台数据库") from None

    async def stop(self) -> None:
        engine = self._engine
        self._session_factory = None
        self._engine = None
        if engine is not None:
            await engine.dispose()

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        factory = self._session_factory
        if factory is None:
            raise DatabaseNotStartedError("平台数据库尚未启动")

        async with factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[AsyncConnection]:
        engine = self._engine
        if engine is None:
            raise DatabaseNotStartedError("平台数据库尚未启动")
        async with engine.connect() as connection:
            yield connection
