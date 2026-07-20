#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

KIB = 1024
MIB = 1024 * KIB
GIB = 1024 * MIB
MAX_VM_USED_BYTES = 25 * GIB
MAX_SWAP_USED_BYTES = 512 * MIB
MAX_FINAL_SWAP_GROWTH_BYTES = 64 * MIB
MIN_VM_TOTAL_BYTES = 24 * GIB
MAX_VM_TOTAL_BYTES = 32 * GIB
MIN_SOAK_SECONDS = 1800
PROFILE = "common-agent-dev"
DOCKER_CONTEXT = "colima-common-agent-dev"
CONTAINERS = (
    "common-agent-platform-mysql",
    "common-agent-ragflow-api",
    "common-agent-ragflow-elasticsearch",
    "common-agent-ragflow-mysql",
    "common-agent-ragflow-minio",
    "common-agent-ragflow-valkey",
)
DEFAULT_HEALTH_URL = "http://127.0.0.1:18200/api/v1/system/status"


def main() -> int:
    parser = argparse.ArgumentParser(description="common-agent 32 GiB real 资源监视器")
    parser.add_argument("mode", nargs="?", choices=("cold-start", "soak"))
    parser.add_argument("--duration-seconds", type=int)
    parser.add_argument("--interval-seconds", type=float)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        print("real 资源监视器解析与阈值自测通过")
        return 0
    if args.mode is None or args.output is None:
        parser.error("mode 与 --output 必填")

    duration = args.duration_seconds
    if duration is None:
        duration = 600 if args.mode == "cold-start" else MIN_SOAK_SECONDS
    if duration <= 0:
        parser.error("监视时长必须为正整数")
    if args.mode == "soak" and duration < MIN_SOAK_SECONDS:
        parser.error(f"正式 real soak 至少 {MIN_SOAK_SECONDS} 秒")
    interval = args.interval_seconds
    if interval is None:
        interval = 1.0 if args.mode == "cold-start" else 10.0
    if interval <= 0:
        parser.error("采样间隔必须大于 0")

    report = _monitor(
        mode=args.mode,
        duration_seconds=duration,
        interval_seconds=interval,
        health_url=args.health_url,
        output=args.output,
    )
    _print_summary(report)
    return 0


def _monitor(
    *,
    mode: str,
    duration_seconds: int,
    interval_seconds: float,
    health_url: str,
    output: Path,
) -> dict[str, Any]:
    started = time.monotonic()
    next_sample_at = started
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    ready_samples = 0
    output.parent.mkdir(parents=True, exist_ok=True)

    while True:
        elapsed = time.monotonic() - started
        if elapsed > duration_seconds:
            break
        try:
            sample = _sample(health_url)
            sample["elapsed_seconds"] = round(elapsed, 3)
            samples.append(sample)
            ready_samples = ready_samples + 1 if sample["system_ready"] else 0
            if mode == "cold-start" and ready_samples >= 2:
                break
        except (OSError, RuntimeError, subprocess.SubprocessError) as error:
            errors.append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": f"{elapsed:.3f}",
                    "type": type(error).__name__,
                }
            )
            if mode == "soak":
                break
        _write_report(
            output,
            _build_report(mode, duration_seconds, interval_seconds, samples, errors),
        )
        next_sample_at += interval_seconds
        now = time.monotonic()
        remaining = duration_seconds - (now - started)
        if remaining <= 0:
            break
        sleep_seconds = min(max(0.0, next_sample_at - now), remaining)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    report = _build_report(mode, duration_seconds, interval_seconds, samples, errors)
    _validate_report(report)
    report["status"] = "passed"
    _write_report(output, report)
    return report


def _sample(health_url: str) -> dict[str, Any]:
    memory = _read_vm_memory()
    containers = _read_containers()
    return {
        "at": datetime.now(UTC).isoformat(),
        **memory,
        "container_used_bytes": sum(item["memory_bytes"] for item in containers.values()),
        "containers": containers,
        "system_ready": _system_ready(health_url),
    }


