from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Protocol, runtime_checkable


class ModelMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class ModelMessage:
    role: ModelMessageRole
    content: str

    def __post_init__(self) -> None:
        if not isinstance(self.role, ModelMessageRole):
            raise ValueError("模型消息角色无效")
        if not isinstance(self.content, str) or not self.content.strip():
            raise ValueError("模型消息正文不能为空")


@dataclass(frozen=True, slots=True)
class ModelRequest:
    messages: tuple[ModelMessage, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.messages, tuple) or not self.messages:
            raise ValueError("模型请求必须包含消息")
        if any(not isinstance(message, ModelMessage) for message in self.messages):
            raise ValueError("模型请求包含无效消息")


@dataclass(frozen=True, slots=True)
class ModelStreamDelta:
    text: str

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or not self.text:
            raise ValueError("模型增量不能为空")


@dataclass(frozen=True, slots=True)
class ModelStreamCompleted:
    pass


type ModelStreamEvent = ModelStreamDelta | ModelStreamCompleted


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

    def stream(self, request: ModelRequest) -> AsyncIterator[ModelStreamEvent]: ...

    def translate_error(
        self,
        error: Exception,
        *,
        stream_started: bool,
    ) -> ModelServiceError | None: ...

    async def aclose(self) -> None: ...
