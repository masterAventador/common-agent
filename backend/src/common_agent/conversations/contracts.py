from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from common_agent.domain.conversation import Conversation, Message
from common_agent.domain.employee import Employee
from common_agent.domain.model_configuration import ModelConfiguration
from common_agent.knowledge.retrieval import KnowledgeBoundSubject, ResolvedKnowledgeContext
from common_agent.tools.models import (
    ToolGrantSelection,
    ToolGrantSnapshot,
    ToolGrantTarget,
)

GENERIC_SYSTEM_INSTRUCTION = "你是通用 AI 助手,请准确、清晰地回答用户问题。"


class ConversationServiceError(Exception):
    code: str
    message: str
    retryable = False

    def __init__(self) -> None:
        super().__init__(self.message)


class ConversationNotFound(ConversationServiceError):
    code = "conversation_not_found"
    message = "会话不存在"


class ConversationBusy(ConversationServiceError):
    code = "conversation_busy"
    message = "当前会话正在生成回复"
    retryable = True


class ConversationRequestConflict(ConversationServiceError):
    code = "conversation_request_conflict"
    message = "会话请求发生冲突,请刷新后重试"
    retryable = True


class MessageNotFound(ConversationServiceError):
    code = "message_not_found"
    message = "消息不存在"


class MessageRequestConflict(ConversationServiceError):
    code = "message_request_conflict"
    message = "消息请求已经提交"


class MessageRetryNotAllowed(ConversationServiceError):
    code = "message_retry_not_allowed"
    message = "只有会话中最后一条失败或已停止的助手消息可以重试"


class GenerationNotActive(ConversationServiceError):
    code = "generation_not_active"
    message = "当前会话没有正在生成的回复"


class ConversationModelDisabled(ConversationServiceError):
    code = "conversation_model_disabled"
    message = "所选模型已停用,请选择当前已启用的模型"


@dataclass(frozen=True, slots=True)
class TurnAccepted:
    turn_id: UUID
    user_message: Message
    assistant_message: Message
    retry: bool


@dataclass(frozen=True, slots=True)
class ConversationTurnAccepted:
    conversation: Conversation
    turn: TurnAccepted


@dataclass(frozen=True, slots=True)
class ConversationHistoryItem:
    conversation: Conversation
    employee_name: str | None


@dataclass(frozen=True, slots=True)
class ConversationExecutionTarget:
    subject_id: UUID
    model_configuration_id: UUID
    model_identifier: str
    streaming_breaks_tool_calls: bool
    system_instruction: str
    knowledge_base_id: str | None
    allowed_workflow_ids: tuple[UUID, ...]
    allowed_tool_capability_ids: tuple[UUID, ...]
    tool_grant_target: ToolGrantTarget


@dataclass(frozen=True, slots=True)
class StopAccepted:
    turn_id: UUID
    assistant_message_id: UUID


class EmployeeDirectory(Protocol):
    async def get(self, employee_id: UUID) -> Employee: ...


class ModelConfigurationDirectory(Protocol):
    async def get(self, model_configuration_id: UUID) -> ModelConfiguration: ...


class ToolGrantDirectory(Protocol):
    async def employee_grants(self, employee_id: UUID) -> ToolGrantSnapshot: ...

    async def conversation_grants(self, conversation_id: UUID) -> ToolGrantSnapshot: ...

    async def prepare_conversation_grants(
        self,
        conversation_id: UUID,
        selection: ToolGrantSelection,
    ) -> ToolGrantSnapshot: ...


class KnowledgeResolver(Protocol):
    async def resolve(
        self,
        subject: KnowledgeBoundSubject,
        user_message: Message,
    ) -> ResolvedKnowledgeContext: ...


__all__ = [
    "GENERIC_SYSTEM_INSTRUCTION",
    "ConversationBusy",
    "ConversationExecutionTarget",
    "ConversationHistoryItem",
    "ConversationModelDisabled",
    "ConversationNotFound",
    "ConversationRequestConflict",
    "ConversationServiceError",
    "ConversationTurnAccepted",
    "EmployeeDirectory",
    "GenerationNotActive",
    "KnowledgeResolver",
    "MessageNotFound",
    "MessageRequestConflict",
    "MessageRetryNotAllowed",
    "ModelConfigurationDirectory",
    "StopAccepted",
    "ToolGrantDirectory",
    "TurnAccepted",
]
