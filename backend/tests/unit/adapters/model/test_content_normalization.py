from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from common_agent.adapters.model.bailian import BailianChatModelAdapter
from common_agent.bootstrap.settings import ModelSettings


def _settings() -> ModelSettings:
    return ModelSettings.from_mapping(
        {
            "BAILIAN_API_KEY": "sk-normalization-test",
            "BAILIAN_BASE_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "BAILIAN_MODEL": "qwen-long",
            "BAILIAN_TIMEOUT_SECONDS": "1",
            "BAILIAN_STREAM_CHUNK_TIMEOUT_SECONDS": "1",
            "BAILIAN_MAX_RETRIES": "0",
        }
    )


def test_payload_flattens_list_content_to_plain_string() -> None:
    """qwen-long 拒收数组 content。适配器必须在发送前拍平成纯字符串。"""
    adapter = BailianChatModelAdapter(_settings())
    chat_model = adapter.langchain_chat_model

    payload = chat_model._get_request_payload(  # type: ignore[attr-defined]
        [
            SystemMessage(
                content=[
                    {"type": "text", "text": "你是助手。"},
                    {"type": "text", "text": "遵守安全规范。"},
                ]
            ),
            HumanMessage(content="你好"),
        ]
    )

    contents = [message["content"] for message in payload["messages"]]
    assert all(isinstance(content, str) for content in contents), contents
    assert contents[0] == "你是助手。\n\n遵守安全规范。"
    assert contents[1] == "你好"


def test_payload_keeps_plain_string_content_unchanged() -> None:
    adapter = BailianChatModelAdapter(_settings())
    chat_model = adapter.langchain_chat_model

    payload = chat_model._get_request_payload(  # type: ignore[attr-defined]
        [
            SystemMessage(content="纯文本系统提示"),
            HumanMessage(content="问题"),
            AIMessage(content="回答"),
        ]
    )

    contents = [message["content"] for message in payload["messages"]]
    assert contents == ["纯文本系统提示", "问题", "回答"]
