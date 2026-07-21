from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path
from typing import IO
from urllib.error import HTTPError, URLError
from urllib.request import urlopen
from uuid import UUID

import httpx
import pytest

TEST_AUTH_BOOTSTRAP_TOKEN = "test-bootstrap-token-that-is-at-least-32-characters"
TEST_AUTH_EMAIL = "integration-owner@example.com"
TEST_AUTH_PASSWORD = "integration owner password is long enough"
TEST_FRONTEND_ORIGIN = "http://127.0.0.1:18280"
_PUBLIC_AUTH_WRITES = {
    "/api/v1/auth/register",
    "/api/v1/auth/login",
    "/api/v1/auth/recovery/reset",
}


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


def authenticated_client(
    *,
    base_url: str,
    timeout: float,
) -> httpx.Client:
    csrf_token = ""

    def authorize(request: httpx.Request) -> None:
        nonlocal csrf_token
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return
        request.headers.setdefault("Origin", TEST_FRONTEND_ORIGIN)
        if csrf_token and request.url.path not in _PUBLIC_AUTH_WRITES:
            request.headers.setdefault("X-CSRF-Token", csrf_token)

    with httpx.Client(base_url=base_url, timeout=timeout) as login_client:
        policy = login_client.get("/api/v1/auth/policy")
        policy.raise_for_status()
        if policy.json()["registration_available"]:
            authenticated = login_client.post(
                "/api/v1/auth/register",
                headers={"Origin": TEST_FRONTEND_ORIGIN},
                json={
                    "email": TEST_AUTH_EMAIL,
                    "password": TEST_AUTH_PASSWORD,
                    "bootstrap_token": TEST_AUTH_BOOTSTRAP_TOKEN,
                },
            )
        else:
            authenticated = login_client.post(
                "/api/v1/auth/login",
                headers={"Origin": TEST_FRONTEND_ORIGIN},
                json={"email": TEST_AUTH_EMAIL, "password": TEST_AUTH_PASSWORD},
            )
        authenticated.raise_for_status()
        csrf_token = str(authenticated.json()["csrf_token"])
        cookies = httpx.Cookies(login_client.cookies)
    return httpx.Client(
        base_url=base_url,
        timeout=timeout,
        cookies=cookies,
        event_hooks={"request": [authorize]},
    )


async def authenticated_async_client(
    *,
    base_url: str,
    timeout: float,
) -> httpx.AsyncClient:
    csrf_token = ""

    async def authorize(request: httpx.Request) -> None:
        nonlocal csrf_token
        if request.method in {"GET", "HEAD", "OPTIONS"}:
            return
        request.headers.setdefault("Origin", TEST_FRONTEND_ORIGIN)
        if csrf_token and request.url.path not in _PUBLIC_AUTH_WRITES:
            request.headers.setdefault("X-CSRF-Token", csrf_token)

    async with httpx.AsyncClient(base_url=base_url, timeout=timeout) as login_client:
        policy = await login_client.get("/api/v1/auth/policy")
        policy.raise_for_status()
        if policy.json()["registration_available"]:
            authenticated = await login_client.post(
                "/api/v1/auth/register",
                headers={"Origin": TEST_FRONTEND_ORIGIN},
                json={
                    "email": TEST_AUTH_EMAIL,
                    "password": TEST_AUTH_PASSWORD,
                    "bootstrap_token": TEST_AUTH_BOOTSTRAP_TOKEN,
                },
            )
        else:
            authenticated = await login_client.post(
                "/api/v1/auth/login",
                headers={"Origin": TEST_FRONTEND_ORIGIN},
                json={"email": TEST_AUTH_EMAIL, "password": TEST_AUTH_PASSWORD},
            )
        authenticated.raise_for_status()
        csrf_token = str(authenticated.json()["csrf_token"])
        cookies = httpx.Cookies(login_client.cookies)
    return httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        cookies=cookies,
        event_hooks={"request": [authorize]},
    )


@contextmanager
def running_api(
    database_url: str,
    *,
    env_overrides: Mapping[str, str] | None = None,
    log_path: Path | None = None,
) -> Iterator[str]:
    port = available_port()
    log_file = log_path.open("w+", encoding="utf-8") if log_path is not None else None
    process = _start_api(database_url, port, env_overrides, stdout=log_file)
    base_url = f"http://127.0.0.1:{port}"

    try:
        _wait_for_api(process, base_url, startup_log=log_file)
        yield base_url
    finally:
        _stop_api(process)
        if log_file is not None:
            log_file.close()


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
    *,
    stdout: IO[str] | int | None = subprocess.PIPE,
) -> subprocess.Popen[str]:
    env = os.environ.copy()
    env["COMMON_AGENT_DATABASE_URL"] = database_url
    env["COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN"] = TEST_AUTH_BOOTSTRAP_TOKEN
    if env.get("TEST_BAILIAN_REAL") != "1":
        env.update(
            {
                "BAILIAN_API_KEY": "integration-test-secret",
                "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
                "BAILIAN_MODEL": "integration-test-model",
            }
        )
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
        stdout=stdout,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )


def _wait_for_api(
    process: subprocess.Popen[str],
    base_url: str,
    *,
    startup_log: IO[str] | None = None,
) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            if process.stdout is not None:
                output = process.stdout.read()
            elif startup_log is not None:
                startup_log.flush()
                startup_log.seek(0)
                output = startup_log.read()
            else:
                output = ""
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
