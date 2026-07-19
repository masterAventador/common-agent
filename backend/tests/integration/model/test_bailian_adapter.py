from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator

import httpx
import pytest
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings
from common_agent.models.base import (
    ModelConfigurationInvalid,
    ModelProviderResponseInvalid,
    ModelRequestRejected,
    ModelServiceUnavailable,
    ModelStreamInterrupted,
)

_TEST_SECRET = "sk-a4-02-must-not-leak"


def _settings(
    *,
    max_retries: str = "2",
    timeout: str = "1",
    stream_timeout: str | None = None,
) -> ModelSettings:
    return ModelSettings.from_mapping(
        {
            "BAILIAN_API_KEY": _TEST_SECRET,
            "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "BAILIAN_MODEL": "qwen-plus",
            "BAILIAN_TIMEOUT_SECONDS": timeout,
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS": stream_timeout or timeout,
            "BAILIAN_MAX_RETRIES": max_retries,
        }
    )


def _sse(*contents: str) -> httpx.Response:
    events = []
    for content in contents:
        events.append(
            "data: "
            + json.dumps(
                {
                    "id": "chatcmpl-a4-02",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": "qwen-plus",
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": content},
                            "finish_reason": None,
                        }
                    ],
                }
            )
            + "\n\n"
        )
    events.append(
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-a4-02",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "qwen-plus",
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


def _delta_event(content: str) -> bytes:
    return (
        "data: "
        + json.dumps(
            {
                "id": "chatcmpl-a4-02",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "qwen-plus",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": content},
                        "finish_reason": None,
                    }
                ],
            }
        )
        + "\n\n"
    ).encode()


