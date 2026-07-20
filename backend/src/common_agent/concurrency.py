from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Hashable
from contextlib import asynccontextmanager
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class KeyedLockPoolSnapshot:
    entry_count: int
    user_count: int
    locked_entry_count: int


@dataclass(slots=True)
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class KeyedLockPool[KeyT: Hashable]:
    def __init__(self) -> None:
        self._entries: dict[KeyT, _LockEntry] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, key: KeyT) -> AsyncIterator[None]:
        async with self._guard:
            entry = self._entries.get(key)
            if entry is None:
                entry = _LockEntry(lock=asyncio.Lock())
                self._entries[key] = entry
            entry.users += 1

        acquired = False
        try:
            await entry.lock.acquire()
            acquired = True
            yield
        finally:
            if acquired:
                entry.lock.release()
            async with self._guard:
                entry.users -= 1
                if entry.users == 0 and self._entries.get(key) is entry:
                    self._entries.pop(key)

    async def snapshot(self) -> KeyedLockPoolSnapshot:
        async with self._guard:
            return KeyedLockPoolSnapshot(
                entry_count=len(self._entries),
                user_count=sum(entry.users for entry in self._entries.values()),
                locked_entry_count=sum(entry.lock.locked() for entry in self._entries.values()),
            )


__all__ = ["KeyedLockPool", "KeyedLockPoolSnapshot"]
