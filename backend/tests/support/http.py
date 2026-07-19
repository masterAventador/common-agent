from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import UUID

import httpx
import pytest


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def assert_error_response(response: httpx.Response, *, status: int, code: str) -> None:
    assert response.status_code == status
    UUID(response.headers["X-Request-ID"])
    body = response.json()
    assert body["code"] == code
    assert set(body) == {"code", "message", "request_id", "retryable"}


@contextmanager
def running_api(
    database_url: str,
    *,
    env_overrides: Mapping[str, str] | None = None,
) -> Iterator[str]:
    port = available_port()
    env = os.environ.copy()
    env["COMMON_AGENT_DATABASE_URL"] = database_url
    if env_overrides is not None:
        env.update(env_overrides)
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
        env=env,
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
