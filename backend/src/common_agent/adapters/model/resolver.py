from __future__ import annotations

import asyncio

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.adapters.model.langchain import LangChainChatModelProvider
from common_agent.bootstrap.settings import ModelSettings
from common_agent.lifecycle import run_cleanups


class BailianChatModelResolver:
    def __init__(
        self,
        settings: ModelSettings,
        *,
        initial_model: BailianChatModelAdapter | None = None,
    ) -> None:
        self._settings = settings
        self._models: dict[tuple[str, bool], BailianChatModelAdapter] = {}
        if initial_model is not None:
            self._models[(settings.model, False)] = initial_model
        self._lock = asyncio.Lock()
        self._closed = False

    async def resolve(
        self,
        model_identifier: str,
        *,
        disable_streaming_for_tool_calls: bool = False,
    ) -> LangChainChatModelProvider:
        async with self._lock:
            if self._closed:
                raise RuntimeError("百炼模型解析器已经关闭")
            key = (model_identifier, disable_streaming_for_tool_calls)
            existing = self._models.get(key)
            if existing is not None:
                return existing
            created = BailianChatModelAdapter(
                self._settings.model_copy(update={"model": model_identifier}),
                disable_streaming_for_tool_calls=disable_streaming_for_tool_calls,
            )
            self._models[key] = created
            return created

    async def aclose(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            models = tuple(self._models.values())
            self._models.clear()
        await run_cleanups(*(model.aclose for model in models))


__all__ = ["BailianChatModelResolver"]
