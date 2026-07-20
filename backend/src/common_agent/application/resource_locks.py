from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from common_agent.concurrency import KeyedLockPool


class ResourceMutationGuard:
    """Serializes mutations that can create or remove cross-resource references."""

    def __init__(self) -> None:
        self._locks: KeyedLockPool[str] = KeyedLockPool()

    @asynccontextmanager
    async def hold(self, *keys: str) -> AsyncIterator[None]:
        normalized = tuple(sorted({key.strip() for key in keys if key.strip()}))
        async with AsyncExitStack() as stack:
            for key in normalized:
                await stack.enter_async_context(self._locks.hold(key))
            yield


def employee_resource(employee_id: object) -> str:
    return f"employee:{employee_id}"


def knowledge_base_resource(knowledge_base_id: str) -> str:
    return f"knowledge:{knowledge_base_id}"


def workflow_resource(workflow_id: object) -> str:
    return f"workflow:{workflow_id}"


__all__ = [
    "ResourceMutationGuard",
    "employee_resource",
    "knowledge_base_resource",
    "workflow_resource",
]
