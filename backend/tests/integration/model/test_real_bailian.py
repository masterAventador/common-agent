from __future__ import annotations

import asyncio
import os

import pytest
from langchain_core.messages import HumanMessage, SystemMessage

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings
from common_agent.models.base import ModelConfigurationInvalid


def test_real_bailian_stream_and_invalid_key_boundary() -> None:
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实百炼验收")

    asyncio.run(_exercise_real_bailian())


async def _exercise_real_bailian() -> None:
    settings = ModelSettings.from_demo_file()
    adapter = BailianChatModelAdapter(settings)
    try:
        chunks = [
            chunk
            async for chunk in adapter.stream_text(
                [
                    SystemMessage(content="严格遵循用户要求。只输出指定文本。"),
                    HumanMessage(content="只回复 COMMON_AGENT_A4_02_OK。不要添加其他内容。"),
                ]
            )
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
            async for _ in invalid_adapter.stream_text([HumanMessage(content="测试无效 Key")]):
                pass
    finally:
        await invalid_adapter.aclose()

    rendered = f"{captured.value!r}\n{captured.value}"
    assert "sk-invalid-a4-02" not in rendered
    assert settings.api_key.get_secret_value() not in rendered
