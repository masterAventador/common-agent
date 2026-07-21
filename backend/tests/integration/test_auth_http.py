from __future__ import annotations

import asyncio
import os
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from sqlalchemy import text

from common_agent.adapters.persistence.database import Database
from tests.support.http import assert_error_response, running_api
from tests.support.settings import TEST_DATABASE_URL

BOOTSTRAP_TOKEN = "integration-bootstrap-token-at-least-32-characters"
ORIGIN = "http://127.0.0.1:18280"
PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "replacement horse battery password"


async def _clear_authentication() -> None:
    database = Database(os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL))
    await database.start()
    try:
        async with database.session() as session:
            await session.execute(text("DELETE FROM auth_login_attempts"))
            await session.execute(text("DELETE FROM auth_users"))
            await session.commit()
    finally:
        await database.stop()


@contextmanager
def _running_auth_api() -> Iterator[str]:
    asyncio.run(_clear_authentication())
    try:
        with running_api(
            TEST_DATABASE_URL,
            env_overrides={
                "COMMON_AGENT_INTEGRATION_MODE": "demo",
                "COMMON_AGENT_AUTH_BOOTSTRAP_TOKEN": BOOTSTRAP_TOKEN,
                "COMMON_AGENT_AUTH_LOGIN_MAX_ATTEMPTS": "3",
                "COMMON_AGENT_AUTH_LOGIN_WINDOW_SECONDS": "60",
            },
        ) as base_url:
            asyncio.run(_clear_authentication())
            yield base_url
    finally:
        asyncio.run(_clear_authentication())


def _register(client: httpx.Client) -> httpx.Response:
    response = client.post(
        "/api/v1/auth/register",
        headers={"Origin": ORIGIN},
        json={
            "email": "Owner@Example.com",
            "password": PASSWORD,
            "bootstrap_token": BOOTSTRAP_TOKEN,
        },
    )
    assert response.status_code == 201
    return response


def test_auth_http_registration_cookie_csrf_logout_and_replay_boundaries() -> None:
    with (
        _running_auth_api() as api_url,
        httpx.Client(base_url=api_url, timeout=10) as client,
    ):
        policy = client.get("/api/v1/auth/policy")
        assert policy.status_code == 200
        assert policy.json() == {"registration_available": True}

        unauthenticated_read = client.get("/api/v1/employees")
        unauthenticated_write = client.post("/api/v1/employees", json={})
        assert_error_response(
            unauthenticated_read,
            status=401,
            code="authentication_required",
        )
        assert_error_response(
            unauthenticated_write,
            status=401,
            code="authentication_required",
        )

        registration_response = _register(client)
        registered = registration_response.json()
        assert registered["email"] == "owner@example.com"
        assert len(registered["recovery_codes"]) == 8
        assert set(registered) == {
            "user_id",
            "email",
            "csrf_token",
            "idle_expires_at",
            "absolute_expires_at",
            "recovery_codes",
        }
        assert PASSWORD not in str(registered)
        assert BOOTSTRAP_TOKEN not in str(registered)
        set_cookie = client.cookies.get("common_agent_session")
        assert set_cookie
        raw_set_cookie = registration_response.headers.get_list("set-cookie")[0].lower()
        assert "httponly" in raw_set_cookie
        assert "samesite=strict" in raw_set_cookie
        assert "path=/" in raw_set_cookie
        assert "secure" not in raw_set_cookie

        current = client.get("/api/v1/auth/session")
        assert current.status_code == 200
        assert current.headers["Cache-Control"] == "no-store"
        csrf_token = current.json()["csrf_token"]
        assert client.get("/api/v1/employees").status_code == 200

        missing_csrf = client.post(
            "/api/v1/employees",
            headers={"Origin": ORIGIN},
            json={},
        )
        wrong_csrf = client.post(
            "/api/v1/employees",
            headers={"Origin": ORIGIN, "X-CSRF-Token": "wrong-token"},
            json={},
        )
        assert_error_response(missing_csrf, status=403, code="csrf_validation_failed")
        assert_error_response(wrong_csrf, status=403, code="csrf_validation_failed")

        logout = client.post(
            "/api/v1/auth/logout",
            headers={"Origin": ORIGIN, "X-CSRF-Token": csrf_token},
        )
        assert logout.status_code == 204
        assert "max-age=0" in logout.headers["set-cookie"].lower()
        client.cookies.set("common_agent_session", set_cookie)
        replay = client.get("/api/v1/auth/session")
        assert_error_response(replay, status=401, code="authentication_required")


