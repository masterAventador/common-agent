from __future__ import annotations

from dataclasses import fields, replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from common_agent.tasks import (
    ConversationReplyPayload,
    DurableTask,
    TaskBacklog,
    TaskKind,
    TaskRequest,
    TaskState,
    WorkflowRunPayload,
)

TENANT_ID = UUID("10000000-0000-0000-0000-000000000001")
TASK_ID = UUID("20000000-0000-0000-0000-000000000001")
CONVERSATION_ID = UUID("30000000-0000-0000-0000-000000000001")
TURN_ID = UUID("40000000-0000-0000-0000-000000000001")
USER_MESSAGE_ID = UUID("50000000-0000-0000-0000-000000000001")
ASSISTANT_MESSAGE_ID = UUID("60000000-0000-0000-0000-000000000001")
LEASE_TOKEN = UUID("70000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 21, 7, 0, tzinfo=UTC)


def _request() -> TaskRequest:
    return TaskRequest(
        task_id=TASK_ID,
        tenant_id=TENANT_ID,
        kind=TaskKind.CONVERSATION_REPLY,
        idempotency_key=f"conversation:{CONVERSATION_ID}:turn:{TURN_ID}",
        aggregate_id=CONVERSATION_ID,
        payload=ConversationReplyPayload(
            conversation_id=CONVERSATION_ID,
            turn_id=TURN_ID,
            user_message_id=USER_MESSAGE_ID,
            assistant_message_id=ASSISTANT_MESSAGE_ID,
            retry=False,
        ),
        created_at=NOW,
    )


def _pending() -> DurableTask:
    return DurableTask(
        request=_request(),
        state=TaskState.PENDING,
        attempts=0,
        max_attempts=3,
        available_at=NOW,
        lease_owner=None,
        lease_token=None,
        lease_until=None,
        stop_requested=False,
        error_code=None,
        updated_at=NOW,
    )


def test_task_contract_has_fixed_identifier_payloads_without_business_body() -> None:
    assert TaskKind.CONVERSATION_REPLY.value == "conversation.reply"
    assert TaskKind.WORKFLOW_RUN.value == "workflow.run"
    assert TaskState.RETRY_WAIT.value == "retry_wait"

    conversation_payload_fields = {field.name for field in fields(ConversationReplyPayload)}
    workflow_payload_fields = {field.name for field in fields(WorkflowRunPayload)}
    assert conversation_payload_fields == {
        "conversation_id",
        "turn_id",
        "user_message_id",
        "assistant_message_id",
        "retry",
    }
    assert workflow_payload_fields == {"run_id", "workflow_id"}
    assert not (conversation_payload_fields | workflow_payload_fields).intersection(
        {"body", "content", "input", "messages", "metadata", "prompt", "token"}
    )

    task_fields = {field.name for field in fields(DurableTask)}
    assert task_fields == {
        "request",
        "state",
        "attempts",
        "max_attempts",
        "available_at",
        "lease_owner",
        "lease_token",
        "lease_until",
        "stop_requested",
        "error_code",
        "updated_at",
    }


def test_running_task_requires_unique_lease_fencing_token() -> None:
    running = DurableTask(
        request=_request(),
        state=TaskState.RUNNING,
        attempts=1,
        max_attempts=3,
        available_at=NOW,
        lease_owner="worker-a",
        lease_token=LEASE_TOKEN,
        lease_until=NOW + timedelta(seconds=60),
        stop_requested=False,
        error_code=None,
        updated_at=NOW,
    )
    assert running.lease_token == LEASE_TOKEN

    with pytest.raises(ValueError, match="lease"):
        DurableTask(
            request=_request(),
            state=TaskState.RUNNING,
            attempts=1,
            max_attempts=3,
            available_at=NOW,
            lease_owner="worker-a",
            lease_token=None,
            lease_until=NOW + timedelta(seconds=60),
            stop_requested=False,
            error_code=None,
            updated_at=NOW,
        )


def test_task_rejects_kind_payload_mismatch_and_unsafe_identity() -> None:
    with pytest.raises(ValueError, match="payload"):
        TaskRequest(
            task_id=TASK_ID,
            tenant_id=TENANT_ID,
            kind=TaskKind.WORKFLOW_RUN,
            idempotency_key=f"workflow:{CONVERSATION_ID}",
            aggregate_id=CONVERSATION_ID,
            payload=_request().payload,
            created_at=NOW,
        )
    with pytest.raises(ValueError, match="idempotency"):
        TaskRequest(
            task_id=TASK_ID,
            tenant_id=TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=" contains spaces ",
            aggregate_id=CONVERSATION_ID,
            payload=_request().payload,
            created_at=NOW,
        )
    with pytest.raises(ValueError, match="UTC"):
        TaskRequest(
            task_id=TASK_ID,
            tenant_id=TENANT_ID,
            kind=TaskKind.CONVERSATION_REPLY,
            idempotency_key=f"conversation:{CONVERSATION_ID}:turn:{TURN_ID}",
            aggregate_id=CONVERSATION_ID,
            payload=_request().payload,
            created_at=datetime(2026, 7, 21, 7, 0),
        )


def test_pending_task_is_active_without_a_lease() -> None:
    pending = _pending()
    assert pending.is_active is True
    assert pending.is_terminal is False


def test_task_payload_and_request_reject_invalid_runtime_types_and_aggregate() -> None:
    payload = cast(ConversationReplyPayload, _request().payload)
    with pytest.raises(ValueError, match="retry"):
        replace(payload, retry=cast(bool, 1))
    with pytest.raises(ValueError, match="UUID"):
        replace(payload, conversation_id=cast(UUID, str(CONVERSATION_ID)))
    with pytest.raises(ValueError, match="kind"):
        replace(_request(), kind=cast(TaskKind, "conversation.reply"))
    with pytest.raises(ValueError, match="aggregate"):
        replace(_request(), aggregate_id=UUID(int=0))


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"request": object()}, "request"),
        ({"state": "pending"}, "state"),
        ({"attempts": True}, "attempts"),
        ({"max_attempts": True}, "max_attempts"),
        ({"max_attempts": 0}, "max_attempts"),
        ({"attempts": 4}, "attempts"),
        ({"updated_at": NOW - timedelta(seconds=1)}, "updated_at"),
        ({"stop_requested": 1}, "stop_requested"),
        ({"lease_owner": "worker-a"}, "only running"),
        ({"state": TaskState.FAILED}, "error_code"),
        ({"error_code": "unexpected"}, "error_code"),
    ],
)
def test_durable_task_rejects_inconsistent_persisted_state(
    changes: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_pending(), **changes)


def test_task_backlog_rejects_invalid_counts_and_timestamp() -> None:
    with pytest.raises(ValueError, match="pending"):
        TaskBacklog(pending=-1)
    with pytest.raises(ValueError, match="pending"):
        TaskBacklog(pending=True)
    with pytest.raises(ValueError, match="UTC"):
        TaskBacklog(oldest_available_at=datetime(2026, 7, 21, 7, 0))
