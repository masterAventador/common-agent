#!/usr/bin/env python3
"""Exercise concurrent writes, durable Worker capacity, and crash recovery."""

from __future__ import annotations

import concurrent.futures
import http.client
import json
import math
import os
import re
import socket
import ssl
import sys
import tempfile
import time
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID, uuid4


class WorkerLoadFailure(RuntimeError):
    """Raised when the production Worker load contract is not met."""


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _bounded_integer(
    environment: Mapping[str, str],
    name: str,
    *,
    minimum: int,
    maximum: int,
    label: str,
) -> int:
    raw = _required(environment, name)
    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{label} must be an integer") from error
    if value < minimum or value > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class WorkerLoadSettings:
    base_url: str
    public_host: str
    email: str
    password: str
    ca_file: Path
    state_file: Path
    capacity_tasks: int
    recovery_tasks: int
    write_concurrency: int
    enqueue_p95_limit_ms: int
    drain_timeout_seconds: int
    recovery_timeout_seconds: int

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> WorkerLoadSettings:
        base_url = _required(environment, "COMMON_AGENT_PERFORMANCE_BASE_URL").rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme != "https":
            raise ValueError("COMMON_AGENT_PERFORMANCE_BASE_URL must use HTTPS")
        if (
            parsed.hostname is None
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or parsed.path not in {"", "/"}
        ):
            raise ValueError("COMMON_AGENT_PERFORMANCE_BASE_URL must be an HTTPS origin")
        public_host = _required(environment, "COMMON_AGENT_PERFORMANCE_HOST")
        if not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?", public_host):
            raise ValueError("COMMON_AGENT_PERFORMANCE_HOST must be a valid hostname")
        ca_file = Path(_required(environment, "COMMON_AGENT_PERFORMANCE_CA_FILE")).expanduser()
        if not ca_file.is_file():
            raise ValueError("COMMON_AGENT_PERFORMANCE_CA_FILE must be a readable file")
        state_file = Path(_required(environment, "COMMON_AGENT_WORKER_LOAD_STATE")).expanduser()
        if not state_file.is_absolute():
            state_file = Path.cwd() / state_file
        return cls(
            base_url=base_url,
            public_host=public_host,
            email=_required(environment, "COMMON_AGENT_PERFORMANCE_EMAIL"),
            password=_required(environment, "COMMON_AGENT_PERFORMANCE_PASSWORD"),
            ca_file=ca_file,
            state_file=state_file,
            capacity_tasks=_bounded_integer(
                environment,
                "COMMON_AGENT_WORKER_CAPACITY_TASKS",
                minimum=1,
                maximum=128,
                label="capacity tasks",
            ),
            recovery_tasks=_bounded_integer(
                environment,
                "COMMON_AGENT_WORKER_RECOVERY_TASKS",
                minimum=1,
                maximum=32,
                label="recovery tasks",
            ),
            write_concurrency=_bounded_integer(
                environment,
                "COMMON_AGENT_WORKER_WRITE_CONCURRENCY",
                minimum=1,
                maximum=64,
                label="write concurrency",
            ),
            enqueue_p95_limit_ms=_bounded_integer(
                environment,
                "COMMON_AGENT_WORKER_ENQUEUE_P95_MS",
                minimum=1,
                maximum=10_000,
                label="enqueue p95",
            ),
            drain_timeout_seconds=_bounded_integer(
                environment,
                "COMMON_AGENT_WORKER_DRAIN_TIMEOUT_SECONDS",
                minimum=30,
                maximum=600,
                label="drain timeout",
            ),
            recovery_timeout_seconds=_bounded_integer(
                environment,
                "COMMON_AGENT_WORKER_RECOVERY_TIMEOUT_SECONDS",
                minimum=60,
                maximum=900,
                label="recovery timeout",
            ),
        )

    @property
    def connect_host(self) -> str:
        hostname = urlsplit(self.base_url).hostname
        if hostname is None:  # Guarded by from_environment.
            raise ValueError("base URL has no hostname")
        return hostname

    @property
    def port(self) -> int:
        return urlsplit(self.base_url).port or 443

    @property
    def public_origin(self) -> str:
        suffix = "" if self.port == 443 else f":{self.port}"
        return f"https://{self.public_host}{suffix}"

    def ssl_context(self) -> ssl.SSLContext:
        return ssl.create_default_context(cafile=str(self.ca_file))


@dataclass(frozen=True, slots=True)
class WorkerLoadResult:
    requested_tasks: int
    accepted_tasks: int
    completed_tasks: int
    failed_tasks: int
    enqueue_p95_ms: float
    completion_seconds: float


