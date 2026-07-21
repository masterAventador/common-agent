from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import DurableTaskRow
from common_agent.adapters.persistence.tasks import SqlAlchemyTaskQueue
from common_agent.tasks import (
    ConversationReplyPayload,
    TaskKind,
    TaskRequest,
    TaskState,
    WorkflowRunPayload,
)
from common_agent.tenancy.constants import DEFAULT_TENANT_ID
from tests.support.settings import TEST_DATABASE_URL


async def _delete_tasks(database: Database) -> None:
    async with database.session() as session:
        await session.execute(delete(DurableTaskRow))
        await session.commit()


def test_mysql_task_queue_is_idempotent_leased_and_recovers_expired_claims() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        await _delete_tasks(database)
        queue = SqlAlchemyTaskQueue(database)
        now = datetime.now(UTC)
        conversation_id = uuid4()
        request = TaskRequest(
            task_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=f"conversation:{conversation_id}:reply:{uuid4()}",
            aggregate_id=conversation_id,
            payload=ConversationReplyPayload(
                conversation_id=conversation_id,
                turn_id=uuid4(),
                user_message_id=uuid4(),
                assistant_message_id=uuid4(),
                retry=False,
            ),
            created_at=now,
        )
        try:
            first = await queue.enqueue(request, max_attempts=3)
            duplicate = await queue.enqueue(request, max_attempts=3)
            assert first.created is True
            assert duplicate.created is False
            assert duplicate.task.request.task_id == request.task_id

            claimed_a = await queue.claim(
                worker_id="worker-a",
                now=now,
                lease_for=timedelta(seconds=10),
            )
            assert claimed_a is not None
            assert claimed_a.state is TaskState.RUNNING
            assert claimed_a.attempts == 1
            assert claimed_a.lease_token is not None
            assert (
                await queue.claim(worker_id="worker-b", now=now, lease_for=timedelta(seconds=10))
                is None
            )

            reclaimed = await queue.claim(
                worker_id="worker-b",
                now=now + timedelta(seconds=11),
                lease_for=timedelta(seconds=10),
            )
            assert reclaimed is not None
            assert reclaimed.request.task_id == request.task_id
            assert reclaimed.attempts == 2
            assert reclaimed.lease_owner == "worker-b"
            assert reclaimed.lease_token is not None
            assert reclaimed.lease_token != claimed_a.lease_token
            assert (
                await queue.complete(
                    request.task_id,
                    worker_id="worker-a",
                    lease_token=claimed_a.lease_token,
                    now=now + timedelta(seconds=12),
                )
                is False
            )
            assert (
                await queue.complete(
                    request.task_id,
                    worker_id="worker-b",
                    lease_token=reclaimed.lease_token,
                    now=now + timedelta(seconds=12),
                )
                is True
            )
            assert (await queue.get(request.task_id)).state is TaskState.SUCCEEDED
        finally:
            await _delete_tasks(database)
            await database.stop()

    asyncio.run(scenario())


def test_mysql_task_queue_reserves_claims_for_supported_task_kinds() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        await _delete_tasks(database)
        queue = SqlAlchemyTaskQueue(database)
        now = datetime.now(UTC)
        conversation_id = uuid4()
        workflow_id = uuid4()
        run_id = uuid4()
        conversation_request = TaskRequest(
            task_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=f"conversation:{conversation_id}:reply:{uuid4()}",
            aggregate_id=conversation_id,
            payload=ConversationReplyPayload(
                conversation_id=conversation_id,
                turn_id=uuid4(),
                user_message_id=uuid4(),
                assistant_message_id=uuid4(),
                retry=False,
            ),
            created_at=now,
        )
        workflow_request = TaskRequest(
            task_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            kind=TaskKind.WORKFLOW_RUN,
            idempotency_key=f"workflow:{workflow_id}:run:{run_id}",
            aggregate_id=run_id,
            payload=WorkflowRunPayload(run_id=run_id, workflow_id=workflow_id),
            created_at=now + timedelta(microseconds=1),
        )
        try:
            await queue.enqueue(conversation_request, max_attempts=3)
            await queue.enqueue(workflow_request, max_attempts=3)

            claimed = await queue.claim(
                worker_id="workflow-reserved-worker",
                now=now + timedelta(seconds=1),
                lease_for=timedelta(seconds=30),
                kinds=frozenset({TaskKind.WORKFLOW_RUN}),
            )

            assert claimed is not None
            assert claimed.request.task_id == workflow_request.task_id
        finally:
            await _delete_tasks(database)
            await database.stop()

    asyncio.run(scenario())


def test_mysql_task_queue_allows_only_one_concurrent_lease_per_task() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        await _delete_tasks(database)
        queue = SqlAlchemyTaskQueue(database)
        now = datetime.now(UTC)
        conversation_id = uuid4()
        request = TaskRequest(
            task_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=f"conversation:{conversation_id}:concurrent:{uuid4()}",
            aggregate_id=conversation_id,
            payload=ConversationReplyPayload(
                conversation_id=conversation_id,
                turn_id=uuid4(),
                user_message_id=uuid4(),
                assistant_message_id=uuid4(),
                retry=False,
            ),
            created_at=now,
        )
        try:
            await queue.enqueue(request, max_attempts=3)

            claims = await asyncio.gather(
                queue.claim(
                    worker_id="concurrent-worker-a",
                    now=now,
                    lease_for=timedelta(seconds=30),
                ),
                queue.claim(
                    worker_id="concurrent-worker-b",
                    now=now,
                    lease_for=timedelta(seconds=30),
                ),
            )

            claimed = [task for task in claims if task is not None]
            assert len(claimed) == 1
            assert claimed[0].request.task_id == request.task_id
        finally:
            await _delete_tasks(database)
            await database.stop()

    asyncio.run(scenario())


