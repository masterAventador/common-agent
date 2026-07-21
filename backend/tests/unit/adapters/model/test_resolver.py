from __future__ import annotations

import asyncio

import pytest
from langchain_openai import ChatOpenAI

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
