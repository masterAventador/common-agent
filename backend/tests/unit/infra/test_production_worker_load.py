from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[4] / "infra" / "production" / "worker_load_test.py"
SPEC = importlib.util.spec_from_file_location("common_agent_production_worker_load", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("无法加载生产 Worker 容量压测入口")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def valid_environment(tmp_path: Path) -> dict[str, str]:
    return {
        "COMMON_AGENT_PERFORMANCE_BASE_URL": "https://127.0.0.1:18443",
        "COMMON_AGENT_PERFORMANCE_HOST": "common-agent.test",
        "COMMON_AGENT_PERFORMANCE_EMAIL": "owner@example.com",
        "COMMON_AGENT_PERFORMANCE_PASSWORD": "owner-password",
        "COMMON_AGENT_PERFORMANCE_CA_FILE": str(tmp_path / "ca.crt"),
        "COMMON_AGENT_WORKER_LOAD_STATE": str(tmp_path / "worker-load.json"),
        "COMMON_AGENT_WORKER_CAPACITY_TASKS": "24",
        "COMMON_AGENT_WORKER_RECOVERY_TASKS": "8",
        "COMMON_AGENT_WORKER_WRITE_CONCURRENCY": "12",
        "COMMON_AGENT_WORKER_ENQUEUE_P95_MS": "1000",
        "COMMON_AGENT_WORKER_DRAIN_TIMEOUT_SECONDS": "120",
        "COMMON_AGENT_WORKER_RECOVERY_TIMEOUT_SECONDS": "300",
    }


def test_settings_require_bounded_capacity_recovery_and_private_state(
    tmp_path: Path,
) -> None:
    (tmp_path / "ca.crt").write_text("test ca", encoding="utf-8")

    settings = MODULE.WorkerLoadSettings.from_environment(valid_environment(tmp_path))

    assert settings.capacity_tasks == 24
    assert settings.recovery_tasks == 8
    assert settings.write_concurrency == 12
    assert settings.enqueue_p95_limit_ms == 1000
    assert settings.drain_timeout_seconds == 120
    assert settings.recovery_timeout_seconds == 300
    assert settings.state_file == tmp_path / "worker-load.json"

    with pytest.raises(ValueError, match="capacity tasks"):
        MODULE.WorkerLoadSettings.from_environment(
            valid_environment(tmp_path) | {"COMMON_AGENT_WORKER_CAPACITY_TASKS": "0"}
        )
    with pytest.raises(ValueError, match="write concurrency"):
        MODULE.WorkerLoadSettings.from_environment(
            valid_environment(tmp_path) | {"COMMON_AGENT_WORKER_WRITE_CONCURRENCY": "65"}
        )
    with pytest.raises(ValueError, match="drain timeout"):
        MODULE.WorkerLoadSettings.from_environment(
            valid_environment(tmp_path) | {"COMMON_AGENT_WORKER_DRAIN_TIMEOUT_SECONDS": "29"}
        )


def test_phase_state_is_written_0600_and_rejects_symlink(tmp_path: Path) -> None:
    state_file = tmp_path / "worker-load.json"
    state = {
        "session_cookie": "__Host-common-agent-session=opaque",
        "csrf_token": "csrf-token",
        "tenant_id": "00000000-0000-4000-8000-000000000001",
        "model_id": "00000000-0000-4000-8000-000000000002",
        "phases": {},
    }

    MODULE.save_state(state_file, state)

    assert json.loads(state_file.read_text(encoding="utf-8")) == state
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600

    state_file.unlink()
    state_file.symlink_to(tmp_path / "target.json")
    with pytest.raises(MODULE.WorkerLoadFailure, match="symbolic link"):
        MODULE.save_state(state_file, state)


def test_aggregate_ids_are_strictly_validated_for_database_observation() -> None:
    phase = {
        "records": [
            {"conversation_id": "00000000-0000-4000-8000-000000000001"},
            {"conversation_id": "00000000-0000-4000-8000-000000000002"},
        ]
    }

    assert MODULE.aggregate_ids(phase) == (
        "'00000000-0000-4000-8000-000000000001','00000000-0000-4000-8000-000000000002'"
    )

    with pytest.raises(MODULE.WorkerLoadFailure, match="conversation id"):
        MODULE.aggregate_ids({"records": [{"conversation_id": "x' OR 1=1 --"}]})


def test_result_rejects_partial_writes_slow_enqueue_and_incomplete_tasks() -> None:
    healthy = MODULE.WorkerLoadResult(
        requested_tasks=24,
        accepted_tasks=24,
        completed_tasks=24,
        failed_tasks=0,
        enqueue_p95_ms=250.0,
        completion_seconds=45.0,
    )
    MODULE.ensure_success(
        healthy,
        enqueue_p95_limit_ms=1000,
        completion_limit_seconds=120,
    )

    failures = (
        MODULE.WorkerLoadResult(24, 23, 23, 0, 250.0, 45.0),
        MODULE.WorkerLoadResult(24, 24, 23, 1, 250.0, 45.0),
        MODULE.WorkerLoadResult(24, 24, 24, 0, 1000.1, 45.0),
        MODULE.WorkerLoadResult(24, 24, 24, 0, 250.0, 120.1),
    )
    for result in failures:
        with pytest.raises(MODULE.WorkerLoadFailure):
            MODULE.ensure_success(
                result,
                enqueue_p95_limit_ms=1000,
                completion_limit_seconds=120,
            )

    with pytest.raises(MODULE.WorkerLoadFailure, match="drain took"):
        MODULE.ensure_success(
            MODULE.WorkerLoadResult(8, 8, 8, 0, 250.0, 300.1),
            enqueue_p95_limit_ms=1000,
            completion_limit_seconds=300,
        )


def test_terminal_message_validation_requires_exact_completed_reply() -> None:
    record = {
        "conversation_id": "00000000-0000-4000-8000-000000000001",
        "user_message_id": "00000000-0000-4000-8000-000000000002",
        "assistant_message_id": "00000000-0000-4000-8000-000000000003",
    }
    messages = [
        {
            "id": record["user_message_id"],
            "role": "user",
            "status": "completed",
            "content": "capacity probe",
        },
        {
            "id": record["assistant_message_id"],
            "role": "assistant",
            "status": "completed",
            "content": "ok",
        },
    ]

    assert MODULE.terminal_outcome(record, messages) == "completed"
    assert (
        MODULE.terminal_outcome(
            record, [messages[0], messages[1] | {"status": "streaming", "content": ""}]
        )
        is None
    )

    with pytest.raises(MODULE.WorkerLoadFailure, match="failed"):
        MODULE.terminal_outcome(
            record,
            [
                messages[0],
                messages[1] | {"status": "failed", "content": "", "error_code": "model_failed"},
            ],
        )
    with pytest.raises(MODULE.WorkerLoadFailure, match="message set"):
        MODULE.terminal_outcome(record, [messages[0]])
