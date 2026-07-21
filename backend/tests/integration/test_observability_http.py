from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from common_agent.adapters.persistence.database import Database
from common_agent.employees.seeds import DEFAULT_KNOWLEDGE_ASSISTANT_ID
from tests.support.conversations import delete_conversations
from tests.support.http import authenticated_client, running_api
from tests.support.settings import TEST_DATABASE_URL


def test_formal_http_trace_metrics_and_json_logs_are_correlated_and_safe(
    tmp_path: Path,
    request: pytest.FixtureRequest,
) -> None:
    log_path = tmp_path / "api.jsonl"
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    parent_span_id = "00f067aa0ba902b7"
    traceparent = f"00-{trace_id}-{parent_span_id}-01"
    secret_key = "sk-observability-must-not-leak"
    secret_prompt = "private prompt must not leak"
    conversation_id = uuid4()
    request.addfinalizer(lambda: asyncio.run(_delete_conversation(conversation_id)))

    with (
        running_api(
            TEST_DATABASE_URL,
            env_overrides={"COMMON_AGENT_INTEGRATION_MODE": "demo"},
            log_path=log_path,
        ) as base_url,
        authenticated_client(base_url=base_url, timeout=5) as client,
    ):
        health = client.get(
            "/api/v1/system/health",
            headers={"traceparent": traceparent},
        )
        invalid = client.post(
            "/api/v1/employees",
            headers={"traceparent": traceparent},
            json={
                "name": "",
                "description": secret_prompt,
                "system_prompt": secret_prompt,
                "api_key": secret_key,
            },
        )
        created = client.post(
            "/api/v1/conversations",
            json={
                "conversation_id": str(conversation_id),
                "employee_id": str(DEFAULT_KNOWLEDGE_ASSISTANT_ID),
                "title": "H7-06 可观测性会话",
            },
        )
        sent = client.post(
            f"/api/v1/conversations/{conversation_id}/messages",
            json={"message_id": str(uuid4()), "content": secret_prompt},
        )
        assistant_message_id = sent.json()["assistant_message"]["id"]
        turn_id = sent.json()["turn_id"]
        for _ in range(100):
            messages = client.get(f"/api/v1/conversations/{conversation_id}/messages")
            assistant = messages.json()[-1]
            if assistant["status"] in {"completed", "failed", "stopped"}:
                break
            time.sleep(0.02)
        else:
            raise AssertionError("demo conversation did not reach a terminal state")
        metrics = client.get("/api/v1/system/metrics")

    assert health.status_code == 200
    response_traceparent = health.headers["traceparent"]
    assert response_traceparent.startswith(f"00-{trace_id}-")
    assert response_traceparent != traceparent
    assert invalid.status_code == 422
    assert created.status_code == 201
    assert sent.status_code == 202
    assert assistant["status"] == "completed"
    assert metrics.status_code == 200
    snapshot = metrics.json()
    assert snapshot["requests_in_flight"] == 0
    assert snapshot["requests_total"] >= 2
    assert snapshot["responses_by_status"]["2xx"] >= 1
    assert snapshot["responses_by_status"]["4xx"] >= 1
    assert snapshot["errors_by_code"]["validation_error"] >= 1
    assert snapshot["latency_ms"]["count"] == snapshot["requests_total"]
    assert snapshot["latency_ms"]["total"] >= 0
    assert snapshot["latency_ms"]["maximum"] >= 0

    raw_logs = log_path.read_text(encoding="utf-8")
    records = [json.loads(line) for line in raw_logs.splitlines() if line.strip()]
    validation_record = next(
        record
        for record in records
        if record.get("event") == "http.request.completed"
        and record.get("error_code") == "validation_error"
    )
    assert validation_record["request_id"] == invalid.headers["X-Request-ID"]
    assert validation_record["trace_id"] == trace_id
    assert validation_record["method"] == "POST"
    assert validation_record["route"] == "/api/v1/employees"
    assert validation_record["status_code"] == 422
    assert validation_record["duration_ms"] >= 0
    assert validation_record["source"]
    conversation_record = next(
        record
        for record in records
        if record.get("event") == "conversation.turn.finished" and record.get("turn_id") == turn_id
    )
    assert conversation_record["conversation_id"] == str(conversation_id)
    assert conversation_record["message_id"] == assistant_message_id
    assert conversation_record["status"] == "completed"
    assert conversation_record["error_code"] is None
    assert conversation_record["duration_ms"] >= 0
    assert secret_key not in raw_logs
    assert secret_prompt not in raw_logs


async def _delete_conversation(conversation_id: UUID) -> None:
    database = Database(TEST_DATABASE_URL)
    await database.start()
    try:
        await delete_conversations(database, conversation_id)
    finally:
        await database.stop()
