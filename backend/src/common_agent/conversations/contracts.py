from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

from common_agent.domain.conversation import Message
from common_agent.domain.employee import Employee
from common_agent.knowledge.retrieval import ResolvedKnowledgeContext


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


@dataclass(frozen=True, slots=True)
class TurnAccepted:
    turn_id: UUID
    user_message: Message
    assistant_message: Message
    retry: bool


@dataclass(frozen=True, slots=True)
class StopAccepted:
    turn_id: UUID
    assistant_message_id: UUID


class EmployeeDirectory(Protocol):
    async def get(self, employee_id: UUID) -> Employee: ...


class KnowledgeResolver(Protocol):
    async def resolve(
        self,
        employee: Employee,
        user_message: Message,
    ) -> ResolvedKnowledgeContext: ...


__all__ = [
    "ConversationBusy",
    "ConversationNotFound",
    "ConversationRequestConflict",
    "ConversationServiceError",
    "EmployeeDirectory",
    "GenerationNotActive",
    "KnowledgeResolver",
    "MessageNotFound",
    "MessageRequestConflict",
    "MessageRetryNotAllowed",
    "StopAccepted",
    "TurnAccepted",
]
