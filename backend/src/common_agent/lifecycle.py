from __future__ import annotations

from collections.abc import Awaitable, Callable

type AsyncCleanup = Callable[[], Awaitable[None]]


async def run_cleanups(*cleanups: AsyncCleanup) -> None:
    errors: list[Exception] = []
    for cleanup in cleanups:
        try:
            await cleanup()
        except Exception as error:
            errors.append(error)

    if len(errors) == 1:
        raise errors[0]
    if errors:
        raise ExceptionGroup("应用资源关闭失败", errors)


__all__ = ["AsyncCleanup", "run_cleanups"]
