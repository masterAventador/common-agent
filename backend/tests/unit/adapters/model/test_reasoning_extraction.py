from __future__ import annotations

from langchain_core.messages import AIMessageChunk, HumanMessage

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


def _extra_body(deep_thinking: bool | None) -> object:
    """取实际出站请求里的供应商自定义参数。

    必须断言 extra_body 而不是随便某个键: 供应商自定义参数如果经 model_kwargs 下发,
    会被当成 OpenAI SDK 的命名参数, SDK 不认识就直接 TypeError, 整轮对话失败。
    """
    adapter = BailianChatModelAdapter(_settings(), deep_thinking=deep_thinking)
    payload = adapter.langchain_chat_model._get_request_payload(  # type: ignore[attr-defined]
        [HumanMessage(content="你好")]
    )
    assert "enable_thinking" not in payload, "供应商自定义参数不能放在顶层"
    return payload.get("extra_body")


def test_deep_thinking_on_asks_the_provider_to_think() -> None:
    """开关打开时显式要求思考: qwen-plus 这类默认不思考的模型也会给出思考内容。"""
    assert _extra_body(True) == {"enable_thinking": True}


def test_deep_thinking_off_asks_the_provider_to_skip_thinking() -> None:
    assert _extra_body(False) == {"enable_thinking": False}


def test_unset_deep_thinking_leaves_the_provider_default_alone() -> None:
    """无法确定时不下发该参数, 用模型自身默认行为, 不去撞供应商的参数限制。"""
    assert _extra_body(None) is None
