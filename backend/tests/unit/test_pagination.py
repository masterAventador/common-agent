from __future__ import annotations

from datetime import UTC, datetime

import pytest

from common_agent.pagination import (
    InvalidPageCursor,
    PageAnchor,
    canonical_uuid_search,
    decode_keyset_cursor,
    decode_offset_cursor,
    encode_keyset_cursor,
    encode_offset_cursor,
)


def test_uuid_search_only_accepts_complete_uuid_values() -> None:
    assert (
        canonical_uuid_search("00000000-0000-0000-0000-000000000123")
        == "00000000-0000-0000-0000-000000000123"
    )
    assert canonical_uuid_search("00000000") is None
    assert canonical_uuid_search("名称前缀") is None


def test_keyset_cursor_round_trips_and_is_bound_to_scope_filter_and_limit() -> None:
    anchor = PageAnchor(
        created_at=datetime(2026, 7, 21, 1, 2, 3, 456789, tzinfo=UTC),
        id="00000000-0000-0000-0000-000000000123",
    )

    cursor = encode_keyset_cursor(
        scope="employees",
        search="知识 助理",
        limit=20,
        anchor=anchor,
    )

    assert (
        decode_keyset_cursor(
            cursor,
            scope="employees",
            search="知识 助理",
            limit=20,
        )
        == anchor
    )
    with pytest.raises(InvalidPageCursor):
        decode_keyset_cursor(
            cursor,
            scope="workflows",
            search="知识 助理",
            limit=20,
        )
    with pytest.raises(InvalidPageCursor):
        decode_keyset_cursor(
            cursor,
            scope="employees",
            search="别的筛选",
            limit=20,
        )
    with pytest.raises(InvalidPageCursor):
        decode_keyset_cursor(
            cursor,
            scope="employees",
            search="知识 助理",
            limit=50,
        )


def test_offset_cursor_round_trips_and_rejects_malformed_or_tampered_values() -> None:
    cursor = encode_offset_cursor(
        scope="knowledge-bases",
        search="产品",
        limit=25,
        offset=50,
    )

    assert (
        decode_offset_cursor(
            cursor,
            scope="knowledge-bases",
            search="产品",
            limit=25,
        )
        == 50
    )
    for invalid in ("", "not-base64", cursor[:-1] + ("A" if cursor[-1] != "A" else "B")):
        with pytest.raises(InvalidPageCursor):
            decode_offset_cursor(
                invalid,
                scope="knowledge-bases",
                search="产品",
                limit=25,
            )
