from __future__ import annotations

import asyncio
from uuid import uuid4

import pytest

from common_agent.domain.workflow_run import WorkflowRun, WorkflowRunTrigger
from common_agent.workflows.events import (
    WorkflowEventBroker,
    WorkflowEventHistoryUnavailable,
    WorkflowEventKind,
    WorkflowEventStreamOverflow,
)


def _running_run() -> WorkflowRun:
    return WorkflowRun.create(
        workflow_id=uuid4(),
        trigger=WorkflowRunTrigger.MANUAL,
        input="input",
    ).start()


def test_workflow_events_are_sequenced_and_replay_persisted_snapshots() -> None:
    async def exercise() -> None:
        broker = WorkflowEventBroker(history_limit=4)
        running = _running_run()
        at_start = running.start_node("start")
        after_start = at_start.complete_node("start")

        first = await broker.publish(run=running, kind=WorkflowEventKind.RUN_STARTED)
        await broker.publish(
            run=at_start,
            kind=WorkflowEventKind.NODE_STARTED,
            node_id="start",
        )
        await broker.publish(
            run=after_start,
            kind=WorkflowEventKind.NODE_COMPLETED,
            node_id="start",
        )
        stream = broker.stream(running.id, after_sequence=1)
        replayed = [await anext(stream), await anext(stream)]
        await stream.aclose()

        assert first.sequence == 1
        assert [event.sequence for event in replayed] == [2, 3]
        assert replayed[0].run == at_start
        assert replayed[0].node_id == "start"

    asyncio.run(exercise())


def test_workflow_events_reject_state_mismatch_history_gap_and_slow_consumer() -> None:
    async def exercise() -> None:
        broker = WorkflowEventBroker(history_limit=1, subscriber_queue_limit=1)
        running = _running_run()
        with pytest.raises(ValueError, match="状态"):
            await broker.publish(run=running, kind=WorkflowEventKind.RUN_COMPLETED)

        stream = broker.stream(running.id)
        waiting = asyncio.create_task(anext(stream))
        await asyncio.sleep(0)
        await broker.publish(run=running, kind=WorkflowEventKind.RUN_STARTED)
        assert (await waiting).sequence == 1

        at_start = running.start_node("start")
        await broker.publish(
            run=at_start,
            kind=WorkflowEventKind.NODE_STARTED,
            node_id="start",
        )
        after_start = at_start.complete_node("start")
        await broker.publish(
            run=after_start,
            kind=WorkflowEventKind.NODE_COMPLETED,
            node_id="start",
        )
        with pytest.raises(WorkflowEventStreamOverflow):
            await anext(stream)
        await stream.aclose()
        with pytest.raises(WorkflowEventHistoryUnavailable):
            await broker.validate_resume(running.id, after_sequence=0)

    asyncio.run(exercise())
