from __future__ import annotations

from collections.abc import AsyncIterator

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
)


class BailianChatModelAdapter:
    provider_name = "bailian"

    def __init__(
        self,
        settings: ModelSettings,
        *,
        http_async_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_async_client = http_async_client is None
        self._closed = False
        active_async_client = (
            http_async_client if http_async_client is not None else httpx.AsyncClient()
        )
        self._chat_model = _create_chat_model(
            settings,
            http_async_client=active_async_client,
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
            async for chunk in self._chat_model.astream(_langchain_messages(request)):
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
    http_async_client: httpx.AsyncClient,
) -> ChatOpenAI:
    return ChatOpenAI(
        model=settings.model,
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=settings.timeout_seconds,
        stream_chunk_timeout=settings.stream_chunk_timeout_seconds,
        max_retries=settings.max_retries,
        streaming=True,
        stream_usage=False,
        use_responses_api=False,
        http_client=httpx.Client(),
        http_async_client=http_async_client,
    )


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
