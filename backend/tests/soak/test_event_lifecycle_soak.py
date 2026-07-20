from __future__ import annotations

import asyncio

from tests.soak.event_lifecycle_soak import run_lifecycle_soak


def test_short_event_and_lock_lifecycle_soak_returns_to_baseline() -> None:
    result = asyncio.run(
        run_lifecycle_soak(
            duration_seconds=0.1,
            batch_size=10,
            state_limit=32,
            state_ttl_seconds=0.01,
        )
    )

    assert result.cycles >= 10
    assert result.max_conversation_states <= 32
    assert result.max_workflow_states <= 32
    assert result.retained_bytes <= 2 * 1024 * 1024
