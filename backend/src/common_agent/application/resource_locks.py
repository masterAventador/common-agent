from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from common_agent.concurrency import CoordinatedLockPool, DistributedLockProvider


class ResourceMutationGuard:
    """Serializes mutations that can create or remove cross-resource references."""

    def __init__(
        self,
        key_namespace: Callable[[str], str] | None = None,
        *,
        distributed: DistributedLockProvider | None = None,
    ) -> None:
        self._locks = CoordinatedLockPool(distributed=distributed)
        self._key_namespace = key_namespace or (lambda key: key)

    @asynccontextmanager
    async def hold(self, *keys: str) -> AsyncIterator[None]:
        normalized = tuple(
            sorted({self._key_namespace(key.strip()) for key in keys if key.strip()})
        )
        async with self._locks.hold(*normalized):
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
