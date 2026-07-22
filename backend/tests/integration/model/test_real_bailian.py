from __future__ import annotations

import asyncio
import os

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.tools import tool

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings
from common_agent.models.base import (
    ModelConfigurationInvalid,
    ModelMessage,
    ModelMessageRole,
    ModelRequest,
    ModelStreamDelta,
)


def test_real_bailian_stream_and_invalid_key_boundary() -> None:
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实百炼验收")

    asyncio.run(_exercise_real_bailian())


def test_real_deepseek_tool_chunks_and_non_streaming_compatibility() -> None:
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实百炼工具流兼容验收")

    asyncio.run(_exercise_real_deepseek_tool_compatibility())


async def _exercise_real_bailian() -> None:
    settings = ModelSettings.from_demo_file()
    adapter = BailianChatModelAdapter(settings)
    try:
        chunks = [
            event.text
            async for event in adapter.stream(
                ModelRequest(
                    messages=(
                        ModelMessage(
                            role=ModelMessageRole.SYSTEM,
                            content="严格遵循用户要求。只输出指定文本。",
                        ),
                        ModelMessage(
                            role=ModelMessageRole.USER,
                            content="只回复 COMMON_AGENT_A4_02_OK。不要添加其他内容。",
                        ),
                    )
                )
            )
            if isinstance(event, ModelStreamDelta)
        ]
    finally:
        await adapter.aclose()
    assert chunks
    assert "COMMON_AGENT_A4_02_OK" in "".join(chunks)

    invalid_settings = ModelSettings.from_mapping(
        {
            "BAILIAN_API_KEY": "sk-invalid-a4-02",
            "BAILIAN_BASE_URL": settings.base_url,
            "BAILIAN_MODEL": settings.model,
            "BAILIAN_TIMEOUT_SECONDS": "30",
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS": "30",
            "BAILIAN_MAX_RETRIES": "0",
        }
    )
    invalid_adapter = BailianChatModelAdapter(invalid_settings)
    try:
        with pytest.raises(ModelConfigurationInvalid) as captured:
            async for _ in invalid_adapter.stream(
                ModelRequest(
                    messages=(ModelMessage(role=ModelMessageRole.USER, content="测试无效 Key"),)
                )
            ):
                pass
    finally:
        await invalid_adapter.aclose()

    rendered = f"{captured.value!r}\n{captured.value}"
    assert "sk-invalid-a4-02" not in rendered
    assert settings.api_key.get_secret_value() not in rendered


async def _exercise_real_deepseek_tool_compatibility() -> None:
    @tool
    def current_time(utc_offset: str) -> str:
        """获取指定 UTC offset 的当前时间。"""

        return utc_offset

    async def collect(*, disable_streaming_for_tool_calls: bool) -> list[object]:
        settings = ModelSettings.from_demo_file().model_copy(
            update={"model": "deepseek-v4-pro"}
        )
        adapter = BailianChatModelAdapter(
            settings,
            disable_streaming_for_tool_calls=disable_streaming_for_tool_calls,
        )
        try:
            bound = adapter.langchain_chat_model.bind_tools([current_time])
            messages = [
                HumanMessage(
                    content=(
                        "必须调用 current_time 查询 +08:00 当前时间,"
                        "不要直接回答。"
                    )
                )
            ]
            events = (
                bound.astream(
                    messages,
                    extra_body={"enable_thinking": False},
                )
                if disable_streaming_for_tool_calls
                else bound.astream(
                    messages,
                    extra_body={"enable_thinking": False},
                    stream=True,
                )
            )
            return [
                chunk
                async for chunk in events
            ]
        finally:
            await adapter.aclose()

    streamed = await collect(disable_streaming_for_tool_calls=False)
    raw_tool_chunks = [
        tool_chunk
        for chunk in streamed
        if isinstance(chunk, AIMessageChunk)
        for tool_chunk in chunk.tool_call_chunks
    ]
    assert len(raw_tool_chunks) > 1
    assert raw_tool_chunks[0]["id"]
    assert raw_tool_chunks[0]["name"] == "current_time"
    assert any(
        tool_chunk["index"] == raw_tool_chunks[0]["index"]
        and not tool_chunk.get("id")
        and not tool_chunk.get("name")
        for tool_chunk in raw_tool_chunks[1:]
    )

    downgraded = await collect(disable_streaming_for_tool_calls=True)
    assert len(downgraded) == 1
    assert isinstance(downgraded[0], AIMessage)
    assert downgraded[0].tool_calls[0]["name"] == "current_time"
    assert downgraded[0].tool_calls[0]["id"]
