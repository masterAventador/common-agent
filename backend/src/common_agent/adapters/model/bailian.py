from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx
import openai
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from common_agent.bootstrap.settings import ModelSettings
from common_agent.models.base import (
    ModelConfigurationInvalid,
    ModelMessageRole,
    ModelProviderResponseInvalid,
    ModelRequest,
    ModelRequestRejected,
    ModelServiceError,
    ModelServiceUnavailable,
    ModelStreamCompleted,
    ModelStreamDelta,
    ModelStreamEvent,
    ModelStreamInterrupted,
    ModelStreamReasoning,
)
from common_agent.observability import outbound_trace_headers

# 百炼 compatible-mode 在 delta/message 上放思考内容的字段名, 也是本项目挂回 LangChain
# additional_kwargs 时使用的键, 两侧保持同一个常量避免拼写漂移。
REASONING_CONTENT_KEY = "reasoning_content"


class BailianChatModelAdapter:
    provider_name = "bailian"

    def __init__(
        self,
        settings: ModelSettings,
        *,
        disable_streaming_for_tool_calls: bool = False,
        deep_thinking: bool | None = None,
        http_async_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_async_client = http_async_client is None
        self._closed = False
        active_async_client = (
            http_async_client
            if http_async_client is not None
            else httpx.AsyncClient(
                event_hooks={"request": [_inject_async_trace_context]},
            )
        )
        self._chat_model = _create_chat_model(
            settings,
            disable_streaming_for_tool_calls=disable_streaming_for_tool_calls,
            deep_thinking=deep_thinking,
            http_async_client=active_async_client,
            http_client=httpx.Client(event_hooks={"request": [_inject_trace_context]}),
        )

    @property
    def langchain_chat_model(self) -> BaseChatModel:
        return self._chat_model

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._chat_model.root_client is not None:
            self._chat_model.root_client.close()
        if self._owns_async_client and self._chat_model.root_async_client is not None:
            await self._chat_model.root_async_client.close()

    async def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]:
        emitted: list[str] = []
        try:
            async for chunk in self._chat_model.astream(
                _langchain_messages(request),
                extra_headers=outbound_trace_headers(),
                stream=True,
            ):
                reasoning = chunk.additional_kwargs.get(REASONING_CONTENT_KEY)
                if isinstance(reasoning, str) and reasoning:
                    yield ModelStreamReasoning(text=reasoning)
                text = _text_content(chunk.content)
                if text:
                    emitted.append(text)
                    yield ModelStreamDelta(text=text)
        except ModelServiceError:
            raise
        except Exception as error:
            translated = self.translate_error(error, stream_started=bool(emitted))
            raise (translated or ModelServiceUnavailable()) from None

        if not "".join(emitted).strip():
            raise ModelProviderResponseInvalid()
        yield ModelStreamCompleted()

    @staticmethod
    def translate_error(
        error: Exception,
        *,
        stream_started: bool,
    ) -> ModelServiceError | None:
        if isinstance(error, ModelServiceError):
            return error
        if stream_started:
            return ModelStreamInterrupted()
        return _known_model_error(error)


def _first_choice_delta(chunk: object) -> object:
    if not isinstance(chunk, dict):
        return None
    choices = chunk.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    return first.get("delta") if isinstance(first, dict) else None


def _first_choice_message(response: object) -> object:
    """从一次性响应里取第一个 choice 的 message。

    响应可能是 dict, 也可能是 OpenAI SDK 的 pydantic 模型, 因此两种访问方式都要支持。
    """
    choices = response.get("choices") if isinstance(response, dict) else getattr(
        response, "choices", None
    )
    if not isinstance(choices, list) or not choices:
        return None
    first = choices[0]
    return first.get("message") if isinstance(first, dict) else getattr(first, "message", None)


def _reasoning_text(container: object) -> str:
    if container is None:
        return ""
    raw = (
        container.get(REASONING_CONTENT_KEY)
        if isinstance(container, dict)
        else getattr(container, REASONING_CONTENT_KEY, None)
    )
    return raw if isinstance(raw, str) and raw else ""


def _text_content(content: object) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            text_parts.append(block)
        elif isinstance(block, dict) and block.get("type") in {"text", "text_delta"}:
            text = block.get("text")
            if isinstance(text, str):
                text_parts.append(text)
    return "".join(text_parts)


def _flatten_outbound_content(content: object) -> object:
    """把出站消息里的文本内容块拍平成纯字符串。

    百炼 compatible-mode 对 qwen-long 等模型要求 messages[].content 必须是纯字符串。
    它拒收 OpenAI 标准的数组内容块并报 Input should be a valid string。Deep Agents
    中间件会把系统消息组装成数组。因此在出站前统一拍平。平台不使用多模态输入且全部为文本。
    该规范化无损。仅含文本块时返回拼接字符串。出现非文本块则原样保留以免误伤未知场景。
    """
    if not isinstance(content, list):
        return content
    parts: list[str] = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict) and block.get("type") in {"text", "text_delta"}:
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
            else:
                return content
        else:
            return content
    return "\n\n".join(parts)


