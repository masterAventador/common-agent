from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from common_agent.domain.workflow_run import (
    WORKFLOW_RUN_INPUT_MAX_LENGTH,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunTransitionError,
    WorkflowRunTrigger,
    WorkflowRunValidationError,
)


def test_workflow_run_moves_through_nodes_to_completed_summary() -> None:
    now = datetime(2026, 7, 20, tzinfo=UTC)
    pending = WorkflowRun.create(
        workflow_id=uuid4(),
        trigger=WorkflowRunTrigger.MANUAL,
        input="原始输入",
        now=now,
    )
    running = pending.start(now=now + timedelta(microseconds=1))
    at_start = running.start_node("start", now=now + timedelta(microseconds=2))
    after_start = at_start.complete_node("start", now=now + timedelta(microseconds=3))
    at_end = after_start.start_node("end", now=now + timedelta(microseconds=4))
    after_end = at_end.complete_node("end", now=now + timedelta(microseconds=5))
    completed = after_end.complete("最终输出", now=now + timedelta(microseconds=6))

    assert pending.status is WorkflowRunStatus.PENDING
    assert completed.status is WorkflowRunStatus.COMPLETED
    assert completed.current_node_id == "end"
    assert completed.completed_node_ids == ("start", "end")
    assert completed.output == "最终输出"
    assert completed.started_at is not None
    assert completed.finished_at == completed.updated_at
    assert "原始输入" not in repr(completed)
    assert "最终输出" not in repr(completed)


def test_workflow_run_records_failure_and_stop_at_current_node() -> None:
    at_chat = (
        WorkflowRun.create(
            workflow_id=uuid4(),
            trigger=WorkflowRunTrigger.EMPLOYEE,
            input="执行输入",
        )
        .start()
        .start_node("chat")
    )

    failed = at_chat.fail("model_unavailable")
    stopped = at_chat.stop()

    assert failed.status is WorkflowRunStatus.FAILED
    assert failed.failed_node_id == "chat"
    assert failed.error_code == "model_unavailable"
    assert failed.output == ""
    assert stopped.status is WorkflowRunStatus.STOPPED
    assert stopped.current_node_id == "chat"
    assert stopped.failed_node_id is None
    assert stopped.error_code is None


def test_workflow_run_rejects_invalid_content_order_and_terminal_reentry() -> None:
    with pytest.raises(WorkflowRunValidationError):
        WorkflowRun.create(
            workflow_id=uuid4(),
            trigger=WorkflowRunTrigger.MANUAL,
            input="x" * (WORKFLOW_RUN_INPUT_MAX_LENGTH + 1),
        )

    pending = WorkflowRun.create(
        workflow_id=uuid4(),
        trigger=WorkflowRunTrigger.MANUAL,
        input="input",
    )
    with pytest.raises(WorkflowRunTransitionError):
        pending.start_node("start")

    running = pending.start()
    with pytest.raises(WorkflowRunTransitionError):
        running.complete_node("start")
    after_start = running.start_node("start").complete_node("start")
    with pytest.raises(WorkflowRunTransitionError):
        after_start.start_node("start")

    completed = after_start.complete("output")
    with pytest.raises(WorkflowRunTransitionError):
        completed.stop()
