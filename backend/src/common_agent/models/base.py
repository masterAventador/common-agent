from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from typing import ClassVar, Protocol, runtime_checkable

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage


class ModelServiceError(Exception):
    code: ClassVar[str]
    message: ClassVar[str]
    retryable: ClassVar[bool]

    def __init__(self) -> None:
        super().__init__(self.message)


class ModelConfigurationInvalid(ModelServiceError):
    code = "configuration_missing"
    message = "模型服务配置缺失或无效"
    retryable = False


class ModelRequestRejected(ModelServiceError):
    code = "model_request_rejected"
    message = "模型服务拒绝了请求"
    retryable = False


class ModelServiceUnavailable(ModelServiceError):
    code = "model_unavailable"
    message = "模型服务暂时不可用"
    retryable = True


class ModelProviderResponseInvalid(ModelServiceError):
    code = "model_response_invalid"
    message = "模型服务返回了无法识别的数据"
    retryable = False


class ModelStreamInterrupted(ModelServiceError):
    code = "model_stream_interrupted"
    message = "模型回复流意外中断"
    retryable = True


@runtime_checkable
class TextStreamingModel(Protocol):
    @property
    def provider_name(self) -> str: ...

    def stream_text(self, messages: Sequence[BaseMessage]) -> AsyncIterator[str]: ...

    def translate_error(
        self,
        error: Exception,
        *,
        stream_started: bool,
    ) -> ModelServiceError | None: ...

    async def aclose(self) -> None: ...


@runtime_checkable
class StreamingChatModel(TextStreamingModel, Protocol):
    @property
    def chat_model(self) -> BaseChatModel: ...
