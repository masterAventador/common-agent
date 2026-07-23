from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest
from pydantic import SecretStr

from common_agent.adapters.model.verification import (
    BailianModelConfigurationVerifier,
    DemoModelConfigurationVerifier,
)
from common_agent.bootstrap.settings import ModelSettings
from common_agent.models.base import (
    ModelRequest,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamEvent,
)


def test_bailian_verifier_streams_probe_and_always_closes_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observed: dict[str, object] = {}

    class AdapterProbe:
        def __init__(self, settings: ModelSettings) -> None:
            observed["model"] = settings.model

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
            observed["prompt"] = request.messages[0].content
            yield ModelStreamDelta("连接")
            yield ModelStreamCompleted()
            yield ModelStreamDelta("成功")

        async def aclose(self) -> None:
            observed["closed"] = True

    monkeypatch.setattr(
        "common_agent.adapters.model.verification.BailianChatModelAdapter",
        AdapterProbe,
    )
    settings = ModelSettings(
        api_key=SecretStr("fixture-secret"),
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        model="old-model",
    )

    result = asyncio.run(BailianModelConfigurationVerifier(settings).verify("qwen-plus"))

    assert result == "连接成功"
    assert observed == {
        "model": "qwen-plus",
        "prompt": "请只回复：连接成功",  # noqa: RUF001
        "closed": True,
    }


def test_demo_verifier_returns_local_success_without_network() -> None:
    assert (
        asyncio.run(DemoModelConfigurationVerifier().verify("ignored"))
        == "演示模式模型连接正常"
    )
