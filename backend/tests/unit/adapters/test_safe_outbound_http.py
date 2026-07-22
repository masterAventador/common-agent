from __future__ import annotations

import asyncio
import os
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from ipaddress import ip_network

import pytest

from common_agent.adapters.security.tool_egress import (
    OutboundAccessPolicy,
    OutboundSecurityError,
    SafeOutboundHttpClient,
)


class CountingResolver:
    def __init__(self) -> None:
        self.calls = 0

    async def resolve(self, host: str, port: int) -> tuple[str, ...]:
        del host, port
        self.calls += 1
        return ("127.0.0.1",)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_GET(self) -> None:
        if self.path.startswith("/redirect"):
            self.send_response(302)
            self.send_header("Location", "http://169.254.169.254/latest/meta-data")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/set-cookie"):
            body = b"cookie-set"
            self.send_response(200)
            self.send_header("Set-Cookie", "ambient=forbidden; Path=/")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path.startswith("/check-cookie"):
            body = b"leaked" if self.headers.get("Cookie") else b"clean"
        elif self.path.startswith("/large"):
            body = b"x" * 2_048
        elif self.path.startswith("/slow"):
            time.sleep(0.2)
            body = b"late"
        else:
            body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        with suppress(BrokenPipeError):
            self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        del format, args


@contextmanager
def local_server() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def _client(
    port: int,
    resolver: CountingResolver,
    *,
    call_timeout: float = 1.0,
) -> SafeOutboundHttpClient:
    policy = OutboundAccessPolicy(
        allowed_hosts=("localhost",),
        allowed_cidrs=(ip_network("127.0.0.0/8"),),
        http_allowed_hosts=("localhost",),
        allow_loopback=True,
        resolver=resolver,
    )
    return SafeOutboundHttpClient(
        endpoint_url=f"http://localhost:{port}/mcp",
        policy=policy,
        connect_timeout_seconds=min(1.0, call_timeout),
        read_timeout_seconds=min(1.0, call_timeout),
        call_timeout_seconds=call_timeout,
        maximum_response_bytes=1_024,
        maximum_concurrency=2,
    )


def test_real_request_pins_validated_ip_and_re_resolves_each_connection() -> None:
    resolver = CountingResolver()
    with local_server() as port:
        client = _client(port, resolver)

        async def exercise() -> None:
            first = await client.request("GET", f"http://localhost:{port}/ok")
            second = await client.request("GET", f"http://localhost:{port}/ok?round=2")
            assert first.body == second.body == b'{"ok":true}'
            assert b'{"ok":true}' not in repr(first).encode()
            await client.request("GET", f"http://localhost:{port}/set-cookie")
            cookie_check = await client.request("GET", f"http://localhost:{port}/check-cookie")
            assert cookie_check.body == b"clean"
            await client.aclose()

        asyncio.run(exercise())

    assert resolver.calls == 4


def test_proxy_environment_is_ignored_and_cross_origin_is_blocked() -> None:
    resolver = CountingResolver()
    with local_server() as port:
        client = _client(port, resolver)
        previous = os.environ.get("HTTP_PROXY")
        os.environ["HTTP_PROXY"] = "http://127.0.0.1:1"

        async def exercise() -> None:
            response = await client.request("GET", f"http://localhost:{port}/ok")
            assert response.status_code == 200
            with pytest.raises(OutboundSecurityError, match="来源"):
                await client.request("GET", f"http://127.0.0.1:{port}/ok")
            await client.aclose()

        try:
            asyncio.run(exercise())
        finally:
            if previous is None:
                os.environ.pop("HTTP_PROXY", None)
            else:
                os.environ["HTTP_PROXY"] = previous


def test_redirect_response_size_and_total_timeout_fail_closed_without_url_leak() -> None:
    resolver = CountingResolver()
    with local_server() as port:
        client = _client(port, resolver, call_timeout=0.05)

        async def exercise() -> None:
            with pytest.raises(OutboundSecurityError, match="重定向"):
                await client.request("GET", f"http://localhost:{port}/redirect")
            secret_url = f"http://localhost:{port}/large?api_key=must-not-leak"
            with pytest.raises(OutboundSecurityError, match="过大") as too_large:
                await client.request("GET", secret_url)
            assert "must-not-leak" not in str(too_large.value)
            with pytest.raises(OutboundSecurityError, match="超时"):
                await client.request("GET", f"http://localhost:{port}/slow")
            await client.aclose()

        asyncio.run(exercise())


def test_stream_client_keeps_fixed_origin_and_does_not_replay_response_cookies() -> None:
    resolver = CountingResolver()
    with local_server() as port:
        client = _client(port, resolver)

        async def exercise() -> None:
            async with client.stream_client(headers={"X-MCP-Key": "secret"}) as streaming:
                first = await streaming.get(f"http://localhost:{port}/set-cookie")
                assert first.status_code == 200
                second = await streaming.get(f"http://localhost:{port}/check-cookie")
                assert second.text == "clean"
                with pytest.raises(OutboundSecurityError, match="来源"):
                    await streaming.get(f"http://127.0.0.1:{port}/ok")
            await client.aclose()

        asyncio.run(exercise())