def test_auth_http_rejects_cross_origin_bootstrap_and_rate_limits_login() -> None:
    with (
        _running_auth_api() as api_url,
        httpx.Client(base_url=api_url, timeout=10) as client,
    ):
        cross_origin = client.post(
            "/api/v1/auth/register",
            headers={"Origin": "https://attacker.example"},
            json={
                "email": "owner@example.com",
                "password": PASSWORD,
                "bootstrap_token": BOOTSTRAP_TOKEN,
            },
        )
        assert_error_response(cross_origin, status=403, code="origin_validation_failed")
        _register(client)
        client.cookies.clear()

        for _ in range(3):
            rejected = client.post(
                "/api/v1/auth/login",
                headers={"Origin": ORIGIN},
                json={"email": "owner@example.com", "password": "wrong password value"},
            )
            assert_error_response(rejected, status=401, code="invalid_credentials")

        limited = client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "owner@example.com", "password": PASSWORD},
        )
        assert_error_response(limited, status=429, code="login_rate_limited")


def test_auth_http_recovery_is_single_use_and_revokes_old_session() -> None:
    with (
        _running_auth_api() as api_url,
        httpx.Client(base_url=api_url, timeout=10) as client,
    ):
        registered = _register(client).json()
        old_cookie = client.cookies.get("common_agent_session")
        recovery_code = str(registered["recovery_codes"][0])

        reset = client.post(
            "/api/v1/auth/recovery/reset",
            headers={"Origin": ORIGIN},
            json={
                "email": "owner@example.com",
                "recovery_code": recovery_code.lower(),
                "new_password": NEW_PASSWORD,
            },
        )
        assert reset.status_code == 204
        assert old_cookie
        assert_error_response(
            client.get("/api/v1/auth/session"),
            status=401,
            code="authentication_required",
        )

        replay = client.post(
            "/api/v1/auth/recovery/reset",
            headers={"Origin": ORIGIN},
            json={
                "email": "owner@example.com",
                "recovery_code": recovery_code,
                "new_password": "another replacement password",
            },
        )
        assert_error_response(
            replay,
            status=401,
            code="invalid_recovery_credentials",
        )
        login = client.post(
            "/api/v1/auth/login",
            headers={"Origin": ORIGIN},
            json={"email": "owner@example.com", "password": NEW_PASSWORD},
        )
        assert login.status_code == 200


def test_auth_http_expired_session_is_revoked_by_formal_database_lookup() -> None:
    with (
        _running_auth_api() as api_url,
        httpx.Client(base_url=api_url, timeout=10) as client,
    ):
        _register(client)

        async def expire() -> None:
            database = Database(TEST_DATABASE_URL)
            await database.start()
            try:
                async with database.session() as session:
                    await session.execute(
                        text(
                            "UPDATE auth_sessions SET created_at = '2020-01-01 00:00:00', "
                            "last_seen_at = '2020-01-01 00:00:00', "
                            "idle_expires_at = '2020-01-01 00:00:01', "
                            "absolute_expires_at = '2020-01-01 00:00:01'"
                        )
                    )
                    await session.commit()
            finally:
                await database.stop()

        asyncio.run(expire())
        expired = client.get("/api/v1/auth/session")
        assert_error_response(expired, status=401, code="authentication_required")
