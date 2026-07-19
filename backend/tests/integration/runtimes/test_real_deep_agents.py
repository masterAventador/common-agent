from __future__ import annotations

import asyncio
import os

import pytest

from common_agent.adapters.agent.deep_agents import DeepAgentsEmployeeRuntime
from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings
from common_agent.runtimes.base import RuntimeEvent, RuntimeEventKind, RuntimeStopToken
from tests.support.runtime import runtime_request


def test_real_deep_agents_bailian_stream_failure_and_stop_boundaries() -> None:
    if os.environ.get("TEST_BAILIAN_REAL") != "1":
        pytest.skip("未显式启用真实 Deep Agents + 百炼验收")

    asyncio.run(_exercise_real_deep_agents())


async def _exercise_real_deep_agents() -> None:
    settings = ModelSettings.from_demo_file()
    runtime = DeepAgentsEmployeeRuntime(BailianChatModelAdapter(settings))
    try:
        events = [
            event
            async for event in runtime.stream(
                runtime_request(
                    system_instruction=(
                        "只根据知识片段回答当前问题。直接输出片段中的验收标记,不使用任何工具。"
                    )
                ),
                stop=RuntimeStopToken(),
            )
        ]
    finally:
        await runtime.aclose()

    _assert_successful_marker_stream(events)

    stop_runtime = DeepAgentsEmployeeRuntime(BailianChatModelAdapter(settings))
    stop = RuntimeStopToken()
    try:
        stopped_events: list[RuntimeEvent] = []
        async for event in stop_runtime.stream(
            runtime_request(
                knowledge_base_id=None,
                knowledge_context=(),
                system_instruction="直接从 1 数到 1000,每个数字用逗号分隔,不使用任何工具。",
            ),
            stop=stop,
        ):
            stopped_events.append(event)
            if event.kind is RuntimeEventKind.DELTA:
                stop.request_stop()
    finally:
        await stop_runtime.aclose()

    assert stopped_events[0].kind is RuntimeEventKind.DELTA
    assert stopped_events[-1].kind is RuntimeEventKind.STOPPED
    assert RuntimeEventKind.COMPLETED not in {event.kind for event in stopped_events}
    assert RuntimeEventKind.FAILED not in {event.kind for event in stopped_events}

    invalid_settings = ModelSettings.from_mapping(
        {
            "BAILIAN_API_KEY": "sk-invalid-a4-04",
            "BAILIAN_BASE_URL": settings.base_url,
            "BAILIAN_MODEL": settings.model,
            "BAILIAN_TIMEOUT_SECONDS": "30",
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS": "30",
            "BAILIAN_MAX_RETRIES": "0",
        }
    )
    invalid_runtime = DeepAgentsEmployeeRuntime(BailianChatModelAdapter(invalid_settings))
    try:
        invalid_events = [
            event
            async for event in invalid_runtime.stream(
                runtime_request(knowledge_base_id=None, knowledge_context=()),
                stop=RuntimeStopToken(),
            )
        ]
    finally:
        await invalid_runtime.aclose()

    assert len(invalid_events) == 1
    assert invalid_events[0].kind is RuntimeEventKind.FAILED
    assert invalid_events[0].error_code == "configuration_missing"
    rendered = repr(invalid_events)
    assert "sk-invalid-a4-04" not in rendered
    assert settings.api_key.get_secret_value() not in rendered


def _assert_successful_marker_stream(events: list[RuntimeEvent]) -> None:
    assert events
    assert events[-1].kind is RuntimeEventKind.COMPLETED
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert "COMMON_AGENT_A4_04_OK" in "".join(event.delta or "" for event in events)
