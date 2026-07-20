from __future__ import annotations

import ast
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from common_agent.models.base import (
    ModelConfigurationInvalid,
    ModelMessage,
    ModelMessageRole,
    ModelProviderResponseInvalid,
    ModelRequest,
    ModelRequestRejected,
    ModelServiceUnavailable,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamEvent,
    ModelStreamInterrupted,
    TextStreamingModel,
)


def test_model_errors_expose_only_stable_safe_metadata() -> None:
    expected = [
        (ModelConfigurationInvalid(), "configuration_missing", False),
        (ModelRequestRejected(), "model_request_rejected", False),
        (ModelServiceUnavailable(), "model_unavailable", True),
        (ModelProviderResponseInvalid(), "model_response_invalid", False),
        (ModelStreamInterrupted(), "model_stream_interrupted", True),
    ]

    for error, code, retryable in expected:
        assert error.code == code
        assert error.retryable is retryable
        assert str(error) == error.message
        assert "upstream" not in repr(error).lower()


def test_platform_messages_requests_and_stream_events_are_strict() -> None:
    request = ModelRequest(
        messages=(
            ModelMessage(role=ModelMessageRole.SYSTEM, content="遵守平台规则"),
            ModelMessage(role=ModelMessageRole.USER, content="回答问题"),
        )
    )
    events: tuple[ModelStreamEvent, ...] = (
        ModelStreamDelta(text="回答"),
        ModelStreamCompleted(),
    )

    assert request.messages[0].role is ModelMessageRole.SYSTEM
    assert request.messages[1].content == "回答问题"
    assert events == (ModelStreamDelta(text="回答"), ModelStreamCompleted())

    with pytest.raises(ValueError):
        ModelMessage(role=ModelMessageRole.USER, content=" ")
    with pytest.raises(ValueError):
        ModelRequest(messages=())
    with pytest.raises(ValueError):
        ModelStreamDelta(text="")


def test_text_streaming_model_protocol_uses_only_platform_types() -> None:
    class ModelProbe:
        provider_name = "probe"

        async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
            assert request.messages
            yield ModelStreamDelta(text="完成")
            yield ModelStreamCompleted()

        def translate_error(
            self,
            error: Exception,
            *,
            stream_started: bool,
        ) -> None:
            del error, stream_started

        async def aclose(self) -> None:
            pass

    assert isinstance(ModelProbe(), TextStreamingModel)


def test_model_and_message_third_party_imports_stay_inside_adapters() -> None:
    source_root = Path(__file__).parents[3] / "src" / "common_agent"
    forbidden_roots = {"deepagents", "langchain", "langchain_core", "langchain_openai", "openai"}
    violations: list[str] = []
    for source_file in source_root.rglob("*.py"):
        if "adapters" in source_file.relative_to(source_root).parts:
            continue
        tree = ast.parse(source_file.read_text(encoding="utf-8"), filename=str(source_file))
        for node in ast.walk(tree):
            module = ""
            if isinstance(node, ast.Import):
                modules = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                modules = [node.module or ""]
            else:
                continue
            for module in modules:
                if module.split(".", 1)[0] in forbidden_roots:
                    violations.append(
                        f"{source_file.relative_to(source_root)}:{node.lineno}:{module}"
                    )

    assert violations == []
