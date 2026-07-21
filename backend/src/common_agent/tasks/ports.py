from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol
from uuid import UUID

from common_agent.tasks.models import (
    DurableTask,
    TaskBacklog,
    TaskEnqueueResult,
    TaskKind,
    TaskLeaseState,
    TaskRequest,
)


class TaskSubmission(Protocol):
    async def enqueue(self, request: TaskRequest, *, max_attempts: int) -> TaskEnqueueResult: ...


class TaskQueue(TaskSubmission, Protocol):
    async def get(self, task_id: UUID) -> DurableTask: ...

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_for: timedelta,
        kinds: frozenset[TaskKind] | None = None,
    ) -> DurableTask | None: ...

    async def heartbeat(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
        lease_for: timedelta,
    ) -> TaskLeaseState: ...

    async def complete(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> bool: ...

    async def retry(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        error_code: str,
        available_at: datetime,
        now: datetime,
    ) -> bool: ...

    async def fail(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        error_code: str,
        now: datetime,
    ) -> bool: ...

    async def cancel(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> bool: ...

    async def request_stop(self, task_id: UUID, *, now: datetime) -> DurableTask: ...

    async def request_stop_for_aggregate(
        self,
        *,
        tenant_id: UUID,
        kind: TaskKind,
        aggregate_id: UUID,
        now: datetime,
    ) -> DurableTask: ...

    async def backlog(self) -> TaskBacklog: ...


__all__ = ["TaskQueue", "TaskSubmission"]
