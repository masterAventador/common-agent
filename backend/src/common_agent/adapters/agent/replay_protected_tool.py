from __future__ import annotations

import asyncio
from typing import Any

from langchain_core.tools import StructuredTool
from pydantic import PrivateAttr


class ReplayProtectedStructuredTool(StructuredTool):
    """Coalesce duplicate provider tool-call IDs within one resolved agent turn."""

    _call_tasks: dict[str, asyncio.Task[Any]] = PrivateAttr(default_factory=dict)
    _call_tasks_lock: asyncio.Lock = PrivateAttr(default_factory=asyncio.Lock)

    async def arun(
        self,
        tool_input: str | dict[str, Any],
        *args: Any,
        tool_call_id: str | None = None,
        **kwargs: Any,
    ) -> Any:
        invoke = super().arun
        if tool_call_id is None:
            return await invoke(
                tool_input,
                *args,
                tool_call_id=tool_call_id,
                **kwargs,
            )
        async with self._call_tasks_lock:
            task = self._call_tasks.get(tool_call_id)
            if task is None:
                task = asyncio.create_task(
                    invoke(
                        tool_input,
                        *args,
                        tool_call_id=tool_call_id,
                        **kwargs,
                    ),
                    name=f"tool-{self.name}-{tool_call_id}",
                )
                self._call_tasks[tool_call_id] = task
        return await task


__all__ = ["ReplayProtectedStructuredTool"]
