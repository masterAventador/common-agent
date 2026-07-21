from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID


class EventStreamKind(StrEnum):
    CONVERSATION = "conversation"
    WORKFLOW = "workflow"


@dataclass(frozen=True, slots=True)
class EventAppendRequest:
    event_id: UUID
    tenant_id: UUID
    stream_kind: EventStreamKind
    stream_id: UUID
    event_key: str
    event_type: str
    payload: dict[str, object]
    occurred_at: datetime

    def __post_init__(self) -> None:
        _uuid("event_id", self.event_id)
        _uuid("tenant_id", self.tenant_id)
        _uuid("stream_id", self.stream_id)
        if not isinstance(self.stream_kind, EventStreamKind):
            raise ValueError("stream_kind must be EventStreamKind")
        _safe_text("event_key", self.event_key, maximum=191)
        _safe_text("event_type", self.event_type, maximum=64)
        _payload(self.payload)
        _utc("occurred_at", self.occurred_at)


@dataclass(frozen=True, slots=True)
class DurableEvent:
    request: EventAppendRequest
    sequence: int
    retention_until: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.request, EventAppendRequest):
            raise ValueError("request must be EventAppendRequest")
        if (
            not isinstance(self.sequence, int)
            or isinstance(self.sequence, bool)
            or self.sequence < 1
        ):
            raise ValueError("sequence must be a positive integer")
        _utc("retention_until", self.retention_until)
        if self.retention_until <= self.request.occurred_at:
            raise ValueError("retention_until must follow occurred_at")


class EventCapacityExceeded(RuntimeError):
    pass


class EventIdempotencyConflict(RuntimeError):
    pass


def _uuid(name: str, value: object) -> None:
    if not isinstance(value, UUID):
        raise ValueError(f"{name} must be UUID")


def _utc(name: str, value: object) -> None:
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() != UTC.utcoffset(None)
    ):
        raise ValueError(f"{name} must use UTC")


def _safe_text(name: str, value: object, *, maximum: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or len(value) > maximum
        or any(character in value for character in "\r\n\0")
    ):
        raise ValueError(f"{name} must be safe non-empty text")


def _payload(value: object) -> None:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ValueError("payload must be a JSON object")
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as error:
        raise ValueError("payload must contain JSON values") from error
    if len(encoded.encode("utf-8")) > 1_000_000:
        raise ValueError("payload exceeds 1000000 bytes")


__all__ = [
    "DurableEvent",
    "EventAppendRequest",
    "EventCapacityExceeded",
    "EventIdempotencyConflict",
    "EventStreamKind",
]
