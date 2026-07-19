from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPResponse
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import UUID

import pytest


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _read_json(response: HTTPResponse | HTTPError) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


@contextmanager
def _running_api() -> Iterator[str]:
    port = _available_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "common_agent.api.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 10

    try:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                output = process.stdout.read() if process.stdout else ""
                pytest.fail(f"Uvicorn exited before becoming ready:\n{output}")
            try:
                with urlopen(f"{base_url}/api/v1/system/health", timeout=0.25):
                    break
            except (HTTPError, URLError, TimeoutError):
                time.sleep(0.05)
        else:
            pytest.fail("Uvicorn did not become ready within 10 seconds")

        yield base_url
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def test_health_uses_real_loopback_uvicorn() -> None:
    with (
        _running_api() as base_url,
        urlopen(f"{base_url}/api/v1/system/health", timeout=2) as response,
    ):
        body = _read_json(response)

    assert response.status == 200
    UUID(response.headers["X-Request-ID"])
    assert body == {
        "status": "ok",
        "service": "common-agent-api",
        "version": "0.1.0",
    }


def test_unknown_route_uses_stable_error_envelope_over_real_http() -> None:
    with _running_api() as base_url:
        with pytest.raises(HTTPError) as captured:
            urlopen(f"{base_url}/api/v1/does-not-exist", timeout=2)

        error = captured.value
        body = _read_json(error)

    assert error.status == 404
    request_id = error.headers["X-Request-ID"]
    UUID(request_id)
    assert body == {
        "code": "resource_not_found",
        "message": "请求的资源不存在",
        "request_id": request_id,
        "retryable": False,
    }
