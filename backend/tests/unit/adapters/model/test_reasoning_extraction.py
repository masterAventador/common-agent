from __future__ import annotations

from langchain_core.messages import AIMessageChunk

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings


def _settings() -> ModelSettings:
    return ModelSettings.from_mapping(
        {
            "BAILIAN_API_KEY": "sk-reasoning-test",
            "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "BAILIAN_MODEL": "qwen3.7-plus",
            "BAILIAN_TIMEOUT_SECONDS": "1",
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS": "1",
            "BAILIAN_MAX_RETRIES": "0",
        }
    )


def _convert(chunk: dict[str, object]) -> AIMessageChunk | None:
    """走适配器实际使用的那个 chat model 做 chunk 转换。"""
    adapter = BailianChatModelAdapter(_settings())
    generation = adapter.langchain_chat_model._convert_chunk_to_generation_chunk(  # type: ignore[attr-defined]
        chunk,
        AIMessageChunk,
        None,
    )
    return None if generation is None else generation.message  # type: ignore[return-value]


def test_reasoning_delta_is_preserved_on_the_chunk() -> None:
    """上游 ChatOpenAI 明确丢弃 reasoning_content, 本项目的子类必须把它取回来。

    百炼 compatible-mode 端点实测会在 delta 里返回 reasoning_content(qwen3.7-plus、
    deepseek-v4-pro、glm-5.2 默认返回, qwen-plus 需要 enable_thinking)。
    """
    message = _convert(
        {
            "id": "chunk-1",
            "choices": [
                {
                    "index": 0,
                    "delta": {"role": "assistant", "reasoning_content": "先比较大小。"},
                    "finish_reason": None,
                }
            ],
        }
    )

    assert message is not None
    assert message.additional_kwargs.get("reasoning_content") == "先比较大小。"
    assert message.content == ""


def test_reasoning_and_content_can_arrive_in_the_same_chunk() -> None:
    message = _convert(
        {
            "id": "chunk-2",
            "choices": [
                {
                    "index": 0,
                    "delta": {"reasoning_content": "还在想", "content": "7"},
                    "finish_reason": None,
                }
            ],
        }
    )

    assert message is not None
    assert message.additional_kwargs.get("reasoning_content") == "还在想"
    assert message.content == "7"


def test_chunk_without_reasoning_keeps_additional_kwargs_clean() -> None:
    """没有思考内容的模型不能凭空多出一个空字段。"""
    message = _convert(
        {
            "id": "chunk-3",
            "choices": [{"index": 0, "delta": {"content": "7"}, "finish_reason": None}],
        }
    )

    assert message is not None
    assert "reasoning_content" not in message.additional_kwargs
    assert message.content == "7"


def test_blank_reasoning_is_ignored() -> None:
    message = _convert(
        {
            "id": "chunk-4",
            "choices": [
                {"index": 0, "delta": {"reasoning_content": "", "content": "7"}}
            ],
        }
    )

    assert message is not None
    assert "reasoning_content" not in message.additional_kwargs


def test_usage_only_chunk_stays_untouched() -> None:
    """收尾的 usage chunk 没有 choices, 不能因为改造而报错或凭空造字段。"""
    message = _convert({"id": "chunk-5", "choices": [], "usage": {"total_tokens": 7}})

    assert message is not None
    assert "reasoning_content" not in message.additional_kwargs
