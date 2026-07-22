from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from http.client import HTTPResponse
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest
from urllib.request import urlopen
from uuid import UUID

import pytest
from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from tests.support.http import available_port, running_api
from tests.support.ragflow import provision_api_key
from tests.support.settings import TEST_DATABASE_URL


def _read_json(response: HTTPResponse | HTTPError) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(response.read().decode("utf-8")))


def _database_url() -> str:
    return os.environ.get(
        "TEST_PLATFORM_DATABASE_URL",
        TEST_DATABASE_URL,
    )


def test_health_uses_real_loopback_uvicorn() -> None:
    with (
        running_api(_database_url()) as base_url,
        urlopen(f"{base_url}/api/v1/system/health", timeout=2) as response,
    ):
        body = _read_json(response)

    assert response.status == 200
    UUID(response.headers["X-Request-ID"])
    assert body == {
        "status": "ok",
        "service": "common-agent-api",
        "version": "0.1.0",
        "integration_mode": "real",
    }


def test_health_exposes_explicit_demo_mode_over_formal_uvicorn() -> None:
    with (
        running_api(
            _database_url(),
            env_overrides={
                "COMMON_AGENT_INTEGRATION_MODE": "demo",
                "RAGFLOW_BASE_URL": "https://invalid.example.com",
                "BAILIAN_BASE_URL": "http://invalid.example.com",
            },
        ) as base_url,
        urlopen(f"{base_url}/api/v1/system/health", timeout=2) as response,
    ):
        body = _read_json(response)

    assert response.status == 200
    assert body["integration_mode"] == "demo"


def test_status_exposes_demo_dependencies_without_presenting_them_as_real() -> None:
    with (
        running_api(
            _database_url(),
            env_overrides={"COMMON_AGENT_INTEGRATION_MODE": "demo"},
        ) as base_url,
        urlopen(f"{base_url}/api/v1/system/status", timeout=2) as response,
    ):
        body = _read_json(response)

    assert response.status == 200
    assert body == {
        "backend": "available",
        "service": "common-agent-api",
        "version": "0.1.0",
        "integration_mode": "demo",
        "model": {"provider": "demo", "status": "demo"},
        "knowledge": {
            "provider": "demo",
            "availability": "available",
            "version": "demo-1",
            "error_code": None,
        },
    }


def test_status_exposes_real_ragflow_and_configured_bailian_over_formal_uvicorn() -> None:
    base_url = os.environ.get("TEST_RAGFLOW_BASE_URL")
    expected_version = os.environ.get("TEST_RAGFLOW_EXPECTED_VERSION")
    api_key = os.environ.get("TEST_RAGFLOW_API_KEY")
    if not base_url or not expected_version:
        pytest.skip("真实 RAGFlow 地址或期望版本未配置")
    if not api_key:
        api_key = asyncio.run(provision_api_key(base_url))

    with (
        running_api(
            _database_url(),
            env_overrides={
                "COMMON_AGENT_INTEGRATION_MODE": "real",
                "RAGFLOW_BASE_URL": base_url,
                "RAGFLOW_API_KEY": api_key,
                "RAGFLOW_EXPECTED_VERSION": expected_version,
            },
        ) as api_url,
        urlopen(f"{api_url}/api/v1/system/status", timeout=5) as response,
    ):
        body = _read_json(response)

    assert response.status == 200
    assert body["integration_mode"] == "real"
    assert body["model"] == {"provider": "bailian", "status": "configured"}
    assert body["knowledge"] == {
        "provider": "ragflow",
        "availability": "available",
        "version": expected_version,
        "error_code": None,
    }


def test_unknown_route_uses_stable_error_envelope_over_real_http() -> None:
    with running_api(_database_url()) as base_url:
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
            running_api(database_url) as base_url,
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

    assert asyncio.run(revision()) == "20260722_0025"


def test_health_allows_the_project_frontend_origin_over_real_http() -> None:
    request = UrlRequest(
        "http://127.0.0.1:0/api/v1/system/health",
        headers={"Origin": "http://127.0.0.1:18280"},
    )

    with running_api(_database_url()) as base_url:
        request.full_url = f"{base_url}/api/v1/system/health"
        with urlopen(request, timeout=2) as response:
            response.read()

    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:18280"


def test_formal_api_fails_closed_when_mysql_authentication_fails() -> None:
    port = available_port()
    secret = "api-startup-secret-must-not-leak"
    database_url = (
        f"mysql+aiomysql://common_agent:{secret}@127.0.0.1:19506/common_agent?charset=utf8mb4"
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
