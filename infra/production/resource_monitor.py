#!/usr/bin/env python3
"""Sample formal production TLS health and Docker resource usage."""

from __future__ import annotations

import argparse
import http.client
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

KIB = 1024
MIB = 1024 * KIB
GIB = 1024 * MIB
_CONTAINER_NAME = re.compile(r"^common-agent-[a-z0-9-]+$")


class ResourceMonitorFailure(RuntimeError):
    """Raised when production resources cannot be sampled safely."""


def parse_size(value: str) -> int:
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
            try:
                number = float(normalized[: -len(suffix)].strip())
            except ValueError as error:
                raise ResourceMonitorFailure(f"invalid memory size: {value}") from error
            if number < 0 or number != number:
                raise ResourceMonitorFailure(f"invalid memory size: {value}")
            return round(number * units[suffix])
    raise ResourceMonitorFailure(f"invalid memory size: {value}")


def _parse_percent(value: object, label: str) -> float:
    if not isinstance(value, str) or not value.endswith("%"):
        raise ResourceMonitorFailure(f"invalid {label} percentage")
    try:
        result = float(value[:-1])
    except ValueError as error:
        raise ResourceMonitorFailure(f"invalid {label} percentage") from error
    if result < 0 or result != result:
        raise ResourceMonitorFailure(f"invalid {label} percentage")
    return result


def merge_container_states(stats_payload: str, inspect_payload: str) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, float | int]] = {}
    for raw_line in stats_payload.splitlines():
        if not raw_line.strip():
            continue
        try:
            row = json.loads(raw_line)
        except json.JSONDecodeError as error:
            raise ResourceMonitorFailure("invalid Docker stats JSON") from error
        if not isinstance(row, dict):
            raise ResourceMonitorFailure("invalid Docker stats row")
        name = row.get("Name")
        memory_usage = row.get("MemUsage")
        if (
            not isinstance(name, str)
            or not _CONTAINER_NAME.fullmatch(name)
            or not isinstance(memory_usage, str)
        ):
            raise ResourceMonitorFailure("invalid Docker stats container or memory")
        used, separator, _limit = memory_usage.partition("/")
        if not separator:
            raise ResourceMonitorFailure("invalid Docker stats memory usage")
        stats[name] = {
            "cpu_percent": _parse_percent(row.get("CPUPerc"), "CPU"),
            "memory_bytes": parse_size(used.strip()),
        }
    if not stats:
        raise ResourceMonitorFailure("Docker stats returned no containers")

    try:
        inspected = json.loads(inspect_payload)
    except json.JSONDecodeError as error:
        raise ResourceMonitorFailure("invalid Docker inspect JSON") from error
    if not isinstance(inspected, list):
        raise ResourceMonitorFailure("invalid Docker inspect result")
    states: dict[str, dict[str, Any]] = {}
    for raw in inspected:
        if not isinstance(raw, dict):
            raise ResourceMonitorFailure("invalid Docker inspect row")
        raw_name = raw.get("Name")
        name = raw_name.removeprefix("/") if isinstance(raw_name, str) else ""
        state = raw.get("State")
        restart_count = raw.get("RestartCount")
        if (
            name not in stats
            or isinstance(restart_count, bool)
            or not isinstance(restart_count, int)
            or restart_count < 0
            or not isinstance(state, dict)
            or not isinstance(state.get("OOMKilled"), bool)
        ):
            raise ResourceMonitorFailure("Docker inspect does not match stats")
        states[name] = stats[name] | {
            "restart_count": restart_count,
            "oom_killed": state["OOMKilled"],
        }
    if states.keys() != stats.keys():
        raise ResourceMonitorFailure("Docker inspect does not match stats")
    return dict(sorted(states.items()))


def build_report(
    *,
    interval_seconds: float,
    samples: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "configured_interval_seconds": interval_seconds,
        "sampling_errors": errors,
        "samples": samples,
    }


def write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise ResourceMonitorFailure("output must not be a symbolic link")
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


class _ResolvedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(
        self,
        *,
        connect_host: str,
        public_host: str,
        port: int,
        ca_file: Path,
    ) -> None:
        context = ssl.create_default_context(cafile=str(ca_file))
        super().__init__(public_host, port, timeout=5, context=context)
        self._connect_host = connect_host
        self._tls_context = context

    def connect(self) -> None:
        raw_socket = socket.create_connection((self._connect_host, self.port), self.timeout)
        self.sock = self._tls_context.wrap_socket(raw_socket, server_hostname=self.host)


def _edge_healthy(*, connect_host: str, public_host: str, port: int, ca_file: Path) -> bool:
    connection = _ResolvedHTTPSConnection(
        connect_host=connect_host,
        public_host=public_host,
        port=port,
        ca_file=ca_file,
    )
    try:
        connection.request(
            "GET",
            "/api/v1/system/health",
            headers={"Accept": "application/json", "Host": public_host},
        )
        response = connection.getresponse()
        payload = response.read()
        if response.status != 200:
            return False
        parsed = json.loads(payload)
        return bool(
            isinstance(parsed, dict)
            and parsed.get("status") == "ok"
            and parsed.get("integration_mode") == "real"
        )
    except (OSError, http.client.HTTPException, json.JSONDecodeError):
        return False
    finally:
        connection.close()


