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
    process = _start_api(database_url, port, env_overrides)
    base_url = f"http://127.0.0.1:{port}"

    try:
        _wait_for_api(process, base_url)
        yield base_url
    finally:
        _stop_api(process)


@contextmanager
def running_apis(
    database_url: str,
    *,
    count: int,
    env_overrides: Mapping[str, str] | None = None,
) -> Iterator[tuple[str, ...]]:
    if count < 1:
        raise ValueError("count must be positive")
    ports: set[int] = set()
    while len(ports) < count:
        ports.add(available_port())
    processes = [_start_api(database_url, port, env_overrides) for port in sorted(ports)]
    base_urls = tuple(f"http://127.0.0.1:{port}" for port in sorted(ports))

    try:
        for process, base_url in zip(processes, base_urls, strict=True):
            _wait_for_api(process, base_url)
        yield base_urls
    finally:
        for process in processes:
            _stop_api(process)


def _start_api(
    database_url: str,
    port: int,
    env_overrides: Mapping[str, str] | None,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["COMMON_AGENT_DATABASE_URL"] = database_url
    if env_overrides is not None:
        env.update(env_overrides)
    return subprocess.Popen(
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


def _wait_for_api(process: subprocess.Popen[str], base_url: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            pytest.fail(f"Uvicorn exited before becoming ready:\n{output}")
        try:
            with urlopen(f"{base_url}/api/v1/system/health", timeout=0.25):
                return
        except (HTTPError, URLError, TimeoutError):
            time.sleep(0.05)
    pytest.fail("Uvicorn did not become ready within 10 seconds")


def _stop_api(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
