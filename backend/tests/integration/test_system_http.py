from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPResponse
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from uuid import UUID

import pytest
from sqlalchemy import text

from common_agent.adapters.persistence.database import Database


def _available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _read_json(response: HTTPResponse | HTTPError) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


def _database_url() -> str:
    return os.environ.get(
        "TEST_PLATFORM_DATABASE_URL",
        "mysql+asyncmy://common_agent:common_agent_dev@127.0.0.1:19506/"
        "common_agent_test?charset=utf8mb4",
    )


@contextmanager
def _running_api(database_url: str) -> Iterator[str]:
    port = _available_port()
    env = os.environ.copy()
    env["COMMON_AGENT_DATABASE_URL"] = database_url
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


def test_health_uses_real_loopback_uvicorn() -> None:
    with (
        _running_api(_database_url()) as base_url,
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
    with _running_api(_database_url()) as base_url:
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


def test_formal_api_migrates_mysql_and_recovers_after_restart() -> None:
    database_url = _database_url()

    for _ in range(2):
        with (
            _running_api(database_url) as base_url,
            urlopen(f"{base_url}/api/v1/system/health", timeout=2) as response,
        ):
            assert response.status == 200

    async def revision() -> str:
        database = Database(database_url)
        await database.start()
        try:
            async with database.session() as session:
                result = await session.execute(text("SELECT version_num FROM alembic_version"))
                return str(result.scalar_one())
        finally:
            await database.stop()

    assert asyncio.run(revision()) == "20260719_0001"


def test_health_allows_the_project_frontend_origin_over_real_http() -> None:
    request = UrlRequest(
        "http://127.0.0.1:0/api/v1/system/health",
        headers={"Origin": "http://127.0.0.1:18280"},
    )

    with _running_api(_database_url()) as base_url:
        request.full_url = f"{base_url}/api/v1/system/health"
        with urlopen(request, timeout=2) as response:
            response.read()

    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:18280"


def test_formal_api_fails_closed_when_mysql_authentication_fails() -> None:
    port = _available_port()
    secret = "api-startup-secret-must-not-leak"
    database_url = (
        f"mysql+asyncmy://common_agent:{secret}@127.0.0.1:19506/common_agent?charset=utf8mb4"
    )
    env = os.environ.copy()
    env["COMMON_AGENT_DATABASE_URL"] = database_url
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

    try:
        output, _ = process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=5)
        pytest.fail("Uvicorn did not fail closed after MySQL authentication failure")

    assert process.returncode != 0
    assert database_url not in output
    assert secret not in output
    with pytest.raises(URLError):
        urlopen(f"http://127.0.0.1:{port}/api/v1/system/health", timeout=0.25)