def _read_vm_memory() -> dict[str, int]:
    payload = _run(
        "colima",
        "ssh",
        "--profile",
        PROFILE,
        "--",
        "cat",
        "/proc/meminfo",
    )
    values: dict[str, int] = {}
    for line in payload.splitlines():
        name, separator, remainder = line.partition(":")
        if not separator or name not in {
            "MemTotal",
            "MemAvailable",
            "SwapTotal",
            "SwapFree",
        }:
            continue
        values[name] = int(remainder.strip().split()[0]) * KIB
    required = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree"}
    if values.keys() < required:
        raise RuntimeError("Colima meminfo 不完整")
    return {
        "vm_total_bytes": values["MemTotal"],
        "vm_available_bytes": values["MemAvailable"],
        "vm_used_bytes": values["MemTotal"] - values["MemAvailable"],
        "swap_total_bytes": values["SwapTotal"],
        "swap_used_bytes": values["SwapTotal"] - values["SwapFree"],
    }


def _read_containers() -> dict[str, dict[str, Any]]:
    stats_payload = _run(
        "docker",
        "--context",
        DOCKER_CONTEXT,
        "stats",
        "--no-stream",
        "--format",
        "{{.Name}}\t{{.MemUsage}}",
        *CONTAINERS,
    )
    memory_by_name: dict[str, int] = {}
    for line in stats_payload.splitlines():
        name, separator, usage = line.partition("\t")
        if separator:
            memory_by_name[name] = _parse_size(usage.partition("/")[0].strip())

    inspect_payload = _run(
        "docker",
        "--context",
        DOCKER_CONTEXT,
        "inspect",
        "--format",
        (
            "{{.Name}}\t{{.RestartCount}}\t{{.State.OOMKilled}}\t{{.State.Status}}\t"
            "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}"
        ),
        *CONTAINERS,
    )
    containers: dict[str, dict[str, Any]] = {}
    for line in inspect_payload.splitlines():
        fields = line.split("\t")
        if len(fields) != 5:
            raise RuntimeError("Docker inspect 输出格式无效")
        name = fields[0].removeprefix("/")
        if name not in memory_by_name:
            raise RuntimeError(f"Docker stats 缺少容器 {name}")
        containers[name] = {
            "memory_bytes": memory_by_name[name],
            "restart_count": int(fields[1]),
            "oom_killed": fields[2].lower() == "true",
            "status": fields[3],
            "health": fields[4],
        }
    if set(containers) != set(CONTAINERS):
        raise RuntimeError("real 容器集合不完整")
    return containers


def _system_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError):
        return False
    return bool(
        payload.get("integration_mode") == "real"
        and payload.get("model", {}).get("status") == "configured"
        and payload.get("knowledge", {}).get("availability") == "available"
    )


def _run(*command: str) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def _parse_size(value: str) -> int:
    normalized = value.strip()
    units = {
        "KiB": KIB,
        "MiB": MIB,
        "GiB": GIB,
        "KB": 1000,
        "MB": 1000**2,
        "GB": 1000**3,
        "B": 1,
    }
    for suffix in sorted(units, key=len, reverse=True):
        if normalized.endswith(suffix):
            number = normalized[: -len(suffix)].strip()
            return round(float(number) * units[suffix])
    raise RuntimeError(f"无法解析内存值: {normalized}")


def _build_report(
    mode: str,
    duration_seconds: int,
    interval_seconds: float,
    samples: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "mode": mode,
        "configured_duration_seconds": duration_seconds,
        "interval_seconds": interval_seconds,
        "thresholds": {
            "max_vm_used_bytes": MAX_VM_USED_BYTES,
            "max_swap_used_bytes": MAX_SWAP_USED_BYTES,
            "max_final_swap_growth_bytes": MAX_FINAL_SWAP_GROWTH_BYTES,
        },
        "samples": samples,
        "sampling_errors": errors,
        "status": "running",
    }


