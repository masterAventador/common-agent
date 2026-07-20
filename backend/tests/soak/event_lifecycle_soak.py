from __future__ import annotations

import argparse
import asyncio
import gc
import json
import tracemalloc
from dataclasses import asdict, dataclass
from time import monotonic
from uuid import uuid4

from common_agent.concurrency import KeyedLockPool
from common_agent.conversations.events import ConversationEventBroker, ConversationEventKind
from common_agent.domain.conversation import Message
from common_agent.domain.workflow_run import WorkflowRun, WorkflowRunTrigger
from common_agent.workflows.events import WorkflowEventBroker, WorkflowEventKind


@dataclass(frozen=True, slots=True)
class LifecycleSoakResult:
    cycles: int
    peak_bytes: int
    retained_bytes: int
    max_conversation_states: int
    max_workflow_states: int


async def run_lifecycle_soak(
    *,
    duration_seconds: float,
    batch_size: int = 25,
    state_limit: int = 128,
    state_ttl_seconds: float = 0.05,
) -> LifecycleSoakResult:
    if duration_seconds <= 0 or duration_seconds > 3600:
        raise ValueError("duration_seconds must be between 0 and 3600")
    if batch_size < 1 or batch_size > 1000:
        raise ValueError("batch_size must be between 1 and 1000")

    conversations = ConversationEventBroker(
        history_limit=8,
        state_limit=state_limit,
        state_ttl_seconds=state_ttl_seconds,
    )
    workflows = WorkflowEventBroker(
        history_limit=8,
        state_limit=state_limit,
        state_ttl_seconds=state_ttl_seconds,
    )
    locks: KeyedLockPool[str] = KeyedLockPool()
    tracing_was_active = tracemalloc.is_tracing()
    if not tracing_was_active:
        tracemalloc.start()
    baseline_bytes = tracemalloc.get_traced_memory()[0]
    deadline = monotonic() + duration_seconds
    cycles = 0
    max_conversation_states = 0
    max_workflow_states = 0

    try:
        while monotonic() < deadline:
            for _ in range(batch_size):
                conversation_id = uuid4()
                turn_id = uuid4()
                pending = Message.create_assistant(
                    conversation_id=conversation_id,
                    sequence_number=2,
                )
                streaming = pending.append_delta("x")
                completed = streaming.complete()
                await conversations.publish(
                    turn_id=turn_id,
                    message=pending,
                    kind=ConversationEventKind.ASSISTANT_STARTED,
                )
                await conversations.publish(
                    turn_id=turn_id,
                    message=streaming,
                    kind=ConversationEventKind.ASSISTANT_DELTA,
                    delta="x",
                )
                await conversations.publish(
                    turn_id=turn_id,
                    message=completed,
                    kind=ConversationEventKind.ASSISTANT_COMPLETED,
                )

                running = WorkflowRun.create(
                    workflow_id=uuid4(),
                    trigger=WorkflowRunTrigger.MANUAL,
                    input="input",
                ).start()
                await workflows.publish(run=running, kind=WorkflowEventKind.RUN_STARTED)
                await workflows.publish(
                    run=running.complete("done"),
                    kind=WorkflowEventKind.RUN_COMPLETED,
                )

                async with locks.hold(str(uuid4())):
                    pass
                cycles += 1

            conversation_snapshot = await conversations.lifecycle_snapshot()
            workflow_snapshot = await workflows.lifecycle_snapshot()
            max_conversation_states = max(
                max_conversation_states,
                conversation_snapshot.state_count,
            )
            max_workflow_states = max(
                max_workflow_states,
                workflow_snapshot.state_count,
            )
            if conversation_snapshot.state_count > state_limit:
                raise AssertionError("conversation event states exceeded the configured limit")
            if workflow_snapshot.state_count > state_limit:
                raise AssertionError("workflow event states exceeded the configured limit")
            await asyncio.sleep(0)

        await asyncio.sleep(state_ttl_seconds * 2)
        conversation_snapshot = await conversations.lifecycle_snapshot()
        workflow_snapshot = await workflows.lifecycle_snapshot()
        lock_snapshot = await locks.snapshot()
        if conversation_snapshot.state_count != 0:
            raise AssertionError("conversation event states did not return to zero")
        if workflow_snapshot.state_count != 0:
            raise AssertionError("workflow event states did not return to zero")
        if lock_snapshot.entry_count != 0:
            raise AssertionError("keyed locks did not return to zero")

        gc.collect()
        retained, peak = tracemalloc.get_traced_memory()
        retained_delta = max(0, retained - baseline_bytes)
        if retained_delta > 2 * 1024 * 1024:
            raise AssertionError(
                f"lifecycle soak retained too much traced memory: {retained_delta} bytes"
            )
        return LifecycleSoakResult(
            cycles=cycles,
            peak_bytes=max(0, peak - baseline_bytes),
            retained_bytes=retained_delta,
            max_conversation_states=max_conversation_states,
            max_workflow_states=max_workflow_states,
        )
    finally:
        await conversations.aclose()
        await workflows.aclose()
        if not tracing_was_active:
            tracemalloc.stop()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=float, default=60)
    parser.add_argument("--batch-size", type=int, default=25)
    arguments = parser.parse_args()
    result = asyncio.run(
        run_lifecycle_soak(
            duration_seconds=arguments.duration_seconds,
            batch_size=arguments.batch_size,
        )
    )
    print(json.dumps(asdict(result), sort_keys=True))


if __name__ == "__main__":
    main()