class _BailianChatOpenAI(ChatOpenAI):
    """百炼 compatible-mode 兼容层。

    出站消息内容块拍平成纯字符串; 入站补回被上游丢弃的思考内容。

    上游 `ChatOpenAI` 只对齐 OpenAI 官方响应规范, 其文档明确写着第三方供应商附加的
    `reasoning_content` 等字段"不会被提取或保留", 并指引"用供应商专用子类"补齐。百炼
    compatible-mode 恰好在流式 delta 与非流式 message 里返回 `reasoning_content`,
    因此在本项目自己的子类里通过公开扩展点取回, 不改动第三方源码。
    """

    def _get_request_payload(
        self, input_: Any, *, stop: Any = None, **kwargs: Any
    ) -> dict[str, Any]:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        messages = payload.get("messages")
        if isinstance(messages, list):
            for message in messages:
                if isinstance(message, dict) and "content" in message:
                    message["content"] = _flatten_outbound_content(message["content"])
        return payload

    def _convert_chunk_to_generation_chunk(
        self,
        chunk: dict[str, Any],
        default_chunk_class: type,
        base_generation_info: dict[str, Any] | None,
    ) -> Any:
        generation = super()._convert_chunk_to_generation_chunk(
            chunk, default_chunk_class, base_generation_info
        )
        if generation is None:
            return None
        reasoning = _reasoning_text(_first_choice_delta(chunk))
        if reasoning:
            generation.message.additional_kwargs[REASONING_CONTENT_KEY] = reasoning
        return generation

    def _create_chat_result(self, response: Any, generation_info: Any = None) -> Any:
        """非流式路径同样补回思考内容。

        绑定工具且标记流式不兼容的模型会走一次性响应, 此时 `reasoning_content` 挂在
        `choices[].message` 上而不是 delta 上。
        """
        result = super()._create_chat_result(response, generation_info)
        reasoning = _reasoning_text(_first_choice_message(response))
        if reasoning and result.generations:
            result.generations[0].message.additional_kwargs[REASONING_CONTENT_KEY] = reasoning
        return result


def _langchain_messages(request: ModelRequest) -> tuple[BaseMessage, ...]:
    messages: list[BaseMessage] = []
    for message in request.messages:
        if message.role is ModelMessageRole.SYSTEM:
            messages.append(SystemMessage(content=message.content))
        elif message.role is ModelMessageRole.USER:
            messages.append(HumanMessage(content=message.content))
        else:
            messages.append(AIMessage(content=message.content))
    return tuple(messages)


def _create_chat_model(
    settings: ModelSettings,
    *,
    disable_streaming_for_tool_calls: bool,
    deep_thinking: bool | None,
    http_async_client: httpx.AsyncClient,
    http_client: httpx.Client,
) -> ChatOpenAI:
    # 只有明确要求时才下发 enable_thinking。留空表示用模型自身默认行为, 避免撞上
    # 部分模型的参数限制(例如 MiniMax-M2.5 只接受 True, 传 False 直接 400)。
    #
    # 必须走 extra_body: 供应商自定义参数经 model_kwargs 会被当成 OpenAI SDK 的命名参数,
    # SDK 不认识就直接 TypeError, 整轮对话失败。
    extra_body: dict[str, Any] | None = (
        None if deep_thinking is None else {"enable_thinking": deep_thinking}
    )
    return _BailianChatOpenAI(
        extra_body=extra_body,
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        stream_chunk_timeout=settings.stream_chunk_timeout_seconds,
        max_retries=settings.max_retries,
        disable_streaming=(
            "tool_calling" if disable_streaming_for_tool_calls else False
        ),
        stream_usage=False,
        use_responses_api=False,
        http_client=http_client,
        http_async_client=http_async_client,
    )


def _inject_trace_context(request: httpx.Request) -> None:
    request.headers.update(outbound_trace_headers())


async def _inject_async_trace_context(request: httpx.Request) -> None:
    request.headers.update(outbound_trace_headers())


def _known_model_error(error: Exception) -> ModelServiceError | None:
    if isinstance(error, (openai.AuthenticationError, openai.PermissionDeniedError)):
        return ModelConfigurationInvalid()
    if isinstance(
        error,
        (
            openai.BadRequestError,
            openai.ConflictError,
            openai.NotFoundError,
            openai.UnprocessableEntityError,
        ),
    ):
        return ModelRequestRejected()
    if isinstance(
        error,
        (
            openai.APIConnectionError,
            openai.APITimeoutError,
            openai.InternalServerError,
            openai.RateLimitError,
        ),
    ):
        return ModelServiceUnavailable()
    if isinstance(error, openai.APIStatusError):
        if error.status_code == 429 or error.status_code >= 500:
            return ModelServiceUnavailable()
        return ModelRequestRejected()
    return None