def _validate_report(report: dict[str, Any]) -> None:
    samples = report["samples"]
    if not samples:
        raise RuntimeError("没有取得 real 资源样本")
    if report["sampling_errors"] and report["mode"] == "soak":
        raise RuntimeError("30 分钟 soak 出现资源采样失败")
    if report["mode"] == "cold-start" and not samples[-1]["system_ready"]:
        raise RuntimeError("real 冷启动未在期限内达到 ready")
    if report["mode"] == "soak" and any(not sample["system_ready"] for sample in samples):
        raise RuntimeError("30 分钟 soak 出现健康抖动")

    peak_vm = max(sample["vm_used_bytes"] for sample in samples)
    if peak_vm > MAX_VM_USED_BYTES:
        raise RuntimeError("real VM 峰值超过 25 GiB")
    peak_swap = max(sample["swap_used_bytes"] for sample in samples)
    if peak_swap > MAX_SWAP_USED_BYTES:
        raise RuntimeError("real VM Swap 使用超过 512 MiB")
    if samples[-1]["swap_used_bytes"] - samples[0]["swap_used_bytes"] > (
        MAX_FINAL_SWAP_GROWTH_BYTES
    ):
        raise RuntimeError("real VM Swap 持续增长超过 64 MiB")
    if any(
        not MIN_VM_TOTAL_BYTES <= sample["vm_total_bytes"] <= MAX_VM_TOTAL_BYTES
        for sample in samples
    ):
        raise RuntimeError("real VM 总内存不在 24-32 GiB 门禁内")
    if max(sample["container_used_bytes"] for sample in samples) > MAX_VM_USED_BYTES:
        raise RuntimeError("real 容器内存总和超过 25 GiB")
    if report["mode"] == "soak":
        minimum_elapsed = report["configured_duration_seconds"] - (report["interval_seconds"] * 1.5)
        minimum_samples = int(
            report["configured_duration_seconds"] / report["interval_seconds"] * 0.9
        )
        if samples[-1]["elapsed_seconds"] < minimum_elapsed or len(samples) < minimum_samples:
            raise RuntimeError("30 分钟 soak 采样时长或样本数不足")

    for sample in samples:
        for name, state in sample["containers"].items():
            if state["restart_count"] != 0:
                raise RuntimeError(f"容器发生重启: {name}")
            if state["oom_killed"]:
                raise RuntimeError(f"容器发生 OOM: {name}")
            require_ready_state = report["mode"] == "soak" or sample["system_ready"]
            if require_ready_state and (
                state["status"] != "running" or state["health"] not in {"healthy", "none"}
            ):
                raise RuntimeError(f"容器状态异常: {name}")


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _print_summary(report: dict[str, Any]) -> None:
    samples = report["samples"]
    peak_vm = max(sample["vm_used_bytes"] for sample in samples)
    peak_containers = max(sample["container_used_bytes"] for sample in samples)
    peak_swap = max(sample["swap_used_bytes"] for sample in samples)
    print(
        f"real {report['mode']} 资源门禁通过: samples={len(samples)}, "
        f"vm_peak={peak_vm / GIB:.2f} GiB, "
        f"containers_peak={peak_containers / GIB:.2f} GiB, "
        f"swap_peak={peak_swap / MIB:.2f} MiB"
    )


def _self_test() -> None:
    assert _parse_size("3.819GiB") == round(3.819 * GIB)
    assert _parse_size("410MiB") == 410 * MIB
    assert _parse_size("70.5MB") == 70_500_000
    meminfo = "MemTotal: 33554432 kB\nMemAvailable: 25165824 kB\n"
    assert "MemTotal" in meminfo and int(meminfo.split()[1]) * KIB == 32 * GIB


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as error:
        print(f"real 资源门禁失败: {error}", file=sys.stderr)
        raise SystemExit(1) from None
