from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings
from common_agent.models.base import (
    ModelMessage,
    ModelMessageRole,
    ModelProviderResponseInvalid,
    ModelRequest,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamReasoning,
)


def _settings() -> ModelSettings:
    return ModelSettings.from_mapping(
        {
            "BAILIAN_API_KEY": "sk-reasoning-stream",
            "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "BAILIAN_MODEL": "qwen3.7-plus",
            "BAILIAN_TIMEOUT_SECONDS": "5",
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS": "5",
            "BAILIAN_MAX_RETRIES": "0",
        }
    )


def _request() -> ModelRequest:
    return ModelRequest(
        messages=(ModelMessage(role=ModelMessageRole.USER, content="3 和 7 哪个大"),)
    )


def _sse(*deltas: dict[str, str]) -> httpx.Response:
    events = [
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-reasoning",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "qwen3.7-plus",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
        )
        + "\n\n"
        for delta in deltas
    ]
    events.append(
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-reasoning",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "qwen3.7-plus",
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
            }
        )
        + "\n\ndata: [DONE]\n\n"
    )
    return httpx.Response(
        200,
        headers={"content-type": "text/event-stream"},
        content="".join(events).encode(),
    )


def _collect(response: httpx.Response) -> list[object]:
    async def exercise() -> list[object]:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: response)
        ) as client:
            adapter = BailianChatModelAdapter(_settings(), http_async_client=client)
            return [event async for event in adapter.stream(_request())]

    return asyncio.run(exercise())


def test_stream_emits_reasoning_before_the_answer() -> None:
    """思考内容要按到达顺序单独产出, 不能混进正文增量。"""
    events = _collect(
        _sse(
            {"reasoning_content": "先比较"},
            {"reasoning_content": "大小"},
            {"content": "7"},
            {"content": " 更大"},
        )
    )

    assert events == [
        ModelStreamReasoning(text="先比较"),
        ModelStreamReasoning(text="大小"),
        ModelStreamDelta(text="7"),
        ModelStreamDelta(text=" 更大"),
        ModelStreamCompleted(),
    ]


def test_stream_keeps_interleaved_order_within_one_chunk() -> None:
    events = _collect(_sse({"reasoning_content": "想", "content": "7"}))

    assert events == [
        ModelStreamReasoning(text="想"),
        ModelStreamDelta(text="7"),
        ModelStreamCompleted(),
    ]


def test_reasoning_only_response_is_still_an_empty_answer() -> None:
    """只有思考没有正文时仍然算空回复, 不能因为有思考就当成功。"""
    with pytest.raises(ModelProviderResponseInvalid):
        _collect(_sse({"reasoning_content": "想了很久"}))


def test_model_without_reasoning_emits_no_reasoning_events() -> None:
    events = _collect(_sse({"content": "7"}))

    assert events == [ModelStreamDelta(text="7"), ModelStreamCompleted()]
