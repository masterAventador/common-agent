from __future__ import annotations

import asyncio
from typing import cast

import pytest
from langchain_openai import ChatOpenAI

import common_agent.adapters.model.resolver as resolver_module
from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.adapters.model.resolver import BailianChatModelResolver
from common_agent.bootstrap.settings import ModelSettings


def _settings() -> ModelSettings:
    return ModelSettings.from_mapping(
        {
            "BAILIAN_API_KEY": "safe-unit-test-key",
            "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "BAILIAN_MODEL": "qwen-plus",
        }
    )


def test_bailian_model_resolver_caches_each_identifier_and_closes_as_one_resource() -> None:
    async def exercise() -> None:
        resolver = BailianChatModelResolver(_settings())

        first = await resolver.resolve("qwen-plus")
        repeated = await resolver.resolve("qwen-plus")
        other = await resolver.resolve("qwen-turbo")

        assert repeated is first
        assert other is not first
        assert isinstance(first.langchain_chat_model, ChatOpenAI)
        assert isinstance(other.langchain_chat_model, ChatOpenAI)
        assert first.langchain_chat_model.model_name == "qwen-plus"
        assert other.langchain_chat_model.model_name == "qwen-turbo"

        await resolver.aclose()
        await resolver.aclose()
        with pytest.raises(RuntimeError, match="已经关闭"):
            await resolver.resolve("qwen-plus")

    asyncio.run(exercise())


def test_bailian_model_resolver_isolates_tool_streaming_compatibility_variants() -> None:
    async def exercise() -> None:
        resolver = BailianChatModelResolver(_settings())

        streaming = await resolver.resolve("deepseek-v4-pro")
        downgraded = await resolver.resolve(
            "deepseek-v4-pro",
            disable_streaming_for_tool_calls=True,
        )
        repeated = await resolver.resolve(
            "deepseek-v4-pro",
            disable_streaming_for_tool_calls=True,
        )

        assert streaming is not downgraded
        assert repeated is downgraded
        assert streaming.langchain_chat_model.disable_streaming is False
        assert downgraded.langchain_chat_model.disable_streaming == "tool_calling"

        await resolver.aclose()

    asyncio.run(exercise())


def test_bailian_model_resolver_finishes_all_closes_when_one_model_close_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ClosingModel:
        def __init__(self, *, error: Exception | None = None) -> None:
            self.error = error
            self.closed = False

        async def aclose(self) -> None:
            if self.error is not None:
                self.closed = True
                raise self.error
            await asyncio.sleep(0.05)
            self.closed = True

    first_error = RuntimeError("first model close failed")
    first = ClosingModel(error=first_error)
    second = ClosingModel()
    monkeypatch.setattr(
        resolver_module,
        "BailianChatModelAdapter",
        lambda _, **kwargs: second,
    )

    async def exercise() -> None:
        resolver = BailianChatModelResolver(
            _settings(),
            initial_model=cast(BailianChatModelAdapter, first),
        )
        await resolver.resolve("qwen-turbo")

        with pytest.raises(RuntimeError) as captured:
            await resolver.aclose()

        assert captured.value is first_error
        assert first.closed is True
        assert second.closed is True

    asyncio.run(exercise())
