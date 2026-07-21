from __future__ import annotations

import pytest

from common_agent.bootstrap import ConfigurationError, WorkerSettings


def test_worker_settings_defaults_and_cross_field_bounds() -> None:
    assert WorkerSettings.from_mapping({}) == WorkerSettings(
        poll_interval_seconds=0.25,
        lease_seconds=60,
        heartbeat_seconds=10,
        maximum_attempts=3,
        claim_batch_size=8,
        event_retention_days=30,
        maximum_events_per_stream=100_000,
    )

    with pytest.raises(ConfigurationError, match="HEARTBEAT_SECONDS"):
        WorkerSettings.from_mapping(
            {
                "COMMON_AGENT_WORKER_LEASE_SECONDS": "30",
                "COMMON_AGENT_WORKER_HEARTBEAT_SECONDS": "15",
            }
        )
    with pytest.raises(ConfigurationError, match="MAXIMUM_ATTEMPTS"):
        WorkerSettings.from_mapping({"COMMON_AGENT_WORKER_MAXIMUM_ATTEMPTS": "11"})
    with pytest.raises(ConfigurationError, match="EVENT_MAX_PER_STREAM"):
        WorkerSettings.from_mapping({"COMMON_AGENT_EVENT_MAX_PER_STREAM": "1000001"})
    with pytest.raises(ConfigurationError, match="CLAIM_BATCH_SIZE"):
        WorkerSettings.from_mapping({"COMMON_AGENT_WORKER_CLAIM_BATCH_SIZE": "1"})