def test_adapter_uses_chat_openai_and_streams_incremental_text() -> None:
    requests: list[httpx.Request] = []

    def respond(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return _sse("通", "过")

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(_settings(), http_async_client=client)
            assert isinstance(adapter.chat_model, ChatOpenAI)
            assert adapter.chat_model.model_name == "qwen-plus"
            assert adapter.chat_model.max_retries == 2
            assert adapter.chat_model.request_timeout == 1
            assert adapter.chat_model.stream_chunk_timeout == 1
            assert adapter.chat_model.stream_usage is False

            chunks = [
                chunk
                async for chunk in adapter.stream_text(
                    [SystemMessage(content="简洁回答"), HumanMessage(content="测试")]
                )
            ]
            assert chunks == ["通", "过"]

    asyncio.run(exercise())

    assert len(requests) == 1
    assert requests[0].url.path == "/compatible-mode/v1/chat/completions"
    assert requests[0].headers["authorization"] == f"Bearer {_TEST_SECRET}"
    payload = json.loads(requests[0].content)
    assert payload["stream"] is True
    assert payload["model"] == "qwen-plus"
    assert payload["messages"] == [
        {"role": "system", "content": "简洁回答"},
        {"role": "user", "content": "测试"},
    ]


def test_adapter_retries_only_to_configured_limit_before_success() -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            return httpx.Response(503, json={"message": "sensitive upstream body"})
        return _sse("恢复")

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(_settings(max_retries="2"), http_async_client=client)
            assert (
                "".join(
                    [
                        chunk
                        async for chunk in adapter.stream_text([HumanMessage(content="测试重试")])
                    ]
                )
                == "恢复"
            )

    asyncio.run(exercise())
    assert attempts == 3


@pytest.mark.parametrize("status_code", [429, 503])
def test_adapter_stops_retrying_and_redacts_exhausted_transient_errors(
    status_code: int,
) -> None:
    attempts = 0
    provider_detail = "exhausted-provider-detail"

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(status_code, json={"message": provider_detail})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(_settings(max_retries="1"), http_async_client=client)
            with pytest.raises(ModelServiceUnavailable) as captured:
                async for _ in adapter.stream_text([HumanMessage(content="耗尽重试")]):
                    pass
            assert provider_detail not in str(captured.value)

    asyncio.run(exercise())
    assert attempts == 2


def test_adapter_does_not_retry_a_rejected_request() -> None:
    attempts = 0

    def respond(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(400, json={"message": "rejected-provider-detail"})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(_settings(max_retries="2"), http_async_client=client)
            with pytest.raises(ModelRequestRejected):
                async for _ in adapter.stream_text([HumanMessage(content="非法请求")]):
                    pass

    asyncio.run(exercise())
    assert attempts == 1


def test_adapter_maps_authentication_failure_without_leaking_provider_details() -> None:
    provider_detail = "provider-secret-auth-detail"

    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": provider_detail})

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(_settings(max_retries="0"), http_async_client=client)
            try:
                async for _ in adapter.stream_text([HumanMessage(content="认证失败")]):
                    pass
            except ModelConfigurationInvalid as error:
                rendered = f"{error!r}\n{error}"
                assert provider_detail not in rendered
                assert _TEST_SECRET not in rendered
                assert error.__suppress_context__ is True
            else:
                raise AssertionError("认证失败必须转换为安全平台错误")

    asyncio.run(exercise())


def test_adapter_maps_timeout_to_retryable_safe_error() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout detail must not leak", request=request)

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(_settings(max_retries="0"), http_async_client=client)
            try:
                async for _ in adapter.stream_text([HumanMessage(content="超时")]):
                    pass
            except ModelServiceUnavailable as error:
                assert error.retryable is True
                assert "timeout detail" not in str(error)
            else:
                raise AssertionError("超时必须转换为可重试平台错误")

    asyncio.run(exercise())


class _InterruptedStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield _delta_event("部分")
        raise httpx.ReadError("stream detail must not leak")


class _SlowStream(httpx.AsyncByteStream):
    async def __aiter__(self) -> AsyncIterator[bytes]:
        await asyncio.sleep(0.05)
        yield _delta_event("迟到")


def test_adapter_marks_failure_after_first_delta_as_stream_interrupted() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_InterruptedStream(),
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(_settings(max_retries="0"), http_async_client=client)
            emitted: list[str] = []
            try:
                async for chunk in adapter.stream_text([HumanMessage(content="断流")]):
                    emitted.append(chunk)
            except ModelStreamInterrupted as error:
                assert emitted == ["部分"]
                assert "stream detail" not in str(error)
            else:
                raise AssertionError("首个增量后的连接失败必须标记为流中断")

    asyncio.run(exercise())


def test_adapter_applies_per_chunk_timeout_to_an_open_stream() -> None:
    def respond(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            stream=_SlowStream(),
        )

    async def exercise() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = BailianChatModelAdapter(
                _settings(max_retries="0", stream_timeout="0.01"),
                http_async_client=client,
            )
            with pytest.raises(ModelServiceUnavailable):
                async for _ in adapter.stream_text([HumanMessage(content="逐块超时")]):
                    pass

    asyncio.run(exercise())


def test_adapter_rejects_an_empty_successful_stream() -> None:
    async def exercise() -> None:
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: _sse())
        ) as client:
            adapter = BailianChatModelAdapter(_settings(max_retries="0"), http_async_client=client)
            try:
                async for _ in adapter.stream_text([HumanMessage(content="空输出")]):
                    pass
            except ModelProviderResponseInvalid as error:
                assert error.retryable is False
            else:
                raise AssertionError("空成功流必须作为非法上游响应处理")

    asyncio.run(exercise())


def test_adapter_explicitly_closes_owned_sync_and_async_clients() -> None:
    async def exercise() -> None:
        adapter = BailianChatModelAdapter(_settings())
        model = adapter.chat_model
        assert isinstance(model, ChatOpenAI)
        assert model.root_client is not None
        assert model.root_async_client is not None
        assert model.root_client.is_closed() is False
        assert model.root_async_client.is_closed() is False

        await adapter.aclose()
        await adapter.aclose()

        assert model.root_client.is_closed() is True
        assert model.root_async_client.is_closed() is True

    asyncio.run(exercise())


def test_owned_clients_are_isolated_between_adapter_instances() -> None:
    async def exercise() -> None:
        first = BailianChatModelAdapter(_settings())
        second = BailianChatModelAdapter(_settings())
        first_model = first.chat_model
        second_model = second.chat_model
        assert isinstance(first_model, ChatOpenAI)
        assert isinstance(second_model, ChatOpenAI)
        assert first_model.root_client is not None
        assert first_model.root_async_client is not None
        assert second_model.root_client is not None
        assert second_model.root_async_client is not None

        await first.aclose()

        assert first_model.root_client.is_closed() is True
        assert first_model.root_async_client.is_closed() is True
        assert second_model.root_client.is_closed() is False
        assert second_model.root_async_client.is_closed() is False

        await second.aclose()

    asyncio.run(exercise())
