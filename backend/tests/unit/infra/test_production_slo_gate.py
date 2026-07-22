from __future__ import annotations

import importlib.util
import json
import sys
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[4]
SCRIPT_PATH = REPOSITORY_ROOT / "infra" / "production" / "slo_gate.py"
POLICY_PATH = REPOSITORY_ROOT / "infra" / "production" / "slo-policy.json"
SPEC = importlib.util.spec_from_file_location("common_agent_production_slo_gate", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("无法加载生产 SLO 门禁")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def healthy_evidence() -> dict[str, Any]:
    containers = {
        "common-agent-production-api-blue": {
            "cpu_percent": 35.0,
            "memory_bytes": 512 * 1024**2,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-production-worker-blue": {
            "cpu_percent": 45.0,
            "memory_bytes": 768 * 1024**2,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-production-platform-mysql": {
            "cpu_percent": 20.0,
            "memory_bytes": 600 * 1024**2,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-production-web-blue": {
            "cpu_percent": 2.0,
            "memory_bytes": 32 * 1024**2,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-production-edge": {
            "cpu_percent": 3.0,
            "memory_bytes": 32 * 1024**2,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-ragflow-api": {
            "cpu_percent": 50.0,
            "memory_bytes": 4 * 1024**3,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-ragflow-elasticsearch": {
            "cpu_percent": 30.0,
            "memory_bytes": 2 * 1024**3,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-ragflow-mysql": {
            "cpu_percent": 20.0,
            "memory_bytes": 1024**3,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-ragflow-minio": {
            "cpu_percent": 5.0,
            "memory_bytes": 256 * 1024**2,
            "oom_killed": False,
            "restart_count": 0,
        },
        "common-agent-ragflow-valkey": {
            "cpu_percent": 5.0,
            "memory_bytes": 128 * 1024**2,
            "oom_killed": False,
            "restart_count": 0,
        },
    }
    sample = {
        "elapsed_seconds": 300.0,
        "edge_healthy": True,
        "containers": containers,
    }
    return {
        "api": {
            "requests_total": 1500,
            "failure_rate": 0.0,
            "dropped_iterations": 0,
            "p95_ms": 8.2,
            "p99_ms": 9.0,
        },
        "sse": {
            "requested_connections": 128,
            "established_connections": 128,
            "alive_at_deadline": 128,
            "unexpected_disconnects": 0,
            "handshake_p95_ms": 22.9,
            "requests_in_flight": 0,
        },
        "worker": {
            "capacity": {
                "requested_tasks": 24,
                "accepted_tasks": 24,
                "completed_tasks": 24,
                "failed_tasks": 0,
                "enqueue_p95_ms": 144.5,
                "completion_seconds": 9.31,
            },
            "recovery": {
                "requested_tasks": 8,
                "accepted_tasks": 8,
                "completed_tasks": 8,
                "failed_tasks": 0,
                "enqueue_p95_ms": 84.7,
                "completion_seconds": 70.28,
                "max_attempts": 2,
            },
        },
        "resources": {
            "configured_interval_seconds": 5,
            "sampling_errors": [],
            "samples": [sample, deepcopy(sample)],
        },
        "backup": {"age_hours": 0.1, "restore_drill_age_days": 0.0},
    }


def test_versioned_policy_defines_slos_budgets_and_actionable_alerts() -> None:
    policy = MODULE.load_policy(POLICY_PATH)

    assert policy["schema_version"] == 1
    assert policy["slo"]["availability_target"] == 0.999
    assert policy["slo"]["api_failure_rate_max"] == 0.001
    assert policy["slo"]["api_p95_ms_max"] == 500
    assert policy["resource_budgets"]["business_node_memory_bytes_max"] == 12 * 1024**3
    assert policy["resource_budgets"]["ragflow_node_memory_bytes_max"] == 24 * 1024**3
    assert {alert["code"] for alert in policy["alerts"]} >= {
        "edge_availability_burn",
        "api_error_budget_burn",
        "api_latency_breach",
        "sse_capacity_breach",
        "worker_backlog_breach",
        "worker_recovery_breach",
        "business_resource_pressure",
        "ragflow_resource_pressure",
        "container_restart_or_oom",
        "backup_rpo_breach",
        "restore_drill_stale",
    }
    assert all(alert["severity"] in {"warning", "critical"} for alert in policy["alerts"])
    assert all(alert["runbook"] for alert in policy["alerts"])


def test_healthy_formal_evidence_satisfies_every_slo_and_resource_budget() -> None:
    result = MODULE.evaluate(MODULE.load_policy(POLICY_PATH), healthy_evidence())

    assert result["status"] == "passed"
    assert result["alerts"] == []
    assert result["summary"]["availability"] == 1.0
    assert result["summary"]["business_memory_peak_bytes"] < 12 * 1024**3
    assert result["summary"]["ragflow_memory_peak_bytes"] < 24 * 1024**3


def test_runtime_scope_is_explicit_and_does_not_fabricate_backup_evidence() -> None:
    evidence = healthy_evidence()
    del evidence["backup"]

    result = MODULE.evaluate(MODULE.load_policy(POLICY_PATH), evidence, require_backup=False)

    assert result["status"] == "passed"
    assert result["scope"] == "runtime"
    assert result["backup_status"] == "not_evaluated"
    with pytest.raises(MODULE.SloGateFailure, match="backup"):
        MODULE.evaluate(MODULE.load_policy(POLICY_PATH), evidence)


@pytest.mark.parametrize(
    ("mutate", "expected_code"),
    [
        (
            lambda value: value["resources"]["samples"][0].update(edge_healthy=False),
            "edge_availability_burn",
        ),
        (lambda value: value["api"].update(failure_rate=0.0011), "api_error_budget_burn"),
        (lambda value: value["api"].update(p95_ms=500.1), "api_latency_breach"),
        (
            lambda value: value["sse"].update(alive_at_deadline=127),
            "sse_capacity_breach",
        ),
        (
            lambda value: value["worker"]["capacity"].update(completed_tasks=23),
            "worker_backlog_breach",
        ),
        (
            lambda value: value["worker"]["recovery"].update(max_attempts=1),
            "worker_recovery_breach",
        ),
        (
            lambda value: value["resources"]["samples"][0]["containers"][
                "common-agent-production-api-blue"
            ].update(memory_bytes=13 * 1024**3),
            "business_resource_pressure",
        ),
        (
            lambda value: value["resources"]["samples"][0]["containers"][
                "common-agent-ragflow-api"
            ].update(memory_bytes=25 * 1024**3),
            "ragflow_resource_pressure",
        ),
        (
            lambda value: value["resources"]["samples"][0]["containers"][
                "common-agent-production-api-blue"
            ].update(oom_killed=True),
            "container_restart_or_oom",
        ),
        (lambda value: value["backup"].update(age_hours=24.1), "backup_rpo_breach"),
        (
            lambda value: value["backup"].update(restore_drill_age_days=90.1),
            "restore_drill_stale",
        ),
    ],
)
def test_each_alert_condition_closes_the_gate(
    mutate: Callable[[dict[str, Any]], None], expected_code: str
) -> None:
    evidence = healthy_evidence()
    mutate(evidence)

    result = MODULE.evaluate(MODULE.load_policy(POLICY_PATH), evidence)

    assert result["status"] == "failed"
    assert expected_code in {alert["code"] for alert in result["alerts"]}


def test_missing_or_corrupt_resource_samples_close_the_gate() -> None:
    evidence = healthy_evidence()
    evidence["resources"]["samples"] = []
    with pytest.raises(MODULE.SloGateFailure, match="resource samples"):
        MODULE.evaluate(MODULE.load_policy(POLICY_PATH), evidence)


def test_restart_or_oom_alert_names_the_exact_container() -> None:
    evidence = healthy_evidence()
    container_name = "common-agent-production-api-blue"
    evidence["resources"]["samples"][0]["containers"][container_name]["restart_count"] = 1

    result = MODULE.evaluate(MODULE.load_policy(POLICY_PATH), evidence)
    alert = next(item for item in result["alerts"] if item["code"] == "container_restart_or_oom")

    assert container_name in alert["detail"]
    assert "restart_count=1" in alert["detail"]

    evidence = healthy_evidence()
    evidence["resources"]["sampling_errors"] = [{"type": "DockerError"}]
    with pytest.raises(MODULE.SloGateFailure, match="sampling errors"):
        MODULE.evaluate(MODULE.load_policy(POLICY_PATH), evidence)


def test_cli_writes_private_machine_readable_result(tmp_path: Path) -> None:
    evidence_path = tmp_path / "evidence.json"
    output_path = tmp_path / "result.json"
    evidence_path.write_text(json.dumps(healthy_evidence()), encoding="utf-8")

    assert MODULE.main([str(POLICY_PATH), str(evidence_path), str(output_path)]) == 0
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "passed"
    assert output_path.stat().st_mode & 0o777 == 0o600
