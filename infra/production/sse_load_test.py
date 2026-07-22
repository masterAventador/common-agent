#!/usr/bin/env python3
"""Validate sustained SSE capacity through the formal TLS edge."""

from __future__ import annotations

import asyncio
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
from collections.abc import Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlsplit
from uuid import uuid4


class SseLoadFailure(RuntimeError):
    """Raised when the production SSE capacity contract is not met."""


def _required(environment: Mapping[str, str], name: str) -> str:
    value = environment.get(name, "").strip()
    if not value:
        raise ValueError(f"{name} is required")
    return value


def _bounded_integer(
    environment: Mapping[str, str],
    name: str,
    *,
    default: int | None,
    minimum: int,
    maximum: int,
    label: str,
) -> int:
    raw = environment.get(name, "").strip()
    if not raw:
        if default is None:
            raise ValueError(f"{name} is required")
        value = default
    else:
        try:
            value = int(raw)
        except ValueError as error:
            raise ValueError(f"{label} must be an integer") from error
    if value < minimum or value > maximum:
        raise ValueError(f"{label} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True, slots=True)
class SseLoadSettings:
    base_url: str
    public_host: str
    email: str
    password: str
    connections: int
    duration_seconds: int
    ramp_connections_per_second: int
    handshake_timeout_seconds: int
    handshake_p95_limit_ms: int
    ca_file: Path | None

    @classmethod
    def from_environment(cls, environment: Mapping[str, str]) -> SseLoadSettings:
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
        ca_value = environment.get("COMMON_AGENT_PERFORMANCE_CA_FILE", "").strip()
        ca_file = Path(ca_value).expanduser().resolve() if ca_value else None
        if ca_file is not None and not ca_file.is_file():
            raise ValueError("COMMON_AGENT_PERFORMANCE_CA_FILE must be a readable file")
        return cls(
            base_url=base_url,
            public_host=public_host,
            email=_required(environment, "COMMON_AGENT_PERFORMANCE_EMAIL"),
            password=_required(environment, "COMMON_AGENT_PERFORMANCE_PASSWORD"),
            connections=_bounded_integer(
                environment,
                "COMMON_AGENT_SSE_CONNECTIONS",
                default=None,
                minimum=1,
                maximum=1024,
                label="connections",
            ),
            duration_seconds=_bounded_integer(
                environment,
                "COMMON_AGENT_SSE_DURATION_SECONDS",
                default=None,
                minimum=10,
                maximum=900,
                label="duration",
            ),
            ramp_connections_per_second=_bounded_integer(
                environment,
                "COMMON_AGENT_SSE_RAMP_CONNECTIONS_PER_SECOND",
                default=16,
                minimum=1,
                maximum=128,
                label="ramp connections per second",
            ),
            handshake_timeout_seconds=_bounded_integer(
                environment,
                "COMMON_AGENT_SSE_HANDSHAKE_TIMEOUT_SECONDS",
                default=30,
                minimum=1,
                maximum=120,
                label="handshake timeout",
            ),
            handshake_p95_limit_ms=_bounded_integer(
                environment,
                "COMMON_AGENT_SSE_HANDSHAKE_P95_MS",
                default=None,
                minimum=1,
                maximum=10_000,
                label="handshake p95",
            ),
            ca_file=ca_file,
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
        return ssl.create_default_context(cafile=str(self.ca_file) if self.ca_file else None)


@dataclass(frozen=True, slots=True)
class SseLoadResult:
    requested_connections: int
    established_connections: int
    alive_at_deadline: int
    unexpected_disconnects: int
    handshake_p95_ms: float
    requests_in_flight: int


@dataclass(frozen=True, slots=True)
class _Fixture:
    session_cookie: str
    csrf_token: str
    tenant_id: str
    employee_id: str
    conversation_id: str


class _ResolvedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, settings: SseLoadSettings) -> None:
        tls_context = settings.ssl_context()
        super().__init__(
            settings.public_host,
            settings.port,
            timeout=settings.handshake_timeout_seconds,
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


def extract_session_cookie(set_cookie_headers: Sequence[str]) -> str:
    cookie_name = "__Host-common-agent-session"
    for header in set_cookie_headers:
        first_part = header.split(";", 1)[0].strip()
        name, separator, value = first_part.partition("=")
        if name == cookie_name and separator and value:
            return first_part
    raise SseLoadFailure("login did not return the production session cookie")


def nearest_rank_percentile(samples: Sequence[float], percentile: int) -> float:
    if not samples:
        raise ValueError("samples must not be empty")
    if percentile < 1 or percentile > 100:
        raise ValueError("percentile must be between 1 and 100")
    ordered = sorted(samples)
    rank = math.ceil((percentile / 100) * len(ordered))
    return float(ordered[rank - 1])


def resolve_tenant_model(
    accesses: Sequence[Mapping[str, Any]],
    model_lookup: Callable[[str], Any],
) -> tuple[str, str]:
    for access in accesses:
        tenant_id = access.get("id")
        if not isinstance(tenant_id, str):
            continue
        models = model_lookup(tenant_id)
        items = models.get("items") if isinstance(models, dict) else None
        if not isinstance(items, list) or not items:
            continue
        model_id = items[0].get("id") if isinstance(items[0], dict) else None
        if isinstance(model_id, str):
            return tenant_id, model_id
    raise SseLoadFailure("no accessible tenant has an enabled configuration")


def ensure_success(result: SseLoadResult, *, handshake_p95_limit_ms: int) -> None:
    if result.established_connections != result.requested_connections:
        raise SseLoadFailure(
            "SSE capacity was partial: "
            f"{result.established_connections}/{result.requested_connections} established"
        )
    if result.alive_at_deadline != result.requested_connections:
        raise SseLoadFailure(
            "SSE connections did not survive the deadline: "
            f"{result.alive_at_deadline}/{result.requested_connections} alive"
        )
    if result.unexpected_disconnects:
        raise SseLoadFailure(
            f"SSE unexpected_disconnects was {result.unexpected_disconnects}, expected 0"
        )
    if result.handshake_p95_ms > handshake_p95_limit_ms:
        raise SseLoadFailure(
            f"SSE handshake p95 was {result.handshake_p95_ms:.2f}ms, "
            f"limit is {handshake_p95_limit_ms}ms"
        )
    if result.requests_in_flight != 0:
        raise SseLoadFailure(
            f"requests_in_flight did not recover to 0: {result.requests_in_flight}"
        )


def request_headers(
    settings: SseLoadSettings,
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
    settings: SseLoadSettings,
    method: str,
    path: str,
    *,
    session_cookie: str | None = None,
    csrf_token: str | None = None,
    tenant_id: str | None = None,
    body: Mapping[str, Any] | None = None,
    expected_status: int = 200,
) -> tuple[Any, list[str]]:
    headers = request_headers(
        settings,
        method,
        session_cookie=session_cookie,
        csrf_token=csrf_token,
        tenant_id=tenant_id,
        has_body=body is not None,
    )
    payload: bytes | None = None
    if body is not None:
        payload = json.dumps(body, separators=(",", ":")).encode("utf-8")
    connection = _ResolvedHTTPSConnection(settings)
    try:
        connection.request(method, path, body=payload, headers=headers)
        response = connection.getresponse()
        raw_body = response.read()
        set_cookie_headers = [
            value for name, value in response.getheaders() if name.lower() == "set-cookie"
        ]
        if response.status != expected_status:
            preview = raw_body.decode("utf-8", errors="replace")[:300]
            raise SseLoadFailure(
                f"{method} {path} returned {response.status}, expected {expected_status}: {preview}"
            )
        if not raw_body:
            return None, set_cookie_headers
        try:
            return json.loads(raw_body), set_cookie_headers
        except json.JSONDecodeError as error:
            raise SseLoadFailure(f"{method} {path} returned invalid JSON") from error
    finally:
        connection.close()


def _create_fixture(settings: SseLoadSettings) -> _Fixture:
    login, set_cookie_headers = _json_request(
        settings,
        "POST",
        "/api/v1/auth/login",
        body={"email": settings.email, "password": settings.password},
    )
    if not isinstance(login, dict) or not isinstance(login.get("csrf_token"), str):
        raise SseLoadFailure("login did not return a CSRF token")
    session_cookie = extract_session_cookie(set_cookie_headers)
    tenants, _ = _json_request(
        settings,
        "GET",
        "/api/v1/tenants",
        session_cookie=session_cookie,
    )
    if not isinstance(tenants, list) or not tenants:
        raise SseLoadFailure("tenant list did not return an accessible tenant")

    def load_models(tenant_id: str) -> Any:
        models, _ = _json_request(
            settings,
            "GET",
            "/api/v1/model-configurations?enabled_only=true&limit=1",
            session_cookie=session_cookie,
            tenant_id=tenant_id,
        )
        return models

    tenant_id, model_id = resolve_tenant_model(tenants, load_models)

    unique_suffix = uuid4().hex[:12]
    employee, _ = _json_request(
        settings,
        "POST",
        "/api/v1/employees",
        session_cookie=session_cookie,
        csrf_token=login["csrf_token"],
        tenant_id=tenant_id,
        body={
            "name": f"S10-08 SSE {unique_suffix}",
            "description": "S10-08 production SSE capacity fixture",
            "system_prompt": "Answer briefly for the production SSE capacity fixture.",
            "default_model_configuration_id": model_id,
            "knowledge_base_id": None,
            "allowed_workflow_ids": [],
        },
        expected_status=201,
    )
    if not isinstance(employee, dict) or not isinstance(employee.get("id"), str):
        raise SseLoadFailure("employee creation did not return an id")
    conversation_id = str(uuid4())
    conversation, _ = _json_request(
        settings,
        "POST",
        "/api/v1/conversations",
        session_cookie=session_cookie,
        csrf_token=login["csrf_token"],
        tenant_id=tenant_id,
        body={
            "conversation_id": conversation_id,
            "employee_id": employee["id"],
            "title": f"S10-08 SSE {unique_suffix}",
        },
        expected_status=201,
    )
    if not isinstance(conversation, dict) or conversation.get("id") != conversation_id:
        raise SseLoadFailure("conversation creation did not return the requested id")
    return _Fixture(
        session_cookie=session_cookie,
        csrf_token=login["csrf_token"],
        tenant_id=tenant_id,
        employee_id=employee["id"],
        conversation_id=conversation_id,
    )


def _delete_fixture(settings: SseLoadSettings, fixture: _Fixture) -> None:
    _json_request(
        settings,
        "DELETE",
        f"/api/v1/conversations/{fixture.conversation_id}",
        session_cookie=fixture.session_cookie,
        csrf_token=fixture.csrf_token,
        tenant_id=fixture.tenant_id,
        expected_status=204,
    )
    _json_request(
        settings,
        "DELETE",
        f"/api/v1/employees/{fixture.employee_id}",
        session_cookie=fixture.session_cookie,
        csrf_token=fixture.csrf_token,
        tenant_id=fixture.tenant_id,
        expected_status=204,
    )


async def _hold_sse_stream(
    settings: SseLoadSettings,
    fixture: _Fixture,
    handshake: asyncio.Future[float],
    stop: asyncio.Event,
    tls_context: ssl.SSLContext,
    start_delay_seconds: float,
) -> bool:
    writer: asyncio.StreamWriter | None = None
    if start_delay_seconds:
        await asyncio.sleep(start_delay_seconds)
    started_at = time.monotonic()
    try:
        reader, writer = await asyncio.open_connection(
            settings.connect_host,
            settings.port,
            ssl=tls_context,
            server_hostname=settings.public_host,
        )
        query = urlencode({"after_sequence": 0, "tenant_id": fixture.tenant_id})
        path = f"/api/v1/conversations/{fixture.conversation_id}/events?{query}"
        handshake_request = (
            f"GET {path} HTTP/1.1\r\n"
            f"Host: {settings.public_host}\r\n"
            "Accept: text/event-stream\r\n"
            "Cache-Control: no-cache\r\n"
            f"Cookie: {fixture.session_cookie}\r\n"
            "Connection: keep-alive\r\n\r\n"
        )
        writer.writelines((handshake_request.encode("ascii"),))
        await writer.drain()
        status_line = await asyncio.wait_for(
            reader.readline(), timeout=settings.handshake_timeout_seconds
        )
        parts = status_line.decode("ascii", errors="replace").strip().split(" ", 2)
        if len(parts) < 2 or parts[1] != "200":
            raise SseLoadFailure(
                "SSE handshake returned " + status_line.decode("ascii", errors="replace").strip()
            )
        response_headers: dict[str, str] = {}
        while True:
            line = await asyncio.wait_for(
                reader.readline(), timeout=settings.handshake_timeout_seconds
            )
            if line in {b"\r\n", b"\n", b""}:
                break
            name, separator, value = line.decode("latin-1").partition(":")
            if separator:
                response_headers[name.strip().lower()] = value.strip()
        if not response_headers.get("content-type", "").lower().startswith("text/event-stream"):
            raise SseLoadFailure("SSE handshake did not return text/event-stream")
        if not handshake.done():
            handshake.set_result((time.monotonic() - started_at) * 1000)

        while True:
            read_task = asyncio.create_task(reader.read(4096))
            stop_task = asyncio.create_task(stop.wait())
            done, pending = await asyncio.wait(
                {read_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if stop_task in done and stop.is_set():
                return False
            if read_task in done and read_task.result() == b"":
                return not stop.is_set()
    except asyncio.CancelledError:
        raise
    except Exception as error:
        if not handshake.done():
            handshake.set_exception(error)
        return True
    finally:
        if not handshake.done():
            handshake.set_exception(SseLoadFailure("SSE handshake ended without a response"))
        if writer is not None:
            writer.close()
            with suppress(ConnectionError, ssl.SSLError):
                await writer.wait_closed()


async def _run_streams(settings: SseLoadSettings, fixture: _Fixture) -> tuple[int, int, int, float]:
    loop = asyncio.get_running_loop()
    stop = asyncio.Event()
    tls_context = settings.ssl_context()
    handshakes = [loop.create_future() for _ in range(settings.connections)]
    tasks = [
        asyncio.create_task(
            _hold_sse_stream(
                settings,
                fixture,
                handshake,
                stop,
                tls_context,
                index / settings.ramp_connections_per_second,
            )
        )
        for index, handshake in enumerate(handshakes)
    ]
    try:
        ramp_duration = (settings.connections - 1) / settings.ramp_connections_per_second
        done, _ = await asyncio.wait(
            handshakes,
            timeout=ramp_duration + settings.handshake_timeout_seconds,
            return_when=asyncio.ALL_COMPLETED,
        )
        samples = [
            future.result()
            for future in done
            if not future.cancelled() and future.exception() is None
        ]
        established = len(samples)
        if established == settings.connections:
            await asyncio.sleep(settings.duration_seconds)
        alive = sum(not task.done() for task in tasks)
        stop.set()
        outcomes = await asyncio.gather(*tasks, return_exceptions=True)
        unexpected_disconnects = sum(outcome is True for outcome in outcomes)
        p95 = nearest_rank_percentile(samples, 95) if samples else math.inf
        return established, alive, unexpected_disconnects, p95
    finally:
        stop.set()
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        for handshake in handshakes:
            if not handshake.done():
                handshake.cancel()


def _requests_in_flight(settings: SseLoadSettings, fixture: _Fixture) -> int:
    metrics, _ = _json_request(
        settings,
        "GET",
        "/api/v1/system/metrics",
        session_cookie=fixture.session_cookie,
    )
    value = metrics.get("requests_in_flight") if isinstance(metrics, dict) else None
    if not isinstance(value, int):
        raise SseLoadFailure("metrics did not return requests_in_flight")
    return value


def run(settings: SseLoadSettings) -> SseLoadResult:
    fixture = _create_fixture(settings)
    primary_error: BaseException | None = None
    try:
        established, alive, disconnects, handshake_p95 = asyncio.run(
            _run_streams(settings, fixture)
        )
        result = SseLoadResult(
            requested_connections=settings.connections,
            established_connections=established,
            alive_at_deadline=alive,
            unexpected_disconnects=disconnects,
            handshake_p95_ms=handshake_p95,
            requests_in_flight=_requests_in_flight(settings, fixture),
        )
        ensure_success(result, handshake_p95_limit_ms=settings.handshake_p95_limit_ms)
        return result
    except BaseException as error:
        primary_error = error
        raise
    finally:
        try:
            _delete_fixture(settings, fixture)
        except Exception as cleanup_error:
            if primary_error is None:
                raise SseLoadFailure("SSE fixture cleanup failed") from cleanup_error
            print(f"SSE fixture cleanup also failed: {cleanup_error}", file=sys.stderr)


def write_private_result(path: Path, result: SseLoadResult) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.is_symlink():
        raise SseLoadFailure("SSE result must not be a symbolic link")
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            descriptor = -1
            json.dump(asdict(result), stream, ensure_ascii=False, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        os.chmod(path, 0o600)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def main() -> int:
    try:
        settings = SseLoadSettings.from_environment(os.environ)
        result = run(settings)
        result_file = os.environ.get("COMMON_AGENT_SSE_RESULT_FILE", "").strip()
        if result_file:
            write_private_result(Path(result_file), result)
    except (OSError, ValueError, SseLoadFailure) as error:
        print(f"SSE capacity test failed: {error}", file=sys.stderr)
        return 1
    print(json.dumps(asdict(result), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
