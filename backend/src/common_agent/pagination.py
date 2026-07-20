from __future__ import annotations

import base64
import binascii
import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID

DEFAULT_PAGE_LIMIT = 20
MAX_PAGE_LIMIT = 100
MAX_PAGE_SEARCH_LENGTH = 128
MAX_PAGE_CURSOR_LENGTH = 1_024


class InvalidPageCursor(ValueError):
    code = "invalid_page_cursor"
    message = "分页游标无效或与当前筛选条件不匹配"
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


@dataclass(frozen=True, slots=True)
class PageAnchor:
    created_at: datetime
    id: str

    def __post_init__(self) -> None:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ValueError("分页锚点时间必须包含时区")
        if not 1 <= len(self.id) <= 128 or self.id != self.id.strip():
            raise ValueError("分页锚点 ID 不合法")


@dataclass(frozen=True, slots=True)
class ListPageRequest:
    limit: int = DEFAULT_PAGE_LIMIT
    search: str = ""
    cursor: str | None = None

    def __post_init__(self) -> None:
        normalized_search = self.search.strip()
        if not 1 <= self.limit <= MAX_PAGE_LIMIT:
            raise ValueError("分页条数不合法")
        if len(normalized_search) > MAX_PAGE_SEARCH_LENGTH:
            raise ValueError("分页搜索词过长")
        if self.cursor is not None and not 1 <= len(self.cursor) <= MAX_PAGE_CURSOR_LENGTH:
            raise InvalidPageCursor
        object.__setattr__(self, "search", normalized_search)


@dataclass(frozen=True, slots=True)
class PageSlice[PageItem]:
    items: tuple[PageItem, ...]
    has_more: bool

    def __post_init__(self) -> None:
        if self.has_more and not self.items:
            raise ValueError("存在下一页时当前页不能为空")


@dataclass(frozen=True, slots=True)
class CursorPage[PageItem]:
    items: tuple[PageItem, ...]
    next_cursor: str | None


def encode_keyset_cursor(
    *,
    scope: str,
    search: str,
    limit: int,
    anchor: PageAnchor,
) -> str:
    _validate_context(scope, limit)
    timestamp = int(anchor.created_at.astimezone(UTC).timestamp() * 1_000_000)
    return _encode(
        {
            "v": 1,
            "k": "keyset",
            "r": scope,
            "s": _search_fingerprint(search),
            "l": limit,
            "t": timestamp,
            "i": anchor.id,
        }
    )


def decode_keyset_cursor(
    cursor: str,
    *,
    scope: str,
    search: str,
    limit: int,
) -> PageAnchor:
    _validate_context(scope, limit)
    payload = _decode(cursor)
    if (
        set(payload) != {"v", "k", "r", "s", "l", "t", "i"}
        or payload.get("v") != 1
        or payload.get("k") != "keyset"
        or payload.get("r") != scope
        or payload.get("s") != _search_fingerprint(search)
        or payload.get("l") != limit
        or type(payload.get("t")) is not int
        or not isinstance(payload.get("i"), str)
    ):
        raise InvalidPageCursor
    try:
        created_at = datetime.fromtimestamp(payload["t"] / 1_000_000, tz=UTC)
        return PageAnchor(created_at=created_at, id=payload["i"])
    except (OverflowError, OSError, ValueError):
        raise InvalidPageCursor from None


def encode_offset_cursor(*, scope: str, search: str, limit: int, offset: int) -> str:
    _validate_context(scope, limit)
    if type(offset) is not int or offset < 0:
        raise ValueError("分页偏移不合法")
    return _encode(
        {
            "v": 1,
            "k": "offset",
            "r": scope,
            "s": _search_fingerprint(search),
            "l": limit,
            "o": offset,
        }
    )


def decode_offset_cursor(
    cursor: str,
    *,
    scope: str,
    search: str,
    limit: int,
) -> int:
    _validate_context(scope, limit)
    payload = _decode(cursor)
    if (
        set(payload) != {"v", "k", "r", "s", "l", "o"}
        or payload.get("v") != 1
        or payload.get("k") != "offset"
        or payload.get("r") != scope
        or payload.get("s") != _search_fingerprint(search)
        or payload.get("l") != limit
        or type(payload.get("o")) is not int
        or payload["o"] < 0
    ):
        raise InvalidPageCursor
    return cast(int, payload["o"])


def canonical_uuid_search(search: str) -> str | None:
    try:
        return str(UUID(search))
    except (AttributeError, ValueError):
        return None


def _validate_context(scope: str, limit: int) -> None:
    if not scope or len(scope) > 64 or not scope.replace("-", "").isalnum():
        raise ValueError("分页作用域不合法")
    if type(limit) is not int or not 1 <= limit <= MAX_PAGE_LIMIT:
        raise ValueError("分页条数不合法")


def _search_fingerprint(search: str) -> str:
    normalized = search.strip().casefold().encode("utf-8")
    return hashlib.sha256(normalized).hexdigest()[:16]


def _encode(payload: dict[str, Any]) -> str:
    payload_bytes = _canonical_json(payload)
    envelope = {
        "p": payload,
        "c": hashlib.sha256(b"common-agent-page-v1\0" + payload_bytes).hexdigest()[:16],
    }
    encoded = base64.urlsafe_b64encode(_canonical_json(envelope)).decode("ascii")
    return encoded.rstrip("=")


def _decode(cursor: str) -> dict[str, Any]:
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= MAX_PAGE_CURSOR_LENGTH:
        raise InvalidPageCursor
    try:
        padding = "=" * (-len(cursor) % 4)
        decoded = base64.b64decode(cursor + padding, altchars=b"-_", validate=True)
        envelope = json.loads(decoded)
    except (UnicodeDecodeError, ValueError, binascii.Error, json.JSONDecodeError):
        raise InvalidPageCursor from None
    if not isinstance(envelope, dict) or set(envelope) != {"p", "c"}:
        raise InvalidPageCursor
    payload = envelope.get("p")
    checksum = envelope.get("c")
    if not isinstance(payload, dict) or not isinstance(checksum, str):
        raise InvalidPageCursor
    expected = hashlib.sha256(b"common-agent-page-v1\0" + _canonical_json(payload)).hexdigest()[:16]
    if checksum != expected:
        raise InvalidPageCursor
    return payload


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


__all__ = [
    "DEFAULT_PAGE_LIMIT",
    "MAX_PAGE_CURSOR_LENGTH",
    "MAX_PAGE_LIMIT",
    "MAX_PAGE_SEARCH_LENGTH",
    "CursorPage",
    "InvalidPageCursor",
    "ListPageRequest",
    "PageAnchor",
    "PageSlice",
    "canonical_uuid_search",
    "decode_keyset_cursor",
    "decode_offset_cursor",
    "encode_keyset_cursor",
    "encode_offset_cursor",
]
