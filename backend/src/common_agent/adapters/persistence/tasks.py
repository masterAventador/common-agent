from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import DurableTaskRow
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.tasks import (
    ConversationReplyPayload,
    DurableTask,
    TaskBacklog,
    TaskEnqueueResult,
    TaskIdempotencyConflict,
    TaskKind,
    TaskLeaseState,
    TaskNotFound,
    TaskRequest,
    TaskState,
    WorkflowRunPayload,
)


class SqlAlchemyTaskSubmission:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def enqueue(self, request: TaskRequest, *, max_attempts: int) -> TaskEnqueueResult:
        if not 1 <= max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        existing = await self._session.scalar(
            select(DurableTaskRow).where(
                DurableTaskRow.tenant_id == str(request.tenant_id),
                DurableTaskRow.idempotency_key == request.idempotency_key,
            )
        )
        if existing is not None:
            return _existing_result(existing, request)
        row = _new_row(request, max_attempts=max_attempts)
        self._session.add(row)
        await self._session.flush()
        return TaskEnqueueResult(task=_from_row(row), created=True)


class SqlAlchemyTaskQueue:
    def __init__(self, database: Database) -> None:
        self._database = database

    async def enqueue(self, request: TaskRequest, *, max_attempts: int) -> TaskEnqueueResult:
        if not 1 <= max_attempts <= 100:
            raise ValueError("max_attempts must be between 1 and 100")
        existing = await self._by_key(request.tenant_id, request.idempotency_key)
        if existing is not None:
            return self._existing_result(existing, request)
        row = _new_row(request, max_attempts=max_attempts)
        try:
            async with self._database.session() as session:
                session.add(row)
                await session.commit()
        except IntegrityError:
            existing = await self._by_key(request.tenant_id, request.idempotency_key)
            if existing is None:
                raise
            return self._existing_result(existing, request)
        return TaskEnqueueResult(task=_from_row(row), created=True)

    async def get(self, task_id: UUID) -> DurableTask:
        async with self._database.session() as session:
            row = await session.get(DurableTaskRow, str(task_id))
        if row is None:
            raise TaskNotFound(str(task_id))
        return _from_row(row)

    async def claim(
        self,
        *,
        worker_id: str,
        now: datetime,
        lease_for: timedelta,
        kinds: frozenset[TaskKind] | None = None,
    ) -> DurableTask | None:
        _worker(worker_id)
        _lease(lease_for)
        task_kinds = _kinds(kinds)
        database_now = to_database_datetime(now)
        lease_until = to_database_datetime(now + lease_for)
        async with self._database.session() as session:
            row = await session.scalar(
                select(DurableTaskRow)
                .where(
                    DurableTaskRow.kind.in_(task_kinds),
                    or_(
                        (
                            DurableTaskRow.state.in_(
                                (TaskState.PENDING.value, TaskState.RETRY_WAIT.value)
                            )
                            & (DurableTaskRow.attempts < DurableTaskRow.max_attempts)
                            & (DurableTaskRow.available_at <= database_now)
                        ),
                        (
                            (DurableTaskRow.state == TaskState.RUNNING.value)
                            & (DurableTaskRow.lease_until <= database_now)
                        ),
                    ),
                )
                .order_by(DurableTaskRow.available_at, DurableTaskRow.created_at)
                .limit(1)
                .with_for_update(skip_locked=True)
            )
            if row is None:
                await session.commit()
                return None
            row.state = TaskState.RUNNING.value
            if row.attempts < row.max_attempts:
                row.attempts += 1
            row.lease_owner = worker_id
            row.lease_token = str(uuid4())
            row.lease_until = lease_until
            row.error_code = None
            row.updated_at = database_now
            await session.commit()
            return _from_row(row)

    async def heartbeat(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
        lease_for: timedelta,
    ) -> TaskLeaseState:
        _worker(worker_id)
        _lease(lease_for)
        async with self._database.session() as session:
            row = await session.get(DurableTaskRow, str(task_id), with_for_update=True)
            if row is None:
                return TaskLeaseState(owned=False, stop_requested=False)
            owned = (
                row.state == TaskState.RUNNING.value
                and row.lease_owner == worker_id
                and row.lease_token == str(lease_token)
            )
            if owned:
                row.lease_until = to_database_datetime(now + lease_for)
                row.updated_at = to_database_datetime(now)
                await session.commit()
            return TaskLeaseState(owned=owned, stop_requested=row.stop_requested)

    async def complete(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> bool:
        return await self._finish(
            task_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=now,
            state=TaskState.SUCCEEDED,
            error_code=None,
        )

    async def retry(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        error_code: str,
        available_at: datetime,
        now: datetime,
    ) -> bool:
        _error(error_code)
        async with self._database.session() as session:
            row = await session.get(DurableTaskRow, str(task_id), with_for_update=True)
            if row is None or not _owns(row, worker_id=worker_id, lease_token=lease_token):
                return False
            row.state = TaskState.RETRY_WAIT.value
            row.available_at = to_database_datetime(available_at)
            row.lease_owner = None
            row.lease_token = None
            row.lease_until = None
            row.error_code = error_code
            row.updated_at = to_database_datetime(now)
            await session.commit()
            return True

    async def fail(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        error_code: str,
        now: datetime,
    ) -> bool:
        _error(error_code)
        return await self._finish(
            task_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=now,
            state=TaskState.FAILED,
            error_code=error_code,
        )

    async def cancel(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
    ) -> bool:
        return await self._finish(
            task_id,
            worker_id=worker_id,
            lease_token=lease_token,
            now=now,
            state=TaskState.CANCELLED,
            error_code=None,
        )

    async def request_stop(self, task_id: UUID, *, now: datetime) -> DurableTask:
        async with self._database.session() as session:
            row = await session.get(DurableTaskRow, str(task_id), with_for_update=True)
            if row is None:
                raise TaskNotFound(str(task_id))
            if row.state not in {
                TaskState.SUCCEEDED.value,
                TaskState.FAILED.value,
                TaskState.CANCELLED.value,
            }:
                row.stop_requested = True
                row.updated_at = to_database_datetime(now)
                await session.commit()
            return _from_row(row)

    async def request_stop_for_aggregate(
        self,
        *,
        tenant_id: UUID,
        kind: TaskKind,
        aggregate_id: UUID,
        now: datetime,
    ) -> DurableTask:
        async with self._database.session() as session:
            row = await session.scalar(
                select(DurableTaskRow)
                .where(
                    DurableTaskRow.tenant_id == str(tenant_id),
                    DurableTaskRow.kind == kind.value,
                    DurableTaskRow.aggregate_id == str(aggregate_id),
                    DurableTaskRow.state.in_(
                        (
                            TaskState.PENDING.value,
                            TaskState.RUNNING.value,
                            TaskState.RETRY_WAIT.value,
                        )
                    ),
                )
                .order_by(DurableTaskRow.created_at.desc(), DurableTaskRow.task_id.desc())
                .limit(1)
                .with_for_update()
            )
            if row is None:
                raise TaskNotFound(str(aggregate_id))
            row.stop_requested = True
            row.updated_at = to_database_datetime(now)
            await session.commit()
            return _from_row(row)

    async def backlog(self) -> TaskBacklog:
        async with self._database.session() as session:
            result = await session.execute(
                select(DurableTaskRow.state, func.count()).group_by(DurableTaskRow.state)
            )
            grouped: dict[str, int] = {state: count for state, count in result.all()}
            oldest = await session.scalar(
                select(func.min(DurableTaskRow.available_at)).where(
                    DurableTaskRow.state.in_((TaskState.PENDING.value, TaskState.RETRY_WAIT.value))
                )
            )
        return TaskBacklog(
            pending=int(grouped.get(TaskState.PENDING.value, 0)),
            running=int(grouped.get(TaskState.RUNNING.value, 0)),
            retry_wait=int(grouped.get(TaskState.RETRY_WAIT.value, 0)),
            failed=int(grouped.get(TaskState.FAILED.value, 0)),
            oldest_available_at=from_database_datetime(oldest) if oldest is not None else None,
        )

    async def _by_key(self, tenant_id: UUID, key: str) -> DurableTaskRow | None:
        async with self._database.session() as session:
            row: DurableTaskRow | None = await session.scalar(
                select(DurableTaskRow).where(
                    DurableTaskRow.tenant_id == str(tenant_id),
                    DurableTaskRow.idempotency_key == key,
                )
            )
            return row

    @staticmethod
    def _existing_result(row: DurableTaskRow, request: TaskRequest) -> TaskEnqueueResult:
        return _existing_result(row, request)

    async def _finish(
        self,
        task_id: UUID,
        *,
        worker_id: str,
        lease_token: UUID,
        now: datetime,
        state: TaskState,
        error_code: str | None,
    ) -> bool:
        _worker(worker_id)
        async with self._database.session() as session:
            row = await session.get(DurableTaskRow, str(task_id), with_for_update=True)
            if row is None or not _owns(row, worker_id=worker_id, lease_token=lease_token):
                return False
            row.state = state.value
            row.lease_owner = None
            row.lease_token = None
            row.lease_until = None
            row.error_code = error_code
            row.updated_at = to_database_datetime(now)
            await session.commit()
            return True


def _payload_to_json(request: TaskRequest) -> dict[str, object]:
    payload = request.payload
    if isinstance(payload, ConversationReplyPayload):
        return {
            "conversation_id": str(payload.conversation_id),
            "turn_id": str(payload.turn_id),
            "user_message_id": str(payload.user_message_id),
            "assistant_message_id": str(payload.assistant_message_id),
            "retry": payload.retry,
        }
    return {"run_id": str(payload.run_id), "workflow_id": str(payload.workflow_id)}


def _new_row(request: TaskRequest, *, max_attempts: int) -> DurableTaskRow:
    return DurableTaskRow(
        task_id=str(request.task_id),
        tenant_id=str(request.tenant_id),
        kind=request.kind.value,
        idempotency_key=request.idempotency_key,
        aggregate_id=str(request.aggregate_id),
        payload=_payload_to_json(request),
        state=TaskState.PENDING.value,
        attempts=0,
        max_attempts=max_attempts,
        available_at=to_database_datetime(request.created_at),
        lease_owner=None,
        lease_token=None,
        lease_until=None,
        stop_requested=False,
        error_code=None,
        created_at=to_database_datetime(request.created_at),
        updated_at=to_database_datetime(request.created_at),
    )


def _existing_result(row: DurableTaskRow, request: TaskRequest) -> TaskEnqueueResult:
    existing = _from_row(row)
    if existing.request != request:
        raise TaskIdempotencyConflict(request.idempotency_key)
    return TaskEnqueueResult(task=existing, created=False)


def _from_row(row: DurableTaskRow) -> DurableTask:
    kind = TaskKind(row.kind)
    raw = row.payload
    payload = (
        ConversationReplyPayload(
            conversation_id=UUID(str(raw["conversation_id"])),
            turn_id=UUID(str(raw["turn_id"])),
            user_message_id=UUID(str(raw["user_message_id"])),
            assistant_message_id=UUID(str(raw["assistant_message_id"])),
            retry=bool(raw["retry"]),
        )
        if kind is TaskKind.CONVERSATION_REPLY
        else WorkflowRunPayload(
            run_id=UUID(str(raw["run_id"])),
            workflow_id=UUID(str(raw["workflow_id"])),
        )
    )
    request = TaskRequest(
        task_id=UUID(row.task_id),
        tenant_id=UUID(row.tenant_id),
        kind=kind,
        idempotency_key=row.idempotency_key,
        aggregate_id=UUID(row.aggregate_id),
        payload=payload,
        created_at=from_database_datetime(row.created_at),
    )
    return DurableTask(
        request=request,
        state=TaskState(row.state),
        attempts=row.attempts,
        max_attempts=row.max_attempts,
        available_at=from_database_datetime(row.available_at),
        lease_owner=row.lease_owner,
        lease_token=UUID(row.lease_token) if row.lease_token is not None else None,
        lease_until=(
            from_database_datetime(row.lease_until) if row.lease_until is not None else None
        ),
        stop_requested=row.stop_requested,
        error_code=row.error_code,
        updated_at=from_database_datetime(row.updated_at),
    )


def _worker(value: str) -> None:
    if not value or value != value.strip() or len(value) > 128:
        raise ValueError("worker_id must be safe non-empty text")


def _lease(value: timedelta) -> None:
    if value < timedelta(seconds=3) or value > timedelta(hours=1):
        raise ValueError("lease_for must be between 3 seconds and 1 hour")


def _error(value: str) -> None:
    if not value or value != value.strip() or len(value) > 128:
        raise ValueError("error_code must be safe non-empty text")


def _kinds(values: frozenset[TaskKind] | None) -> tuple[str, ...]:
    selected = frozenset(TaskKind) if values is None else values
    if not selected or any(not isinstance(value, TaskKind) for value in selected):
        raise ValueError("kinds must contain supported task kinds")
    return tuple(sorted(value.value for value in selected))


def _owns(row: DurableTaskRow | None, *, worker_id: str, lease_token: UUID) -> bool:
    return bool(
        row is not None
        and row.state == TaskState.RUNNING.value
        and row.lease_owner == worker_id
        and row.lease_token == str(lease_token)
    )


__all__ = ["SqlAlchemyTaskQueue", "SqlAlchemyTaskSubmission"]