class _ResolvedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, settings: WorkerLoadSettings, *, timeout: float = 30) -> None:
        tls_context = settings.ssl_context()
        super().__init__(
            settings.public_host,
            settings.port,
            timeout=timeout,
            context=tls_context,
        )
        self._connect_host = settings.connect_host
        self._tls_context = tls_context

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._connect_host, self.port),
            self.timeout,
        )
        self.sock = self._tls_context.wrap_socket(raw_socket, server_hostname=self.host)


def _nearest_rank_percentile(samples: Sequence[float], percentile: int) -> float:
    if not samples:
        raise ValueError("samples must not be empty")
    ordered = sorted(samples)
    return float(ordered[math.ceil((percentile / 100) * len(ordered)) - 1])


def _extract_session_cookie(set_cookie_headers: Sequence[str]) -> str:
    cookie_name = "__Host-common-agent-session"
    for header in set_cookie_headers:
        first_part = header.split(";", 1)[0].strip()
        name, separator, value = first_part.partition("=")
        if name == cookie_name and separator and value:
            return first_part
    raise WorkerLoadFailure("login did not return the production session cookie")


def _request_headers(
    settings: WorkerLoadSettings,
    method: str,
    *,
    session_cookie: str | None,
    csrf_token: str | None,
    tenant_id: str | None,
    has_body: bool,
) -> dict[str, str]:
    headers = {"Accept": "application/json", "Host": settings.public_host}
    if session_cookie:
        headers["Cookie"] = session_cookie
    if tenant_id:
        headers["X-Tenant-ID"] = tenant_id
    if method.upper() not in {"GET", "HEAD", "OPTIONS"}:
        headers["Origin"] = settings.public_origin
        if csrf_token:
            headers["X-CSRF-Token"] = csrf_token
    if has_body:
        headers["Content-Type"] = "application/json"
    return headers


def _json_request(
    settings: WorkerLoadSettings,
    method: str,
    path: str,
    *,
    session_cookie: str | None = None,
    csrf_token: str | None = None,
    tenant_id: str | None = None,
    body: Mapping[str, Any] | None = None,
    expected_status: int | frozenset[int] = 200,
) -> tuple[Any, list[str]]:
    payload = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None
    connection = _ResolvedHTTPSConnection(settings)
    try:
        connection.request(
            method,
            path,
            body=payload,
            headers=_request_headers(
                settings,
                method,
                session_cookie=session_cookie,
                csrf_token=csrf_token,
                tenant_id=tenant_id,
                has_body=body is not None,
            ),
        )
        response = connection.getresponse()
        raw_body = response.read()
        allowed = (
            expected_status
            if isinstance(expected_status, frozenset)
            else frozenset({expected_status})
        )
        if response.status not in allowed:
            preview = raw_body.decode("utf-8", errors="replace")[:300]
            raise WorkerLoadFailure(
                f"{method} {path} returned {response.status}, expected {sorted(allowed)}: {preview}"
            )
        set_cookie_headers = [
            value for name, value in response.getheaders() if name.lower() == "set-cookie"
        ]
        if not raw_body:
            return None, set_cookie_headers
        try:
            return json.loads(raw_body), set_cookie_headers
        except json.JSONDecodeError as error:
            raise WorkerLoadFailure(f"{method} {path} returned invalid JSON") from error
    finally:
        connection.close()


