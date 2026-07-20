from __future__ import annotations

import asyncio
import json
import logging
from io import StringIO
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from fastapi import Request, Response
from starlette.types import Scope

from common_agent.api.observability import observe_http_request
from common_agent.observability import (
    JsonLogFormatter,
    MetricsRegistry,
    bind_observation_context,
    current_observation_context,
    log_event,
    outbound_trace_headers,
)


def test_observation_context_inherits_trace_and_restores_nested_business_ids() -> None:
    request_id = str(uuid4())
    conversation_id = uuid4()
    message_id = uuid4()
    incoming_trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    incoming_span_id = "00f067aa0ba902b7"

    with bind_observation_context(
        request_id=request_id,
        traceparent=f"00-{incoming_trace_id}-{incoming_span_id}-01",
    ) as request_context:
        assert request_context.request_id == request_id
        assert request_context.trace_id == incoming_trace_id
        assert request_context.parent_span_id == incoming_span_id
        assert request_context.span_id != incoming_span_id
        assert request_context.traceparent.startswith(f"00-{incoming_trace_id}-")

        with bind_observation_context(
            conversation_id=conversation_id,
            message_id=message_id,
        ) as business_context:
            assert business_context.conversation_id == str(conversation_id)
            assert business_context.message_id == str(message_id)
            assert current_observation_context() == business_context
            outbound = outbound_trace_headers()
            assert outbound["X-Request-ID"] == request_id
            assert outbound["traceparent"].startswith(f"00-{incoming_trace_id}-")
            assert outbound["traceparent"] != business_context.traceparent

        assert current_observation_context() == request_context

    assert current_observation_context() is None


def test_invalid_traceparent_is_replaced_with_a_safe_local_trace() -> None:
    with bind_observation_context(
        request_id=str(uuid4()), traceparent="00-secret-invalid"
    ) as context:
        assert len(context.trace_id) == 32
        assert len(context.span_id) == 16
        assert context.parent_span_id is None
        assert context.traceparent == f"00-{context.trace_id}-{context.span_id}-01"


def test_json_logging_contains_correlation_and_redacts_sensitive_fields() -> None:
    output = StringIO()
    handler = logging.StreamHandler(output)
    handler.setFormatter(JsonLogFormatter())
    logger = logging.getLogger(f"common_agent.test.{uuid4().hex}")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    prompt = "private prompt body"
    knowledge = "private knowledge body"
    api_key = "sk-private-key"
    password = "private-password"
    upstream = "private upstream response"

    with bind_observation_context(
        request_id=str(uuid4()),
        conversation_id=uuid4(),
        message_id=uuid4(),
        turn_id=uuid4(),
        workflow_id=uuid4(),
        run_id=uuid4(),
    ):
        log_event(
            logger,
            "conversation.turn.finished",
            level=logging.ERROR,
            status="failed",
            error_code="model_unavailable",
            duration_ms=12.5,
            prompt=prompt,
            knowledge_content=knowledge,
            api_key=api_key,
            password=password,
            upstream_response={"detail": upstream},
        )

    raw = output.getvalue()
    payload = json.loads(raw)
    assert payload["event"] == "conversation.turn.finished"
    assert payload["level"] == "ERROR"
    assert payload["logger"] == logger.name
    assert payload["status"] == "failed"
    assert payload["error_code"] == "model_unavailable"
    assert payload["duration_ms"] == 12.5
    assert payload["request_id"]
    assert payload["trace_id"]
    assert payload["conversation_id"]
    assert payload["message_id"]
    assert payload["turn_id"]
    assert payload["workflow_id"]
    assert payload["run_id"]
    assert payload["prompt"] == "[REDACTED]"
    assert payload["knowledge_content"] == "[REDACTED]"
    assert payload["api_key"] == "[REDACTED]"
    assert payload["password"] == "[REDACTED]"
    assert payload["upstream_response"] == "[REDACTED]"
    for secret in (prompt, knowledge, api_key, password, upstream):
        assert secret not in raw

    logger.info("Authorization: Bearer sk-message-secret password=message-password")
    generic_raw = output.getvalue().splitlines()[-1]
    assert "sk-message-secret" not in generic_raw
    assert "message-password" not in generic_raw
    assert generic_raw.count("[REDACTED]") == 2

    logger.error(
        "Traceback (most recent call last):\n"
        '  File "/Users/private/project/app.py", line 1, in run\n'
        "common_agent.DatabaseStartupError: password=private-password"
    )
    traceback_payload = json.loads(output.getvalue().splitlines()[-1])
    assert traceback_payload["message"] == "[REDACTED_EXCEPTION]"
    assert traceback_payload["exception_type"] == "DatabaseStartupError"
    assert "/Users/private" not in json.dumps(traceback_payload)
    assert "private-password" not in json.dumps(traceback_payload)


def test_metrics_registry_tracks_status_latency_errors_and_bounds_error_labels() -> None:
    metrics = MetricsRegistry(max_error_codes=2)

    first = metrics.begin_request()
    metrics.complete_request(first, status_code=200, error_code=None)
    for code in ("model_unavailable", "knowledge_service_unavailable", "unexpected_new_code"):
        started = metrics.begin_request()
        metrics.complete_request(started, status_code=503, error_code=code)

    snapshot = metrics.snapshot()
    assert snapshot.requests_in_flight == 0
    assert snapshot.requests_total == 4
    assert snapshot.responses_by_status == {"2xx": 1, "5xx": 3}
    assert snapshot.errors_by_code == {
        "knowledge_service_unavailable": 1,
        "model_unavailable": 1,
        "other": 1,
    }
    assert snapshot.latency_ms.count == 4
    assert snapshot.latency_ms.total >= 0
    assert snapshot.latency_ms.maximum >= 0
    assert snapshot.uptime_seconds >= 0


def test_http_observer_returns_safe_correlated_internal_error_and_metrics() -> None:
    metrics = MetricsRegistry()
    scope = cast(
        Scope,
        {
            "type": "http",
            "method": "GET",
            "path": "/api/v1/failing",
            "raw_path": b"/api/v1/failing",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("127.0.0.1", 80),
            "client": ("127.0.0.1", 12345),
            "app": SimpleNamespace(state=SimpleNamespace(metrics=metrics)),
        },
    )
    request = Request(scope)

    async def fail(_: Request) -> Response:
        raise RuntimeError("private upstream response and password")

    response = asyncio.run(observe_http_request(request, fail))
    body = json.loads(bytes(response.body))
    snapshot = metrics.snapshot()

    assert response.status_code == 500
    assert response.headers["X-Request-ID"] == body["request_id"]
    assert response.headers["traceparent"].startswith("00-")
    assert body["code"] == "internal_error"
    assert "private upstream" not in bytes(response.body).decode()
    assert snapshot.requests_total == 1
    assert snapshot.responses_by_status == {"5xx": 1}
    assert snapshot.errors_by_code == {"internal_error": 1}
