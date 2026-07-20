from __future__ import annotations

import re
import secrets
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, replace
from uuid import UUID

_TRACEPARENT_PATTERN = re.compile(
    r"^00-(?P<trace_id>[0-9a-f]{32})-(?P<span_id>[0-9a-f]{16})-(?P<flags>[0-9a-f]{2})$"
)


@dataclass(frozen=True, slots=True)
class CorrelationContext:
    trace_id: str
    span_id: str
    trace_flags: str = "01"
    parent_span_id: str | None = None
    request_id: str | None = None
    conversation_id: str | None = None
    message_id: str | None = None
    turn_id: str | None = None
    workflow_id: str | None = None
    run_id: str | None = None

    @property
    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"

    def log_fields(self) -> dict[str, str]:
        fields = {
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_span_id": self.parent_span_id,
            "request_id": self.request_id,
            "conversation_id": self.conversation_id,
            "message_id": self.message_id,
            "turn_id": self.turn_id,
            "workflow_id": self.workflow_id,
            "run_id": self.run_id,
        }
        return {key: value for key, value in fields.items() if value is not None}


_CURRENT_CONTEXT: ContextVar[CorrelationContext | None] = ContextVar(
    "common_agent_observation_context",
    default=None,
)


def current_observation_context() -> CorrelationContext | None:
    return _CURRENT_CONTEXT.get()


@contextmanager
def bind_observation_context(
    *,
    request_id: str | None = None,
    traceparent: str | None = None,
    conversation_id: UUID | str | None = None,
    message_id: UUID | str | None = None,
    turn_id: UUID | str | None = None,
    workflow_id: UUID | str | None = None,
    run_id: UUID | str | None = None,
) -> Iterator[CorrelationContext]:
    current = current_observation_context()
    if current is None:
        trace_id, parent_span_id, trace_flags = _trace_from_parent(traceparent)
        current = CorrelationContext(
            trace_id=trace_id,
            span_id=_new_hex(8),
            trace_flags=trace_flags,
            parent_span_id=parent_span_id,
        )

    updated = replace(
        current,
        request_id=_value(request_id, current.request_id),
        conversation_id=_value(conversation_id, current.conversation_id),
        message_id=_value(message_id, current.message_id),
        turn_id=_value(turn_id, current.turn_id),
        workflow_id=_value(workflow_id, current.workflow_id),
        run_id=_value(run_id, current.run_id),
    )
    token = _CURRENT_CONTEXT.set(updated)
    try:
        yield updated
    finally:
        _CURRENT_CONTEXT.reset(token)


def outbound_trace_headers() -> dict[str, str]:
    context = current_observation_context()
    if context is None:
        return {}
    headers = {
        "traceparent": (f"00-{context.trace_id}-{_new_hex(8)}-{context.trace_flags}"),
    }
    if context.request_id is not None:
        headers["X-Request-ID"] = context.request_id
    return headers


def _trace_from_parent(traceparent: str | None) -> tuple[str, str | None, str]:
    if traceparent is not None:
        match = _TRACEPARENT_PATTERN.fullmatch(traceparent.strip().lower())
        if match is not None:
            trace_id = match.group("trace_id")
            span_id = match.group("span_id")
            if trace_id != "0" * 32 and span_id != "0" * 16:
                return trace_id, span_id, match.group("flags")
    return _new_hex(16), None, "01"


def _new_hex(byte_count: int) -> str:
    while True:
        value = secrets.token_hex(byte_count)
        if set(value) != {"0"}:
            return value


def _value(value: UUID | str | None, existing: str | None) -> str | None:
    if value is None:
        return existing
    normalized = str(value).strip()
    if not normalized:
        raise ValueError("correlation values must not be blank")
    if len(normalized) > 128:
        raise ValueError("correlation values are too long")
    return normalized
