from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from common_agent.observability.context import current_observation_context

_REDACTED = "[REDACTED]"
_REDACTED_EXCEPTION = "[REDACTED_EXCEPTION]"
_SENSITIVE_KEYS = frozenset(
    {
        "api_key",
        "authorization",
        "body",
        "content",
        "cookie",
        "document_text",
        "input",
        "knowledge_content",
        "output",
        "password",
        "prompt",
        "query",
        "request_body",
        "response",
        "secret",
        "system_instruction",
        "token",
        "upstream_response",
    }
)
_SECRET_TEXT_PATTERNS = (
    re.compile(r"(?i)\bsk-[a-z0-9_-]+"),
    re.compile(
        r"(?i)\b(api[_-]?key|authorization|token|password|secret)"
        r"\s*[:=]\s*(?:bearer\s+)?([^\s&,;]+)"
    ),
    re.compile(r"(?i)(https?://[^:/\s]+:)[^@/\s]+@"),
)
_TRACEBACK_EXCEPTION_PATTERN = re.compile(
    r"(?:^|\n)(?:[A-Za-z_][A-Za-z0-9_]*\.)*"
    r"(?P<type>[A-Za-z_][A-Za-z0-9_]*(?:Error|Exception))"
    r"(?::[^\n]*)?\s*$"
)


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": getattr(record, "event_name", "log"),
            "source": f"{record.module}:{record.lineno}",
        }
        context = current_observation_context()
        if context is not None:
            payload.update(context.log_fields())

        inferred_exception_type: str | None = None
        fields = getattr(record, "structured_fields", None)
        if isinstance(fields, Mapping):
            payload.update(_sanitize_mapping(fields))
        elif record.getMessage():
            message, inferred_exception_type = _sanitize_log_message(record.getMessage())
            payload["message"] = message

        if record.exc_info and record.exc_info[0] is not None:
            payload["exception_type"] = record.exc_info[0].__name__
        elif inferred_exception_type is not None:
            payload["exception_type"] = inferred_exception_type
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def configure_json_logging(*, level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonLogFormatter())
    for logger_name in ("", "common_agent", "uvicorn", "uvicorn.error", "alembic"):
        logger = logging.getLogger(logger_name)
        logger.handlers = [handler]
        logger.setLevel(level)
        logger.propagate = False
    logging.getLogger("uvicorn.access").disabled = True


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: bool = False,
    **fields: object,
) -> None:
    """记录结构化事件。

    未预期异常请传 exc_info=True 以保留堆栈: JSON 输出本身不含 traceback,
    但 record.exc_info 仍是排查未预期失败的关键依据。
    """
    normalized_event = event.strip()
    if not normalized_event or len(normalized_event) > 128:
        raise ValueError("log event must be a non-empty stable name")
    logger.log(
        level,
        normalized_event,
        # 必须传 None 而非 False: logging 会把 False 原样写进 record.exc_info,
        # 使格式化器的 record.exc_info[0] 取下标失败。
        exc_info=exc_info or None,
        extra={
            "event_name": normalized_event,
            "structured_fields": fields,
        },
    )


def _sanitize_mapping(value: Mapping[object, object]) -> dict[str, object]:
    sanitized: dict[str, object] = {}
    for raw_key, raw_value in list(value.items())[:50]:
        key = str(raw_key)[:128]
        if _sensitive_key(key):
            sanitized[key] = _REDACTED
        else:
            sanitized[key] = _sanitize_value(raw_value)
    return sanitized


def _sanitize_value(value: object) -> object:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _sanitize_text(value[:1024])
    if isinstance(value, Mapping):
        return _sanitize_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_sanitize_value(item) for item in value[:20]]
    return f"<{type(value).__name__}>"


def _sensitive_key(key: str) -> bool:
    normalized = key.strip().lower().replace("-", "_")
    return (
        normalized in _SENSITIVE_KEYS
        or normalized.endswith("_content")
        or normalized.endswith("_prompt")
        or normalized.endswith("_password")
        or normalized.endswith("_secret")
        or normalized.endswith("_token")
        or normalized.endswith("_response")
    )


def _sanitize_text(value: str) -> str:
    sanitized = value
    for pattern in _SECRET_TEXT_PATTERNS:
        if pattern.pattern.startswith("(?i)(https"):
            sanitized = pattern.sub(r"\1[REDACTED]@", sanitized)
        elif "api[_-]?key" in pattern.pattern:
            sanitized = pattern.sub(r"\1=[REDACTED]", sanitized)
        else:
            sanitized = pattern.sub(_REDACTED, sanitized)
    return sanitized


def _sanitize_log_message(value: str) -> tuple[str, str | None]:
    if "\n" not in value and "Traceback (most recent call last)" not in value:
        return _sanitize_text(value), None
    match = _TRACEBACK_EXCEPTION_PATTERN.search(value)
    exception_type = match.group("type") if match is not None else None
    return _REDACTED_EXCEPTION, exception_type
