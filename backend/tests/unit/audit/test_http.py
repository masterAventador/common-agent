from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import cast
from uuid import UUID

from fastapi import Request, Response

from common_agent.api.app import create_app
from common_agent.api.audit import audit_http_request
from common_agent.audit import (
    AuditAction,
    AuditEntry,
    AuditEvent,
    AuditIntegrity,
    AuditOutcome,
    AuditPage,
    AuditQuery,
    AuditService,
)


class _AuditStoreProbe:
    def __init__(self, *, fail_on: int) -> None:
        self.fail_on = fail_on
        self.entries: list[AuditEntry] = []

    async def append(
        self,
        entry: AuditEntry,
        *,
        retention_until: datetime,
        max_events_per_scope: int,
    ) -> AuditEvent:
        del retention_until, max_events_per_scope
        self.entries.append(entry)
        if len(self.entries) == self.fail_on:
            raise RuntimeError("audit unavailable")
        return cast(AuditEvent, object())

    async def page(self, query: AuditQuery) -> AuditPage:
        del query
        return AuditPage()

    async def verify(self, tenant_id: UUID | None) -> AuditIntegrity:
        del tenant_id
        raise AssertionError("not expected")


def _request(
    service: AuditService,
    *,
    path: str = "/api/v1/employees",
) -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "POST",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("127.0.0.1", 18200),
            "app": SimpleNamespace(state=SimpleNamespace(audit=service)),
        }
    )


def test_atomic_first_conversation_turn_uses_the_reply_audit_action() -> None:
    async def scenario() -> _AuditStoreProbe:
        store = _AuditStoreProbe(fail_on=99)

        async def handler(request: Request) -> Response:
            del request
            return Response(status_code=202)

        response = await audit_http_request(
            _request(AuditService(store), path="/api/v1/conversation-turns"),
            handler,
        )
        assert response.status_code == 202
        return store

    store = asyncio.run(scenario())
    assert [entry.action for entry in store.entries] == [
        AuditAction.CONVERSATION_REPLY_STARTED,
        AuditAction.CONVERSATION_REPLY_STARTED,
    ]


def test_observability_wraps_the_fail_closed_audit_middleware() -> None:
    app = create_app()

    middleware_order = [
        getattr(middleware.kwargs.get("dispatch"), "__name__", None)
        for middleware in app.user_middleware
    ]

    assert middleware_order[:3] == [
        "observe_http_request",
        "audit_http_request",
        "enforce_request_security",
    ]


def test_audit_intent_failure_blocks_the_business_handler() -> None:
    async def scenario() -> tuple[Response, int, _AuditStoreProbe]:
        store = _AuditStoreProbe(fail_on=1)
        called = 0

        async def handler(request: Request) -> Response:
            nonlocal called
            del request
            called += 1
            return Response(status_code=201)

        response = await audit_http_request(_request(AuditService(store)), handler)
        return response, called, store

    response, called, store = asyncio.run(scenario())
    assert response.status_code == 503
    assert called == 0
    assert store.entries[0].outcome is AuditOutcome.STARTED


def test_audit_completion_failure_keeps_success_after_durable_intent() -> None:
    async def scenario() -> tuple[Response, _AuditStoreProbe]:
        store = _AuditStoreProbe(fail_on=2)

        async def handler(request: Request) -> Response:
            del request
            return Response(status_code=201)

        response = await audit_http_request(_request(AuditService(store)), handler)
        return response, store

    response, store = asyncio.run(scenario())
    assert response.status_code == 201
    assert [entry.outcome for entry in store.entries] == [
        AuditOutcome.STARTED,
        AuditOutcome.SUCCEEDED,
    ]