def _run(*command: str) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout


def _container_names(docker_context: str) -> list[str]:
    payload = _run(
        "docker",
        "--context",
        docker_context,
        "ps",
        "--format",
        "{{.Names}}",
    )
    names = sorted(
        name
        for name in payload.splitlines()
        if name.startswith("common-agent-production-") or name.startswith("common-agent-ragflow-")
    )
    required = {
        "common-agent-production-edge",
        "common-agent-production-platform-mysql",
        "common-agent-ragflow-api",
        "common-agent-ragflow-elasticsearch",
        "common-agent-ragflow-mysql",
        "common-agent-ragflow-minio",
        "common-agent-ragflow-valkey",
    }
    if not required.issubset(names):
        raise ResourceMonitorFailure("formal production or RAGFlow container set is incomplete")
    if not any(name.startswith("common-agent-production-api-") for name in names):
        raise ResourceMonitorFailure("formal production API container is missing")
    if not any(name.startswith("common-agent-production-web-") for name in names):
        raise ResourceMonitorFailure("formal production Web container is missing")
    return names


def _container_states(docker_context: str) -> dict[str, dict[str, Any]]:
    names = _container_names(docker_context)
    stats = _run(
        "docker",
        "--context",
        docker_context,
        "stats",
        "--no-stream",
        "--format",
        "{{json .}}",
        *names,
    )
    inspected = _run("docker", "--context", docker_context, "inspect", *names)
    return merge_container_states(stats, inspected)


def _origin(value: str) -> tuple[str, int]:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ResourceMonitorFailure("base URL must be a loopback HTTPS origin")
    try:
        return parsed.hostname, parsed.port or 443
    except ValueError as error:
        raise ResourceMonitorFailure("base URL port is invalid") from error


def monitor(
    *,
    docker_context: str,
    base_url: str,
    public_host: str,
    ca_file: Path,
    output: Path,
    stop_file: Path,
    interval_seconds: float,
    maximum_seconds: int,
) -> dict[str, Any]:
    if interval_seconds <= 0 or interval_seconds > 60:
        raise ResourceMonitorFailure("interval must be between 0 and 60 seconds")
    if maximum_seconds < 1 or maximum_seconds > 3600:
        raise ResourceMonitorFailure("maximum duration must be between 1 and 3600 seconds")
    if not ca_file.is_file() or ca_file.is_symlink():
        raise ResourceMonitorFailure("CA file must be a regular file")
    if stop_file.is_symlink():
        raise ResourceMonitorFailure("stop file must not be a symbolic link")
    connect_host, port = _origin(base_url)
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    while not stop_file.exists():
        elapsed = time.monotonic() - started
        if elapsed > maximum_seconds:
            errors.append({"type": "MonitorTimeout", "at": datetime.now(UTC).isoformat()})
            break
        try:
            samples.append(
                {
                    "at": datetime.now(UTC).isoformat(),
                    "elapsed_seconds": round(elapsed, 3),
                    "edge_healthy": _edge_healthy(
                        connect_host=connect_host,
                        public_host=public_host,
                        port=port,
                        ca_file=ca_file,
                    ),
                    "containers": _container_states(docker_context),
                }
            )
        except (OSError, ResourceMonitorFailure, subprocess.SubprocessError) as error:
            errors.append(
                {
                    "type": type(error).__name__,
                    "at": datetime.now(UTC).isoformat(),
                }
            )
        write_private_json(
            output,
            build_report(interval_seconds=interval_seconds, samples=samples, errors=errors),
        )
        time.sleep(interval_seconds)
    report = build_report(interval_seconds=interval_seconds, samples=samples, errors=errors)
    write_private_json(output, report)
    return report


def main(arguments: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="common-agent formal production resource monitor")
    parser.add_argument("--docker-context", required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--public-host", required=True)
    parser.add_argument("--ca-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--stop-file", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=float, default=5.0)
    parser.add_argument("--maximum-seconds", type=int, default=1200)
    args = parser.parse_args(sys.argv[1:] if arguments is None else list(arguments))
    try:
        report = monitor(
            docker_context=args.docker_context,
            base_url=args.base_url,
            public_host=args.public_host,
            ca_file=args.ca_file,
            output=args.output,
            stop_file=args.stop_file,
            interval_seconds=args.interval_seconds,
            maximum_seconds=args.maximum_seconds,
        )
    except (OSError, ResourceMonitorFailure) as error:
        print(f"resource monitor failed: {error}", file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "samples": len(report["samples"]),
                "sampling_errors": report["sampling_errors"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if report["samples"] and not report["sampling_errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
