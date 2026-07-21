from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from common_agent.events import DurableEvent, EventAppendRequest, EventStreamKind

EVENT_ID = UUID("10000000-0000-0000-0000-000000000001")
TENANT_ID = UUID("20000000-0000-0000-0000-000000000001")
STREAM_ID = UUID("30000000-0000-0000-0000-000000000001")
NOW = datetime(2026, 7, 21, 7, 0, tzinfo=UTC)


def _request() -> EventAppendRequest:
    return EventAppendRequest(
        event_id=EVENT_ID,
        tenant_id=TENANT_ID,
        stream_kind=EventStreamKind.CONVERSATION,
        stream_id=STREAM_ID,
        event_key="assistant-message:completed",
        event_type="assistant.completed",
        payload={"version": 1},
        occurred_at=NOW,
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"event_id": str(EVENT_ID)}, "UUID"),
        ({"stream_kind": "conversation"}, "stream_kind"),
        ({"event_key": ""}, "event_key"),
        ({"event_key": " padded "}, "event_key"),
        ({"event_type": "line\nbreak"}, "event_type"),
        ({"payload": []}, "JSON object"),
        ({"payload": {1: "value"}}, "JSON object"),
        ({"payload": {"value": {1, 2}}}, "JSON values"),
        ({"payload": {"value": float("nan")}}, "JSON values"),
        ({"payload": {"value": "x" * 1_000_001}}, "exceeds"),
        ({"occurred_at": datetime(2026, 7, 21, 7, 0)}, "UTC"),
    ],
)
def test_event_append_request_rejects_unsafe_or_non_json_state(
    changes: dict[str, Any],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        replace(_request(), **changes)


@pytest.mark.parametrize(
    ("event_request", "sequence", "retention_until", "message"),
    [
        (object(), 1, NOW + timedelta(days=1), "request"),
        (_request(), True, NOW + timedelta(days=1), "sequence"),
        (_request(), 0, NOW + timedelta(days=1), "sequence"),
        (_request(), 1, datetime(2026, 7, 22, 7, 0), "UTC"),
        (_request(), 1, NOW, "retention_until"),
    ],
)
def test_durable_event_rejects_invalid_sequence_and_retention(
    event_request: object,
    sequence: object,
    retention_until: datetime,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        DurableEvent(
            request=cast(EventAppendRequest, event_request),
            sequence=cast(int, sequence),
            retention_until=retention_until,
        )