def save_state(path: Path, state: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise WorkerLoadFailure("Worker load state must not be a symbolic link")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(state, stream, separators=(",", ":"), sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _load_state(path: Path) -> dict[str, Any]:
    if path.is_symlink():
        raise WorkerLoadFailure("Worker load state must not be a symbolic link")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise WorkerLoadFailure("Worker load state is unavailable or invalid") from error
    if not isinstance(raw, dict) or not isinstance(raw.get("phases"), dict):
        raise WorkerLoadFailure("Worker load state has an invalid shape")
    return raw


def _phase_name(value: str) -> str:
    if value not in {"capacity", "recovery"}:
        raise WorkerLoadFailure("phase must be capacity or recovery")
    return value


def _phase(state: Mapping[str, Any], phase_name: str) -> dict[str, Any]:
    phases = state.get("phases")
    phase = phases.get(_phase_name(phase_name)) if isinstance(phases, dict) else None
    if not isinstance(phase, dict):
        raise WorkerLoadFailure(f"{phase_name} phase has not been submitted")
    return phase


def aggregate_ids(phase: Mapping[str, Any]) -> str:
    records = phase.get("records")
    if not isinstance(records, list) or not records:
        raise WorkerLoadFailure("phase has no conversation ids")
    values: list[str] = []
    for record in records:
        value = record.get("conversation_id") if isinstance(record, dict) else None
        try:
            normalized = str(UUID(value)) if isinstance(value, str) else ""
        except ValueError as error:
            raise WorkerLoadFailure("phase contains an invalid conversation id") from error
        if normalized != value:
            raise WorkerLoadFailure("phase contains an invalid conversation id")
        values.append(f"'{value}'")
    return ",".join(values)


def ensure_success(
    result: WorkerLoadResult,
    *,
    enqueue_p95_limit_ms: int,
    completion_limit_seconds: int,
) -> None:
    if result.accepted_tasks != result.requested_tasks:
        raise WorkerLoadFailure(
            f"Worker writes were partial: {result.accepted_tasks}/{result.requested_tasks} accepted"
        )
    if result.completed_tasks != result.requested_tasks or result.failed_tasks:
        raise WorkerLoadFailure(
            "Worker tasks did not all complete: "
            f"completed={result.completed_tasks}, failed={result.failed_tasks}"
        )
    if result.enqueue_p95_ms > enqueue_p95_limit_ms:
        raise WorkerLoadFailure(
            f"concurrent write p95 was {result.enqueue_p95_ms:.2f}ms, "
            f"limit is {enqueue_p95_limit_ms}ms"
        )
    if result.completion_seconds > completion_limit_seconds:
        raise WorkerLoadFailure(
            f"Worker drain took {result.completion_seconds:.2f}s, "
            f"limit is {completion_limit_seconds}s"
        )


def terminal_outcome(record: Mapping[str, Any], messages: Any) -> str | None:
    if not isinstance(messages, list) or len(messages) != 2:
        raise WorkerLoadFailure("conversation returned an invalid message set")
    user_id = record.get("user_message_id")
    assistant_id = record.get("assistant_message_id")
    user = next(
        (item for item in messages if isinstance(item, dict) and item.get("id") == user_id),
        None,
    )
    assistant = next(
        (item for item in messages if isinstance(item, dict) and item.get("id") == assistant_id),
        None,
    )
    if (
        not isinstance(user, dict)
        or user.get("role") != "user"
        or user.get("status") != "completed"
        or not isinstance(assistant, dict)
        or assistant.get("role") != "assistant"
    ):
        raise WorkerLoadFailure("conversation returned an invalid message set")
    status = assistant.get("status")
    if status in {"pending", "streaming"}:
        return None
    if status == "completed" and isinstance(assistant.get("content"), str):
        if assistant["content"].strip():
            return "completed"
        raise WorkerLoadFailure("completed Worker reply was empty")
    error_code = assistant.get("error_code")
    raise WorkerLoadFailure(
        f"Worker reply entered {status or 'unknown'} state: {error_code or 'no error code'}"
    )


def _authenticate(settings: WorkerLoadSettings) -> dict[str, str]:
    login, set_cookie_headers = _json_request(
        settings,
        "POST",
        "/api/v1/auth/login",
        body={"email": settings.email, "password": settings.password},
    )
    csrf_token = login.get("csrf_token") if isinstance(login, dict) else None
    if not isinstance(csrf_token, str):
        raise WorkerLoadFailure("login did not return a CSRF token")
    session_cookie = _extract_session_cookie(set_cookie_headers)
    tenants, _ = _json_request(
        settings,
        "GET",
        "/api/v1/tenants",
        session_cookie=session_cookie,
    )
    if not isinstance(tenants, list):
        raise WorkerLoadFailure("tenant list returned an invalid response")
    for access in tenants:
        tenant_id = access.get("id") if isinstance(access, dict) else None
        if not isinstance(tenant_id, str):
            continue
        models, _ = _json_request(
            settings,
            "GET",
            "/api/v1/model-configurations?enabled_only=true&limit=1",
            session_cookie=session_cookie,
            tenant_id=tenant_id,
        )
        items = models.get("items") if isinstance(models, dict) else None
        model_id = (
            items[0].get("id")
            if isinstance(items, list) and items and isinstance(items[0], dict)
            else None
        )
        if isinstance(model_id, str):
            return {
                "session_cookie": session_cookie,
                "csrf_token": csrf_token,
                "tenant_id": tenant_id,
                "model_id": model_id,
            }
    raise WorkerLoadFailure("no accessible tenant has an enabled configuration")


def _planned_records(phase_name: str, count: int) -> list[dict[str, str]]:
    suffix = uuid4().hex[:12]
    return [
        {
            "conversation_id": str(uuid4()),
            "user_message_id": str(uuid4()),
            "assistant_message_id": "",
            "turn_id": "",
            "content": (
                f"生产 Worker 容量探针 {suffix}-{index}, 只回复 OK-{suffix}-{index}。"
                if phase_name == "capacity"
                else (
                    f"生产 Worker 崩溃接管探针 {suffix}-{index}。"
                    "请用至少三百个汉字说明持久任务租约、心跳、随机栅栏和崩溃接管为什么能避免"
                    "任务丢失, 并在结尾写 RECOVERED。"
                )
            ),
        }
        for index in range(count)
    ]


def _submit_one(
    settings: WorkerLoadSettings,
    authentication: Mapping[str, str],
    record: dict[str, str],
) -> tuple[dict[str, str], float]:
    started_at = time.monotonic()
    accepted, _ = _json_request(
        settings,
        "POST",
        "/api/v1/conversation-turns",
        session_cookie=authentication["session_cookie"],
        csrf_token=authentication["csrf_token"],
        tenant_id=authentication["tenant_id"],
        body={
            "conversation_id": record["conversation_id"],
            "message_id": record["user_message_id"],
            "employee_id": None,
            "model_configuration_id": authentication["model_id"],
            "content": record["content"],
        },
        expected_status=202,
    )
    latency_ms = (time.monotonic() - started_at) * 1000
    conversation = accepted.get("conversation") if isinstance(accepted, dict) else None
    turn = accepted.get("turn") if isinstance(accepted, dict) else None
    assistant = turn.get("assistant_message") if isinstance(turn, dict) else None
    if (
        not isinstance(conversation, dict)
        or conversation.get("id") != record["conversation_id"]
        or not isinstance(turn, dict)
        or not isinstance(turn.get("turn_id"), str)
        or not isinstance(assistant, dict)
        or not isinstance(assistant.get("id"), str)
        or assistant.get("status") != "pending"
    ):
        raise WorkerLoadFailure("conversation turn returned an invalid accepted response")
    return (
        record
        | {
            "assistant_message_id": assistant["id"],
            "turn_id": turn["turn_id"],
        },
        latency_ms,
    )


def submit_phase(settings: WorkerLoadSettings, phase_name: str) -> None:
    phase_name = _phase_name(phase_name)
    authentication = _authenticate(settings)
    count = settings.capacity_tasks if phase_name == "capacity" else settings.recovery_tasks
    records = _planned_records(phase_name, count)
    state: dict[str, Any] = (
        _load_state(settings.state_file) if settings.state_file.exists() else {"phases": {}}
    )
    state.update(authentication)
    phases = state["phases"]
    if not isinstance(phases, dict):
        raise WorkerLoadFailure("Worker load state has an invalid phase map")
    phases[phase_name] = {
        "requested_tasks": count,
        "accepted_tasks": 0,
        "enqueue_p95_ms": 0.0,
        "submitted_at_epoch": time.time(),
        "records": records,
    }
    save_state(settings.state_file, state)

    submitted: list[tuple[dict[str, str], float]] = []
    with concurrent.futures.ThreadPoolExecutor(
        max_workers=min(settings.write_concurrency, count)
    ) as executor:
        futures = [
            executor.submit(_submit_one, settings, authentication, record) for record in records
        ]
        try:
            for future in concurrent.futures.as_completed(futures):
                submitted.append(future.result())
        finally:
            completed_by_id = {
                record["conversation_id"]: (record, latency) for record, latency in submitted
            }
            ordered = [
                completed_by_id.get(record["conversation_id"], (record, 0.0)) for record in records
            ]
            accepted_records = [record for record, latency in ordered if latency > 0]
            latencies = [latency for _, latency in ordered if latency > 0]
            phase = phases[phase_name]
            phase["records"] = accepted_records + [
                record for record, latency in ordered if latency == 0
            ]
            phase["accepted_tasks"] = len(accepted_records)
            phase["enqueue_p95_ms"] = _nearest_rank_percentile(latencies, 95) if latencies else 0.0
            save_state(settings.state_file, state)

    phase = phases[phase_name]
    if phase["accepted_tasks"] != count:
        raise WorkerLoadFailure(
            f"Worker writes were partial: {phase['accepted_tasks']}/{count} accepted"
        )
    enqueue_p95 = float(phase["enqueue_p95_ms"])
    if enqueue_p95 > settings.enqueue_p95_limit_ms:
        raise WorkerLoadFailure(
            f"concurrent write p95 was {enqueue_p95:.2f}ms, "
            f"limit is {settings.enqueue_p95_limit_ms}ms"
        )
    print(
        json.dumps(
            {
                "accepted_tasks": count,
                "enqueue_p95_ms": enqueue_p95,
                "phase": phase_name,
                "requested_tasks": count,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )


def await_phase(settings: WorkerLoadSettings, phase_name: str) -> None:
    phase_name = _phase_name(phase_name)
    state = _load_state(settings.state_file)
    phase = _phase(state, phase_name)
    records = phase.get("records")
    if not isinstance(records, list) or not records:
        raise WorkerLoadFailure("phase has no submitted records")
    authentication = {
        name: state.get(name) for name in ("session_cookie", "csrf_token", "tenant_id", "model_id")
    }
    if any(not isinstance(value, str) or not value for value in authentication.values()):
        raise WorkerLoadFailure("Worker load authentication state is invalid")
    completion_limit = (
        settings.drain_timeout_seconds
        if phase_name == "capacity"
        else settings.recovery_timeout_seconds
    )
    deadline = time.monotonic() + completion_limit
    pending = {
        record["conversation_id"]: record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("conversation_id"), str)
    }
    while pending and time.monotonic() < deadline:
        with concurrent.futures.ThreadPoolExecutor(
            max_workers=min(settings.write_concurrency, len(pending))
        ) as executor:
            futures = {
                executor.submit(
                    _json_request,
                    settings,
                    "GET",
                    f"/api/v1/conversations/{conversation_id}/messages",
                    session_cookie=authentication["session_cookie"],
                    tenant_id=authentication["tenant_id"],
                ): conversation_id
                for conversation_id in pending
            }
            for future in concurrent.futures.as_completed(futures):
                conversation_id = futures[future]
                messages, _ = future.result()
                outcome = terminal_outcome(pending[conversation_id], messages)
                if outcome == "completed":
                    del pending[conversation_id]
        if pending:
            time.sleep(0.5)
    completion_seconds = time.time() - float(phase["submitted_at_epoch"])
    result = WorkerLoadResult(
        requested_tasks=int(phase["requested_tasks"]),
        accepted_tasks=int(phase["accepted_tasks"]),
        completed_tasks=len(records) - len(pending),
        failed_tasks=0,
        enqueue_p95_ms=float(phase["enqueue_p95_ms"]),
        completion_seconds=completion_seconds,
    )
    ensure_success(
        result,
        enqueue_p95_limit_ms=settings.enqueue_p95_limit_ms,
        completion_limit_seconds=completion_limit,
    )
    phase["result"] = asdict(result)
    save_state(settings.state_file, state)
    print(json.dumps(asdict(result), separators=(",", ":"), sort_keys=True))


def cleanup_phase(settings: WorkerLoadSettings, phase_name: str) -> None:
    state = _load_state(settings.state_file)
    phase = _phase(state, phase_name)
    records = phase.get("records")
    if not isinstance(records, list):
        raise WorkerLoadFailure("phase has no submitted records")
    for record in records:
        conversation_id = record.get("conversation_id") if isinstance(record, dict) else None
        if not isinstance(conversation_id, str):
            continue
        _json_request(
            settings,
            "DELETE",
            f"/api/v1/conversations/{conversation_id}",
            session_cookie=state.get("session_cookie"),
            csrf_token=state.get("csrf_token"),
            tenant_id=state.get("tenant_id"),
            expected_status=frozenset({204, 404}),
        )
    print(json.dumps({"cleaned_conversations": len(records), "phase": phase_name}))


def main(arguments: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if arguments is None else arguments)
    if len(args) != 2 or args[0] not in {
        "submit",
        "await",
        "cleanup",
        "aggregate-ids",
    }:
        print(
            "usage: worker_load_test.py {submit|await|cleanup|aggregate-ids} {capacity|recovery}",
            file=sys.stderr,
        )
        return 2
    try:
        settings = WorkerLoadSettings.from_environment(os.environ)
        phase_name = _phase_name(args[1])
        if args[0] == "submit":
            submit_phase(settings, phase_name)
        elif args[0] == "await":
            await_phase(settings, phase_name)
        elif args[0] == "cleanup":
            cleanup_phase(settings, phase_name)
        else:
            print(aggregate_ids(_phase(_load_state(settings.state_file), phase_name)))
    except (OSError, ValueError, WorkerLoadFailure) as error:
        print(f"Worker load test failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
