from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

import pytest

from common_agent.lifecycle import run_cleanups


def test_run_cleanups_continues_after_failures_and_reports_all_errors() -> None:
    calls: list[str] = []

    def cleanup(name: str, *, error: Exception | None = None) -> Callable[[], Awaitable[None]]:
        async def run() -> None:
            calls.append(name)
            if error is not None:
                raise error

        return run

    first_error = RuntimeError("workflow close failed")
    second_error = ValueError("event broker close failed")

    with pytest.raises(ExceptionGroup) as captured:
        asyncio.run(
            run_cleanups(
                cleanup("workflows", error=first_error),
                cleanup("conversations"),
                cleanup("events", error=second_error),
                cleanup("database"),
            )
        )

    assert calls == ["workflows", "conversations", "events", "database"]
    assert captured.value.exceptions == (first_error, second_error)


def test_run_cleanups_preserves_a_single_failure() -> None:
    error = RuntimeError("database close failed")

    async def fail() -> None:
        raise error

    with pytest.raises(RuntimeError) as captured:
        asyncio.run(run_cleanups(fail))

    assert captured.value is error
