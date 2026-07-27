from __future__ import annotations

import hashlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from common_agent.concurrency import DistributedLockUnavailable
from common_agent.observability import log_event

_LOGGER = logging.getLogger("common_agent.persistence.locks")


class MySqlNamedLockProvider:
    """Holds MySQL session locks on a dedicated pooled connection."""

    def __init__(self, database: Database, *, timeout_seconds: int = 30) -> None:
        if not 1 <= timeout_seconds <= 300:
            raise ValueError("timeout_seconds must be between 1 and 300")
        self._database = database
        self._timeout_seconds = timeout_seconds

    @asynccontextmanager
    async def hold(self, keys: tuple[str, ...]) -> AsyncIterator[None]:
        names = tuple(_lock_name(key) for key in sorted(set(keys)))
        if not names:
            yield
            return
        async with self._database.connection() as connection:
            acquired: list[str] = []
            try:
                for name in names:
                    result = await connection.scalar(
                        text("SELECT GET_LOCK(:lock_name, :timeout_seconds)"),
                        {"lock_name": name, "timeout_seconds": self._timeout_seconds},
                    )
                    if result != 1:
                        raise DistributedLockUnavailable("无法获取跨进程资源锁")
                    acquired.append(name)
            except BaseException:
                # Cancellation can race with GET_LOCK's server-side completion. Invalidating
                # the connection guarantees that MySQL releases every session-owned lock.
                await connection.invalidate()
                raise

            release_failed = False
            try:
                yield
            finally:
                for name in reversed(acquired):
                    try:
                        released = await connection.scalar(
                            text("SELECT RELEASE_LOCK(:lock_name)"),
                            {"lock_name": name},
                        )
                        release_failed = release_failed or released != 1
                    except Exception as error:
                        release_failed = True
                        log_event(
                            _LOGGER,
                            "distributed_lock.release_failed",
                            level=logging.ERROR,
                            exc_info=True,
                            exception_type=type(error).__name__,
                        )
                if release_failed:
                    await connection.invalidate()


def _lock_name(key: str) -> str:
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()[:50]
    return f"common-agent:{digest}"


__all__ = ["MySqlNamedLockProvider"]
