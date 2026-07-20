from __future__ import annotations

import asyncio
from uuid import UUID, uuid4

from common_agent.concurrency import KeyedLockPool


def test_keyed_lock_pool_reclaims_thousands_of_idle_keys() -> None:
    async def exercise() -> None:
        pool: KeyedLockPool[UUID] = KeyedLockPool()

        for _ in range(5000):
            async with pool.hold(uuid4()):
                assert (await pool.snapshot()).entry_count == 1

        assert (await pool.snapshot()).entry_count == 0

    asyncio.run(exercise())


def test_keyed_lock_pool_keeps_waiters_serialized_and_reclaims_cancelled_waiter() -> None:
    async def exercise() -> None:
        pool: KeyedLockPool[UUID] = KeyedLockPool()
        key = uuid4()
        first_entered = asyncio.Event()
        release_first = asyncio.Event()

        async def first() -> None:
            async with pool.hold(key):
                first_entered.set()
                await release_first.wait()

        async def waiter() -> None:
            async with pool.hold(key):
                raise AssertionError("cancelled waiter must not enter")

        first_task = asyncio.create_task(first())
        await first_entered.wait()
        waiter_task = asyncio.create_task(waiter())
        await asyncio.sleep(0)
        waiting = await pool.snapshot()
        assert waiting.entry_count == 1
        assert waiting.user_count == 2

        waiter_task.cancel()
        await asyncio.gather(waiter_task, return_exceptions=True)
        release_first.set()
        await first_task

        released = await pool.snapshot()
        assert released.entry_count == 0
        assert released.user_count == 0

    asyncio.run(exercise())
