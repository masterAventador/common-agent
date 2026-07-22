from __future__ import annotations

from common_agent.api.errors import AppError
from common_agent.conversations.contracts import (
    ConversationBusy,
    ConversationModelDisabled,
    ConversationNotFound,
    ConversationRequestConflict,
    GenerationNotActive,
    MessageNotFound,
    MessageRequestConflict,
    MessageRetryNotAllowed,
)
from common_agent.domain.conversation import ConversationValidationError
from common_agent.employees.service import EmployeeNotFound
from common_agent.model_configurations.service import ModelConfigurationNotFound
from common_agent.pagination import InvalidPageCursor
from common_agent.tools.models import ToolValidationError
from common_agent.tools.service import (
    ToolCapabilityUnavailable,
    ToolCollectionNotFound,
    ToolServiceError,
)


def conversation_error(error: Exception) -> AppError:
    if isinstance(
        error,
        (ConversationNotFound, MessageNotFound, EmployeeNotFound, ModelConfigurationNotFound),
    ):
        return AppError(error.code, str(error), 404, error.retryable)
    if isinstance(
        error,
        (
            ConversationBusy,
            ConversationRequestConflict,
            MessageRequestConflict,
            MessageRetryNotAllowed,
            GenerationNotActive,
            ConversationModelDisabled,
        ),
    ):
        return AppError(error.code, str(error), 409, error.retryable)
    if isinstance(error, ConversationValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, (ToolCollectionNotFound, ToolCapabilityUnavailable)):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, ToolValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, ToolServiceError):
        return AppError(error.code, error.message, 409, error.retryable)
    if isinstance(error, InvalidPageCursor):
        return AppError(error.code, error.message, 422, error.retryable)
    raise TypeError("unsupported conversation application error")


__all__ = ["conversation_error"]
