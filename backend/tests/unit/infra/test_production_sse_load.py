from __future__ import annotations

import asyncio
import importlib.util
import json
import stat
import sys
from dataclasses import replace
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[4] / "infra" / "production" / "sse_load_test.py"
SPEC = importlib.util.spec_from_file_location("common_agent_production_sse_load", SCRIPT_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("无法加载生产 SSE 长连接压测入口")
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def valid_environment() -> dict[str, str]:
    return {
        "COMMON_AGENT_PERFORMANCE_BASE_URL": "https://127.0.0.1:18443",
        "COMMON_AGENT_PERFORMANCE_HOST": "common-agent.test",
        "COMMON_AGENT_PERFORMANCE_EMAIL": "owner@example.com",
        "COMMON_AGENT_PERFORMANCE_PASSWORD": "owner-password",
        "COMMON_AGENT_SSE_CONNECTIONS": "128",
        "COMMON_AGENT_SSE_DURATION_SECONDS": "60",
        "COMMON_AGENT_SSE_RAMP_CONNECTIONS_PER_SECOND": "16",
        "COMMON_AGENT_SSE_HANDSHAKE_TIMEOUT_SECONDS": "15",
        "COMMON_AGENT_SSE_HANDSHAKE_P95_MS": "500",
    }


def test_settings_require_https_and_bounded_load() -> None:
    settings = MODULE.SseLoadSettings.from_environment(valid_environment())

    assert settings.base_url == "https://127.0.0.1:18443"
    assert settings.public_host == "common-agent.test"
    assert settings.connections == 128
    assert settings.duration_seconds == 60
    assert settings.ramp_connections_per_second == 16
    assert settings.handshake_p95_limit_ms == 500

    invalid_url = valid_environment() | {
        "COMMON_AGENT_PERFORMANCE_BASE_URL": "http://127.0.0.1:18443"
    }
    with pytest.raises(ValueError, match="HTTPS"):
        MODULE.SseLoadSettings.from_environment(invalid_url)

    excessive_connections = valid_environment() | {"COMMON_AGENT_SSE_CONNECTIONS": "1025"}
    with pytest.raises(ValueError, match="connections"):
        MODULE.SseLoadSettings.from_environment(excessive_connections)

    short_duration = valid_environment() | {"COMMON_AGENT_SSE_DURATION_SECONDS": "9"}
    with pytest.raises(ValueError, match="duration"):
        MODULE.SseLoadSettings.from_environment(short_duration)

    invalid_ramp = valid_environment() | {"COMMON_AGENT_SSE_RAMP_CONNECTIONS_PER_SECOND": "0"}
    with pytest.raises(ValueError, match="ramp"):
        MODULE.SseLoadSettings.from_environment(invalid_ramp)


def test_extract_session_cookie_accepts_only_production_cookie() -> None:
    assert (
        MODULE.extract_session_cookie(
            [
                "other=value; Path=/",
                "__Host-common-agent-session=opaque-session; Path=/; Secure; HttpOnly",
            ]
        )
        == "__Host-common-agent-session=opaque-session"
    )

    with pytest.raises(MODULE.SseLoadFailure, match="session cookie"):
        MODULE.extract_session_cookie(["other=value; Path=/"])


def test_delete_fixture_headers_keep_origin_and_csrf_protection() -> None:
    settings = MODULE.SseLoadSettings.from_environment(valid_environment())

    headers = MODULE.request_headers(
        settings,
        "DELETE",
        session_cookie="__Host-common-agent-session=opaque-session",
        csrf_token="csrf-token",
        tenant_id="tenant-id",
        has_body=False,
    )

    assert headers["Origin"] == "https://common-agent.test:18443"
    assert headers["X-CSRF-Token"] == "csrf-token"
    assert headers["X-Tenant-ID"] == "tenant-id"
    assert "Content-Type" not in headers


def test_percentile_uses_nearest_rank_without_hiding_slow_handshakes() -> None:
    samples = [float(value) for value in range(1, 101)]

    assert MODULE.nearest_rank_percentile(samples, 95) == 95.0

    with pytest.raises(ValueError, match="samples"):
        MODULE.nearest_rank_percentile([], 95)


def test_resolve_tenant_model_skips_accesses_without_enabled_models() -> None:
    models = {
        "empty-tenant": {"items": []},
        "ready-tenant": {"items": [{"id": "model-id"}]},
    }

    assert MODULE.resolve_tenant_model(
        [{"id": "empty-tenant"}, {"id": "ready-tenant"}],
        models.__getitem__,
    ) == ("ready-tenant", "model-id")

    with pytest.raises(MODULE.SseLoadFailure, match="enabled configuration"):
        MODULE.resolve_tenant_model([{"id": "empty-tenant"}], models.__getitem__)


def test_stream_runner_reuses_one_tls_context_for_the_capacity_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = replace(
        MODULE.SseLoadSettings.from_environment(valid_environment()),
        connections=3,
        duration_seconds=0,
    )
    fixture = MODULE._Fixture("cookie", "csrf", "tenant", "employee", "conversation")
    contexts: list[object] = []

    async def hold_stream(
        _settings: object,
        _fixture: object,
        handshake: asyncio.Future[float],
        stop: asyncio.Event,
        tls_context: object,
        start_delay_seconds: float,
    ) -> bool:
        await asyncio.sleep(start_delay_seconds)
        contexts.append(tls_context)
        handshake.set_result(1.0)
        await stop.wait()
        return False

    monkeypatch.setattr(MODULE, "_hold_sse_stream", hold_stream)

    established, alive, disconnects, p95 = asyncio.run(MODULE._run_streams(settings, fixture))

    assert (established, alive, disconnects, p95) == (3, 3, 0, 1.0)
    assert len({id(context) for context in contexts}) == 1


def test_sse_handshake_writes_an_http_request_to_the_network_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = MODULE.SseLoadSettings.from_environment(valid_environment())
    fixture = MODULE._Fixture("cookie", "csrf", "tenant", "employee", "conversation")

    class Reader:
        def __init__(self) -> None:
            self.lines = iter(
                (
                    b"HTTP/1.1 200 OK\r\n",
                    b"Content-Type: text/event-stream\r\n",
                    b"\r\n",
                )
            )

        async def readline(self) -> bytes:
            return next(self.lines)

        async def read(self, _size: int) -> bytes:
            await asyncio.Event().wait()
            return b""

    class Writer:
        def __init__(self) -> None:
            self.chunks: list[bytes] = []
            self.closed = False

        def writelines(self, chunks: tuple[bytes, ...]) -> None:
            self.chunks.extend(chunks)

        async def drain(self) -> None:
            return None

        def close(self) -> None:
            self.closed = True

        async def wait_closed(self) -> None:
            return None

    writer = Writer()

    async def open_connection(*_args: object, **_kwargs: object) -> tuple[Reader, Writer]:
        return Reader(), writer

    monkeypatch.setattr(MODULE.asyncio, "open_connection", open_connection)

    async def exercise() -> tuple[bool, float]:
        loop = asyncio.get_running_loop()
        handshake: asyncio.Future[float] = loop.create_future()
        stop = asyncio.Event()
        stop.set()
        disconnected = await MODULE._hold_sse_stream(
            settings,
            fixture,
            handshake,
            stop,
            settings.ssl_context(),
            0,
        )
        return disconnected, handshake.result()

    disconnected, handshake_ms = asyncio.run(exercise())

    request = b"".join(writer.chunks)
    assert disconnected is False
    assert handshake_ms >= 0
    assert request.startswith(
        b"GET /api/v1/conversations/conversation/events?after_sequence=0&tenant_id=tenant "
        b"HTTP/1.1\r\n"
    )
    assert b"Host: common-agent.test\r\n" in request
    assert b"Accept: text/event-stream\r\n" in request
    assert b"Cookie: cookie\r\n" in request
    assert writer.closed is True


def test_result_rejects_partial_capacity_disconnects_latency_and_leaks() -> None:
    healthy = MODULE.SseLoadResult(
        requested_connections=128,
        established_connections=128,
        alive_at_deadline=128,
        unexpected_disconnects=0,
        handshake_p95_ms=42.5,
        requests_in_flight=0,
    )
    MODULE.ensure_success(healthy, handshake_p95_limit_ms=500)

    failures = (
        MODULE.SseLoadResult(128, 127, 127, 0, 42.5, 0),
        MODULE.SseLoadResult(128, 128, 127, 1, 42.5, 0),
        MODULE.SseLoadResult(128, 128, 128, 0, 500.1, 0),
        MODULE.SseLoadResult(128, 128, 128, 0, 42.5, 1),
    )
    for result in failures:
        with pytest.raises(MODULE.SseLoadFailure):
            MODULE.ensure_success(result, handshake_p95_limit_ms=500)


def test_result_file_is_private_and_rejects_symbolic_link(tmp_path: Path) -> None:
    output = tmp_path / "sse-result.json"
    result = MODULE.SseLoadResult(128, 128, 128, 0, 42.5, 0)

    MODULE.write_private_result(output, result)

    assert json.loads(output.read_text(encoding="utf-8"))["alive_at_deadline"] == 128
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    output.unlink()
    output.symlink_to(tmp_path / "target")
    with pytest.raises(MODULE.SseLoadFailure, match="symbolic link"):
        MODULE.write_private_result(output, result)