def test_mysql_task_queue_persists_stop_retry_backlog_and_terminal_failure() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        await _delete_tasks(database)
        queue = SqlAlchemyTaskQueue(database)
        now = datetime.now(UTC)
        conversation_id = uuid4()
        request = TaskRequest(
            task_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=f"conversation:{conversation_id}:reply:{uuid4()}",
            aggregate_id=conversation_id,
            payload=ConversationReplyPayload(
                conversation_id=conversation_id,
                turn_id=uuid4(),
                user_message_id=uuid4(),
                assistant_message_id=uuid4(),
                retry=True,
            ),
            created_at=now,
        )
        try:
            await queue.enqueue(request, max_attempts=2)
            claimed = await queue.claim(
                worker_id="worker-a", now=now, lease_for=timedelta(seconds=30)
            )
            assert claimed is not None
            assert claimed.lease_token is not None
            stopped = await queue.request_stop(request.task_id, now=now + timedelta(seconds=1))
            assert stopped.stop_requested is True
            lease = await queue.heartbeat(
                request.task_id,
                worker_id="worker-a",
                lease_token=claimed.lease_token,
                now=now + timedelta(seconds=2),
                lease_for=timedelta(seconds=30),
            )
            assert lease.owned is True
            assert lease.stop_requested is True
            assert (
                await queue.retry(
                    request.task_id,
                    worker_id="worker-a",
                    lease_token=claimed.lease_token,
                    error_code="temporary_failure",
                    available_at=now + timedelta(seconds=10),
                    now=now + timedelta(seconds=2),
                )
                is True
            )
            assert (await queue.backlog()).retry_wait >= 1

            claimed_again = await queue.claim(
                worker_id="worker-b",
                now=now + timedelta(seconds=11),
                lease_for=timedelta(seconds=30),
            )
            assert claimed_again is not None
            assert claimed_again.lease_token is not None
            assert (
                await queue.fail(
                    request.task_id,
                    worker_id="worker-b",
                    lease_token=claimed_again.lease_token,
                    error_code="retry_exhausted",
                    now=now + timedelta(seconds=12),
                )
                is True
            )
            assert (await queue.get(request.task_id)).state is TaskState.FAILED
        finally:
            await _delete_tasks(database)
            await database.stop()

    asyncio.run(scenario())


def test_mysql_task_queue_stops_active_aggregate_and_persists_cancelled_terminal() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        await _delete_tasks(database)
        queue = SqlAlchemyTaskQueue(database)
        now = datetime.now(UTC)
        conversation_id = uuid4()
        request = TaskRequest(
            task_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=f"conversation:{conversation_id}:reply:{uuid4()}",
            aggregate_id=conversation_id,
            payload=ConversationReplyPayload(
                conversation_id=conversation_id,
                turn_id=uuid4(),
                user_message_id=uuid4(),
                assistant_message_id=uuid4(),
                retry=False,
            ),
            created_at=now,
        )
        try:
            await queue.enqueue(request, max_attempts=3)
            claimed = await queue.claim(
                worker_id="worker-a",
                now=now,
                lease_for=timedelta(seconds=30),
            )
            assert claimed is not None
            assert claimed.lease_token is not None

            stopped = await queue.request_stop_for_aggregate(
                tenant_id=DEFAULT_TENANT_ID,
                kind=TaskKind.CONVERSATION_REPLY,
                aggregate_id=conversation_id,
                now=now + timedelta(seconds=1),
            )
            assert stopped.request.task_id == request.task_id
            assert stopped.stop_requested is True
            assert (
                await queue.cancel(
                    request.task_id,
                    worker_id="worker-a",
                    lease_token=claimed.lease_token,
                    now=now + timedelta(seconds=2),
                )
                is True
            )
            assert (await queue.get(request.task_id)).state is TaskState.CANCELLED
        finally:
            await _delete_tasks(database)
            await database.stop()

    asyncio.run(scenario())


def test_mysql_task_queue_reclaims_crashed_final_attempt_until_handler_can_finalize() -> None:
    async def scenario() -> None:
        database = Database(TEST_DATABASE_URL)
        await database.start()
        await _delete_tasks(database)
        queue = SqlAlchemyTaskQueue(database)
        now = datetime.now(UTC)
        conversation_id = uuid4()
        request = TaskRequest(
            task_id=uuid4(),
            tenant_id=DEFAULT_TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=f"conversation:{conversation_id}:crash:{uuid4()}",
            aggregate_id=conversation_id,
            payload=ConversationReplyPayload(
                conversation_id=conversation_id,
                turn_id=uuid4(),
                user_message_id=uuid4(),
                assistant_message_id=uuid4(),
                retry=False,
            ),
            created_at=now,
        )
        try:
            await queue.enqueue(request, max_attempts=1)
            crashed = await queue.claim(
                worker_id="worker-crashed",
                now=now,
                lease_for=timedelta(seconds=3),
            )
            assert crashed is not None
            assert crashed.attempts == 1

            recovered = await queue.claim(
                worker_id="worker-recovered",
                now=now + timedelta(seconds=4),
                lease_for=timedelta(seconds=3),
            )

            assert recovered is not None
            assert recovered.request.task_id == request.task_id
            assert recovered.attempts == 1
            assert recovered.lease_token != crashed.lease_token
        finally:
            await _delete_tasks(database)
            await database.stop()

    asyncio.run(scenario())
