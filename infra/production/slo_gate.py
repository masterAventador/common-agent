#!/usr/bin/env python3
"""Evaluate production SLO, resource-budget, backup, and alert evidence."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any


class SloGateFailure(RuntimeError):
    """Raised when evidence or policy cannot be evaluated safely."""


def _object(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise SloGateFailure(f"{label} must be an object")
    return value


def _array(value: object, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise SloGateFailure(f"{label} must be an array")
    return value


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SloGateFailure(f"{label} must be a number")
    result = float(value)
    if result < 0 or result != result or result in {float("inf"), float("-inf")}:
        raise SloGateFailure(f"{label} must be a finite non-negative number")
    return result


def _integer(value: object, label: str) -> int:
    number = _number(value, label)
    if not number.is_integer():
        raise SloGateFailure(f"{label} must be an integer")
    return int(number)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise SloGateFailure(f"{label} must be a boolean")
    return value


def _read_json(path: Path, label: str) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise SloGateFailure(f"{label} must be a regular file")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SloGateFailure(f"{label} is unreadable or invalid") from error
    return dict(_object(payload, label))


def load_policy(path: Path) -> dict[str, Any]:
    policy = _read_json(path, "policy")
    if policy.get("schema_version") != 1:
        raise SloGateFailure("policy schema_version must be 1")
    _object(policy.get("window"), "policy.window")
    _object(policy.get("slo"), "policy.slo")
    _object(policy.get("resource_budgets"), "policy.resource_budgets")
    alerts = _array(policy.get("alerts"), "policy.alerts")
    codes: set[str] = set()
    for index, raw in enumerate(alerts):
        alert = _object(raw, f"policy.alerts[{index}]")
        code = alert.get("code")
        if not isinstance(code, str) or not code or code in codes:
            raise SloGateFailure("policy alert codes must be unique non-empty strings")
        if alert.get("severity") not in {"warning", "critical"}:
            raise SloGateFailure(f"policy alert {code} has invalid severity")
        if not isinstance(alert.get("condition"), str) or not alert["condition"]:
            raise SloGateFailure(f"policy alert {code} has no condition")
        if not isinstance(alert.get("runbook"), str) or not alert["runbook"]:
            raise SloGateFailure(f"policy alert {code} has no runbook")
        codes.add(code)
    return policy


def _alert_catalog(policy: Mapping[str, Any]) -> dict[str, dict[str, str]]:
    catalog: dict[str, dict[str, str]] = {}
    for raw in _array(policy["alerts"], "policy.alerts"):
        alert = _object(raw, "policy alert")
        code = str(alert["code"])
        catalog[code] = {
            "code": code,
            "severity": str(alert["severity"]),
            "condition": str(alert["condition"]),
            "runbook": str(alert["runbook"]),
        }
    return catalog


def _add_alert(
    active: list[dict[str, str]],
    catalog: Mapping[str, dict[str, str]],
    code: str,
    detail: str,
) -> None:
    definition = catalog.get(code)
    if definition is None:
        raise SloGateFailure(f"policy does not define alert {code}")
    active.append(definition | {"detail": detail})


def _resource_summary(policy: Mapping[str, Any], evidence: Mapping[str, Any]) -> dict[str, Any]:
    resources = _object(evidence.get("resources"), "evidence.resources")
    errors = _array(resources.get("sampling_errors"), "resource sampling errors")
    if errors:
        raise SloGateFailure("resource sampling errors are not allowed")
    samples = _array(resources.get("samples"), "resource samples")
    if not samples:
        raise SloGateFailure("resource samples must not be empty")
    minimum_samples = _integer(
        _object(policy["window"], "policy.window").get("resource_minimum_samples"),
        "policy resource minimum samples",
    )
    if len(samples) < minimum_samples:
        raise SloGateFailure("resource samples do not cover the minimum window")

    healthy = 0
    business_memory_peak = 0
    ragflow_memory_peak = 0
    business_cpu_peak = 0.0
    ragflow_cpu_peak = 0.0
    restart_or_oom: dict[str, tuple[int, bool]] = {}
    for index, raw_sample in enumerate(samples):
        sample = _object(raw_sample, f"resource sample {index}")
        if _boolean(sample.get("edge_healthy"), f"resource sample {index} edge health"):
            healthy += 1
        containers = _object(sample.get("containers"), f"resource sample {index} containers")
        business_memory = 0
        ragflow_memory = 0
        business_cpu = 0.0
        ragflow_cpu = 0.0
        business_count = 0
        ragflow_count = 0
        for name, raw_state in containers.items():
            if not isinstance(name, str) or not name.startswith("common-agent-"):
                raise SloGateFailure("resource sample contains an unexpected container name")
            state = _object(raw_state, f"container {name}")
            memory = _integer(state.get("memory_bytes"), f"container {name} memory")
            cpu = _number(state.get("cpu_percent"), f"container {name} cpu")
            restarted = _integer(state.get("restart_count"), f"container {name} restarts")
            oom = _boolean(state.get("oom_killed"), f"container {name} OOM")
            if restarted > 0 or oom:
                previous_restart, previous_oom = restart_or_oom.get(name, (0, False))
                restart_or_oom[name] = (
                    max(restarted, previous_restart),
                    oom or previous_oom,
                )
            if name.startswith("common-agent-ragflow-") or name == (
                "common-agent-production-ragflow-edge"
            ):
                ragflow_count += 1
                ragflow_memory += memory
                ragflow_cpu += cpu / 100
            elif name.startswith("common-agent-production-"):
                business_count += 1
                business_memory += memory
                business_cpu += cpu / 100
        if business_count == 0 or ragflow_count == 0:
            raise SloGateFailure("resource samples must include business and RAGFlow containers")
        business_memory_peak = max(business_memory_peak, business_memory)
        ragflow_memory_peak = max(ragflow_memory_peak, ragflow_memory)
        business_cpu_peak = max(business_cpu_peak, business_cpu)
        ragflow_cpu_peak = max(ragflow_cpu_peak, ragflow_cpu)
    return {
        "availability": healthy / len(samples),
        "resource_samples": len(samples),
        "business_memory_peak_bytes": business_memory_peak,
        "ragflow_memory_peak_bytes": ragflow_memory_peak,
        "business_cpu_peak_cores": business_cpu_peak,
        "ragflow_cpu_peak_cores": ragflow_cpu_peak,
        "container_restart_or_oom": bool(restart_or_oom),
        "container_restart_or_oom_details": [
            f"{name}(restart_count={restart_count},oom={str(oom).lower()})"
            for name, (restart_count, oom) in sorted(restart_or_oom.items())
        ],
    }


def evaluate(
    policy: Mapping[str, Any],
    evidence: Mapping[str, Any],
    *,
    require_backup: bool = True,
) -> dict[str, Any]:
    slo = _object(policy.get("slo"), "policy.slo")
    budgets = _object(policy.get("resource_budgets"), "policy.resource_budgets")
    catalog = _alert_catalog(policy)
    alerts: list[dict[str, str]] = []
    summary = _resource_summary(policy, evidence)

    availability_target = _number(slo.get("availability_target"), "availability target")
    if summary["availability"] < availability_target:
        _add_alert(
            alerts,
            catalog,
            "edge_availability_burn",
            f"observed={summary['availability']:.6f}, target={availability_target:.6f}",
        )

    api = _object(evidence.get("api"), "evidence.api")
    requests_total = _integer(api.get("requests_total"), "API requests total")
    failure_rate = _number(api.get("failure_rate"), "API failure rate")
    dropped = _integer(api.get("dropped_iterations"), "API dropped iterations")
    api_p95 = _number(api.get("p95_ms"), "API p95")
    api_p99 = _number(api.get("p99_ms"), "API p99")
    if requests_total < 1:
        raise SloGateFailure("API evidence contains no requests")
    if failure_rate > _number(slo.get("api_failure_rate_max"), "API failure limit") or (
        dropped > _integer(slo.get("api_dropped_iterations_max"), "API dropped limit")
    ):
        _add_alert(
            alerts,
            catalog,
            "api_error_budget_burn",
            f"failure_rate={failure_rate:.6f}, dropped_iterations={dropped}",
        )
    if api_p95 > _number(slo.get("api_p95_ms_max"), "API p95 limit") or api_p99 > (
        _number(slo.get("api_p99_ms_max"), "API p99 limit")
    ):
        _add_alert(
            alerts,
            catalog,
            "api_latency_breach",
            f"p95_ms={api_p95:.2f}, p99_ms={api_p99:.2f}",
        )

    sse = _object(evidence.get("sse"), "evidence.sse")
    sse_requested = _integer(sse.get("requested_connections"), "SSE requested")
    sse_minimum = _integer(slo.get("sse_connections_min"), "SSE connection minimum")
    sse_failed = (
        sse_requested < sse_minimum
        or _integer(sse.get("established_connections"), "SSE established") != sse_requested
        or _integer(sse.get("alive_at_deadline"), "SSE alive") != sse_requested
        or _integer(sse.get("unexpected_disconnects"), "SSE disconnects") != 0
        or _number(sse.get("handshake_p95_ms"), "SSE handshake p95")
        > _number(slo.get("sse_handshake_p95_ms_max"), "SSE handshake limit")
        or _integer(sse.get("requests_in_flight"), "SSE requests in flight") != 0
    )
    if sse_failed:
        _add_alert(alerts, catalog, "sse_capacity_breach", "SSE capacity evidence breached")

    worker = _object(evidence.get("worker"), "evidence.worker")
    capacity = _object(worker.get("capacity"), "worker capacity")
    capacity_requested = _integer(capacity.get("requested_tasks"), "capacity requested")
    capacity_failed = (
        capacity_requested < _integer(slo.get("worker_capacity_tasks_min"), "capacity minimum")
        or _integer(capacity.get("accepted_tasks"), "capacity accepted") != capacity_requested
        or _integer(capacity.get("completed_tasks"), "capacity completed") != capacity_requested
        or _integer(capacity.get("failed_tasks"), "capacity failed") != 0
        or _number(capacity.get("enqueue_p95_ms"), "capacity enqueue p95")
        > _number(slo.get("worker_enqueue_p95_ms_max"), "worker enqueue limit")
        or _number(capacity.get("completion_seconds"), "capacity completion")
        > _number(slo.get("worker_capacity_seconds_max"), "capacity completion limit")
    )
    if capacity_failed:
        _add_alert(
            alerts,
            catalog,
            "worker_backlog_breach",
            "Worker capacity evidence breached",
        )

    recovery = _object(worker.get("recovery"), "worker recovery")
    recovery_requested = _integer(recovery.get("requested_tasks"), "recovery requested")
    recovery_failed = (
        recovery_requested < _integer(slo.get("worker_recovery_tasks_min"), "recovery minimum")
        or _integer(recovery.get("accepted_tasks"), "recovery accepted") != recovery_requested
        or _integer(recovery.get("completed_tasks"), "recovery completed") != recovery_requested
        or _integer(recovery.get("failed_tasks"), "recovery failed") != 0
        or _number(recovery.get("enqueue_p95_ms"), "recovery enqueue p95")
        > _number(slo.get("worker_enqueue_p95_ms_max"), "worker enqueue limit")
        or _number(recovery.get("completion_seconds"), "recovery completion")
        > _number(slo.get("worker_recovery_seconds_max"), "recovery completion limit")
        or _integer(recovery.get("max_attempts"), "recovery max attempts")
        < _integer(slo.get("worker_recovery_attempts_min"), "recovery attempts minimum")
    )
    if recovery_failed:
        _add_alert(
            alerts,
            catalog,
            "worker_recovery_breach",
            "Worker recovery evidence breached",
        )

    if summary["business_memory_peak_bytes"] > _number(
        budgets.get("business_node_memory_bytes_max"), "business memory budget"
    ) or summary["business_cpu_peak_cores"] > _number(
        budgets.get("business_node_cpu_cores_max"), "business CPU budget"
    ):
        _add_alert(
            alerts,
            catalog,
            "business_resource_pressure",
            "business node observed resource budget exceeded",
        )
    if summary["ragflow_memory_peak_bytes"] > _number(
        budgets.get("ragflow_node_memory_bytes_max"), "RAGFlow memory budget"
    ) or summary["ragflow_cpu_peak_cores"] > _number(
        budgets.get("ragflow_node_cpu_cores_max"), "RAGFlow CPU budget"
    ):
        _add_alert(
            alerts,
            catalog,
            "ragflow_resource_pressure",
            "RAGFlow node observed resource budget exceeded",
        )
    if summary["container_restart_or_oom"]:
        failure_details = summary["container_restart_or_oom_details"]
        if not isinstance(failure_details, list):
            raise SloGateFailure("container restart/OOM details are invalid")
        _add_alert(
            alerts,
            catalog,
            "container_restart_or_oom",
            ", ".join(str(item) for item in failure_details),
        )

    if require_backup:
        backup = _object(evidence.get("backup"), "evidence.backup")
        backup_age = _number(backup.get("age_hours"), "backup age")
        drill_age = _number(backup.get("restore_drill_age_days"), "restore drill age")
        if backup_age > _number(slo.get("backup_age_hours_max"), "backup age limit"):
            _add_alert(
                alerts,
                catalog,
                "backup_rpo_breach",
                f"backup_age_hours={backup_age:.2f}",
            )
        if drill_age > _number(slo.get("restore_drill_age_days_max"), "restore drill age limit"):
            _add_alert(
                alerts,
                catalog,
                "restore_drill_stale",
                f"restore_drill_age_days={drill_age:.2f}",
            )

    summary.update(
        {
            "api_requests_total": requests_total,
            "api_failure_rate": failure_rate,
            "api_p95_ms": api_p95,
            "api_p99_ms": api_p99,
        }
    )
    return {
        "schema_version": 1,
        "scope": "complete" if require_backup else "runtime",
        "backup_status": "evaluated" if require_backup else "not_evaluated",
        "status": "passed" if not alerts else "failed",
        "summary": summary,
        "alerts": alerts,
    }


def write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise SloGateFailure("output must not be a symbolic link")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def main(arguments: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if arguments is None else arguments)
    runtime_only = False
    if args and args[0] == "--runtime-only":
        runtime_only = True
        args = args[1:]
    if len(args) != 3:
        print(
            "usage: slo_gate.py [--runtime-only] POLICY EVIDENCE OUTPUT",
            file=sys.stderr,
        )
        return 2
    try:
        policy = load_policy(Path(args[0]))
        evidence = _read_json(Path(args[1]), "evidence")
        result = evaluate(policy, evidence, require_backup=not runtime_only)
        write_private_json(Path(args[2]), result)
    except (OSError, SloGateFailure) as error:
        print(f"SLO gate failed: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
