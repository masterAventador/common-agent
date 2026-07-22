from __future__ import annotations

import importlib.util
import json
import stat
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[4] / "infra" / "production" / "resource_monitor.py"
SPEC = importlib.util.spec_from_file_location(
    "common_agent_production_resource_monitor", SCRIPT_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("无法加载生产资源监视器")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def test_docker_stats_and_inspect_are_merged_without_losing_restart_or_oom() -> None:
    stats = "\n".join(
        (
            json.dumps(
                {
                    "Name": "common-agent-production-api-blue",
                    "CPUPerc": "125.50%",
                    "MemUsage": "512MiB / 5GiB",
                }
            ),
            json.dumps(
                {
                    "Name": "common-agent-ragflow-api",
                    "CPUPerc": "25.00%",
                    "MemUsage": "4.25GiB / 5GiB",
                }
            ),
        )
    )
    inspect = json.dumps(
        [
            {
                "Name": "/common-agent-production-api-blue",
                "RestartCount": 0,
                "State": {"OOMKilled": False},
            },
            {
                "Name": "/common-agent-ragflow-api",
                "RestartCount": 2,
                "State": {"OOMKilled": True},
            },
        ]
    )

    states = MODULE.merge_container_states(stats, inspect)

    assert states["common-agent-production-api-blue"] == {
        "cpu_percent": 125.5,
        "memory_bytes": 512 * 1024**2,
        "oom_killed": False,
        "restart_count": 0,
    }
    assert states["common-agent-ragflow-api"] == {
        "cpu_percent": 25.0,
        "memory_bytes": round(4.25 * 1024**3),
        "oom_killed": True,
        "restart_count": 2,
    }


@pytest.mark.parametrize(
    ("value", "expected"),
    [("1B", 1), ("2KiB", 2 * 1024), ("3.5MiB", round(3.5 * 1024**2)), ("1GiB", 1024**3)],
)
def test_memory_units_are_parsed_exactly(value: str, expected: int) -> None:
    assert MODULE.parse_size(value) == expected


def test_unknown_or_mismatched_docker_output_is_rejected() -> None:
    with pytest.raises(MODULE.ResourceMonitorFailure, match="memory"):
        MODULE.parse_size("1 elephants")

    stats = json.dumps(
        {"Name": "common-agent-production-api-blue", "CPUPerc": "1%", "MemUsage": "1MiB / 5GiB"}
    )
    with pytest.raises(MODULE.ResourceMonitorFailure, match="inspect"):
        MODULE.merge_container_states(stats, "[]")


def test_report_is_private_and_rejects_symbolic_link(tmp_path: Path) -> None:
    output = tmp_path / "resources.json"
    report = MODULE.build_report(
        interval_seconds=5,
        samples=[{"elapsed_seconds": 0.0, "edge_healthy": True, "containers": {}}],
        errors=[],
    )

    MODULE.write_private_json(output, report)

    assert json.loads(output.read_text(encoding="utf-8"))["schema_version"] == 1
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    output.unlink()
    output.symlink_to(tmp_path / "target")
    with pytest.raises(MODULE.ResourceMonitorFailure, match="symbolic link"):
        MODULE.write_private_json(output, report)
