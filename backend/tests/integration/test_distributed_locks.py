from __future__ import annotations

import asyncio

from common_agent.adapters.persistence import Database, MySqlNamedLockProvider
from common_agent.application.resource_locks import ResourceMutationGuard
from tests.support.settings import TEST_DATABASE_URL


def test_mysql_named_lock_serializes_distinct_application_instances() -> None:
    async def exercise() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        try:
            first = ResourceMutationGuard(distributed=MySqlNamedLockProvider(database))
            second = ResourceMutationGuard(distributed=MySqlNamedLockProvider(database))
            first_entered = asyncio.Event()
            release_first = asyncio.Event()
            second_entered = asyncio.Event()

            async def hold_first() -> None:
                async with first.hold("tenant:test:knowledge:kb-1"):
                    first_entered.set()
                    await release_first.wait()

            async def hold_second() -> None:
                await first_entered.wait()
                async with second.hold("tenant:test:knowledge:kb-1"):
                    second_entered.set()

            first_task = asyncio.create_task(hold_first())
            second_task = asyncio.create_task(hold_second())
            await first_entered.wait()
            await asyncio.sleep(0.05)
            assert second_entered.is_set() is False
            release_first.set()
            await asyncio.gather(first_task, second_task)
            assert second_entered.is_set()
        finally:
            await database.stop()

    asyncio.run(exercise())
