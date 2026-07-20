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
    WorkflowEventSubscriberLimitExceeded,
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


def test_workflow_event_states_are_lru_bounded_and_ttl_expired() -> None:
    async def exercise() -> None:
        broker = WorkflowEventBroker(
            history_limit=4,
            state_limit=12,
            state_ttl_seconds=0.02,
        )
        active = _running_run()
        active_event = await broker.publish(run=active, kind=WorkflowEventKind.RUN_STARTED)

        for _ in range(300):
            running = _running_run()
            await broker.publish(run=running, kind=WorkflowEventKind.RUN_STARTED)
            completed = running.complete("done")
            await broker.publish(run=completed, kind=WorkflowEventKind.RUN_COMPLETED)

        bounded = await broker.lifecycle_snapshot()
        assert bounded.state_count <= 12
        assert bounded.active_state_count == 1
        assert bounded.retained_event_count <= 12 * 4

        active_stream = broker.stream(active.id)
        assert await anext(active_stream) == active_event
        await asyncio.sleep(0.04)
        assert (await broker.lifecycle_snapshot()).state_count == 1
        await active_stream.aclose()

        stopped = active.stop()
        terminal = await broker.publish(run=stopped, kind=WorkflowEventKind.RUN_STOPPED)
        await asyncio.sleep(0.04)
        assert (await broker.lifecycle_snapshot()).state_count == 0
        with pytest.raises(WorkflowEventHistoryUnavailable):
            await broker.validate_resume(active.id, after_sequence=terminal.sequence)
        await broker.aclose()

    asyncio.run(exercise())


def test_workflow_event_broker_globally_bounds_subscribers_and_closes_waiters() -> None:
    async def exercise() -> None:
        broker = WorkflowEventBroker(
            state_limit=1,
            subscriber_limit=4,
            total_subscriber_limit=1,
        )
        first = _running_run()
        first_stream = broker.stream(first.id)
        first_waiter = asyncio.create_task(anext(first_stream))
        await asyncio.sleep(0)

        second_stream = broker.stream(_running_run().id)
        with pytest.raises(WorkflowEventSubscriberLimitExceeded, match="订阅者"):
            await anext(second_stream)
        await second_stream.aclose()

        await broker.aclose()
        with pytest.raises(WorkflowEventStreamOverflow):
            await first_waiter
        await first_stream.aclose()
        with pytest.raises(RuntimeError, match="closed"):
            await broker.publish(run=first, kind=WorkflowEventKind.RUN_STARTED)

    asyncio.run(exercise())


@pytest.mark.parametrize(
    "arguments",
    [
        {"history_limit": 0},
        {"subscriber_queue_limit": 0},
        {"subscriber_limit": 0},
        {"total_subscriber_limit": 0},
        {"state_limit": 0},
        {"state_ttl_seconds": 0},
        {"state_ttl_seconds": 86_401},
    ],
)
def test_workflow_event_broker_rejects_invalid_lifecycle_limits(
    arguments: dict[str, int],
) -> None:
    with pytest.raises(ValueError):
        WorkflowEventBroker(**arguments)
