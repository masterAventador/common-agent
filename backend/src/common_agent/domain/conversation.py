from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from math import isfinite
from uuid import UUID, uuid4

CONVERSATION_TITLE_MAX_LENGTH = 200
MESSAGE_CONTENT_MAX_LENGTH = 200_000
MESSAGE_ERROR_CODE_MAX_LENGTH = 128
CITATION_REFERENCE_MAX_LENGTH = 128
CITATION_DOCUMENT_NAME_MAX_LENGTH = 512
CITATION_CONTENT_MAX_LENGTH = 12_000


class ConversationValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"会话字段 {field} {reason}")


class MessageTransitionError(ValueError):
    def __init__(self, status: MessageStatus, action: str) -> None:
        self.status = status
        self.action = action
        super().__init__(f"消息状态 {status.value} 不允许执行 {action}")


class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"


class MessageStatus(StrEnum):
    PENDING = "pending"
    STREAMING = "streaming"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


TERMINAL_MESSAGE_STATUSES = frozenset(
    {MessageStatus.COMPLETED, MessageStatus.FAILED, MessageStatus.STOPPED}
)


@dataclass(frozen=True, slots=True)
class Citation:
    position: int
    knowledge_base_id: str
    chunk_id: str
    document_id: str
    document_name: str
    content: str = field(repr=False)
    score: float

    def __post_init__(self) -> None:
        if (
            not isinstance(self.position, int)
            or isinstance(self.position, bool)
            or self.position < 1
        ):
            raise ConversationValidationError("position", "必须是正整数")
        knowledge_base_id = _required_text(
            "knowledge_base_id", self.knowledge_base_id, CITATION_REFERENCE_MAX_LENGTH
        )
        chunk_id = _required_text("chunk_id", self.chunk_id, CITATION_REFERENCE_MAX_LENGTH)
        document_id = _required_text("document_id", self.document_id, CITATION_REFERENCE_MAX_LENGTH)
        document_name = _required_text(
            "document_name", self.document_name, CITATION_DOCUMENT_NAME_MAX_LENGTH
        )
        content = _content(
            "content", self.content, required=True, max_length=CITATION_CONTENT_MAX_LENGTH
        )
        if (
            not isinstance(self.score, (int, float))
            or isinstance(self.score, bool)
            or not isfinite(self.score)
            or not 0 <= self.score <= 1
        ):
            raise ConversationValidationError("score", "必须是 0 到 1 之间的有限数值")

        object.__setattr__(self, "knowledge_base_id", knowledge_base_id)
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "document_name", document_name)
        object.__setattr__(self, "content", content)
        object.__setattr__(self, "score", float(self.score))


@dataclass(frozen=True, slots=True)
class Conversation:
    id: UUID
    employee_id: UUID
    title: str
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _uuid("id", self.id)
        _uuid("employee_id", self.employee_id)
        title = _required_text("title", self.title, CONVERSATION_TITLE_MAX_LENGTH)
        _utc_timestamp("created_at", self.created_at)
        _utc_timestamp("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ConversationValidationError("updated_at", "不能早于创建时间")
        object.__setattr__(self, "title", title)

    @classmethod
    def create(
        cls,
        *,
        employee_id: UUID,
        title: str,
        conversation_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Conversation:
        created_at = now or datetime.now(UTC)
        return cls(
            id=conversation_id or uuid4(),
            employee_id=employee_id,
            title=title,
            created_at=created_at,
            updated_at=created_at,
        )

    def rename(self, title: str, *, updated_at: datetime | None = None) -> Conversation:
        changed_at = updated_at or datetime.now(UTC)
        _utc_timestamp("updated_at", changed_at)
        if changed_at < self.updated_at:
            raise ConversationValidationError("updated_at", "不能早于当前更新时间")
        return replace(self, title=title, updated_at=changed_at)

    def touch(self, *, updated_at: datetime | None = None) -> Conversation:
        changed_at = updated_at or datetime.now(UTC)
        _utc_timestamp("updated_at", changed_at)
        if changed_at < self.updated_at:
            raise ConversationValidationError("updated_at", "不能早于当前更新时间")
        return replace(self, updated_at=changed_at)


@dataclass(frozen=True, slots=True)
class Message:
    id: UUID
    conversation_id: UUID
    sequence_number: int
    role: MessageRole
    content: str
    status: MessageStatus
    citations: tuple[Citation, ...]
    error_code: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _uuid("id", self.id)
        _uuid("conversation_id", self.conversation_id)
        if (
            not isinstance(self.sequence_number, int)
            or isinstance(self.sequence_number, bool)
            or self.sequence_number < 1
        ):
            raise ConversationValidationError("sequence_number", "必须是正整数")
        if not isinstance(self.role, MessageRole):
            raise ConversationValidationError("role", "不是支持的角色")
        if not isinstance(self.status, MessageStatus):
            raise ConversationValidationError("status", "不是支持的状态")
        content = _content(
            "content",
            self.content,
            required=self.role is MessageRole.USER or self.status is MessageStatus.COMPLETED,
            max_length=MESSAGE_CONTENT_MAX_LENGTH,
        )
        citations = _citations(self.citations)
        error_code = _optional_text("error_code", self.error_code, MESSAGE_ERROR_CODE_MAX_LENGTH)
        _utc_timestamp("created_at", self.created_at)
        _utc_timestamp("updated_at", self.updated_at)
        if self.updated_at < self.created_at:
            raise ConversationValidationError("updated_at", "不能早于创建时间")

        if self.role is MessageRole.USER:
            if self.status is not MessageStatus.COMPLETED:
                raise ConversationValidationError("status", "用户消息必须直接完成")
            if citations:
                raise ConversationValidationError("citations", "用户消息不能包含引用")
            if error_code is not None:
                raise ConversationValidationError("error_code", "用户消息不能包含错误码")
        else:
            _validate_assistant_state(self.status, content, citations, error_code)

        object.__setattr__(self, "content", content)
        object.__setattr__(self, "citations", citations)
        object.__setattr__(self, "error_code", error_code)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL_MESSAGE_STATUSES

    @classmethod
    def create_user(
        cls,
        *,
        conversation_id: UUID,
        sequence_number: int,
        content: str,
        message_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Message:
        created_at = now or datetime.now(UTC)
        return cls(
            id=message_id or uuid4(),
            conversation_id=conversation_id,
            sequence_number=sequence_number,
            role=MessageRole.USER,
            content=content,
            status=MessageStatus.COMPLETED,
            citations=(),
            error_code=None,
            created_at=created_at,
            updated_at=created_at,
        )

    @classmethod
    def create_assistant(
        cls,
        *,
        conversation_id: UUID,
        sequence_number: int,
        message_id: UUID | None = None,
        now: datetime | None = None,
    ) -> Message:
        created_at = now or datetime.now(UTC)
        return cls(
            id=message_id or uuid4(),
            conversation_id=conversation_id,
            sequence_number=sequence_number,
            role=MessageRole.ASSISTANT,
            content="",
            status=MessageStatus.PENDING,
            citations=(),
            error_code=None,
            created_at=created_at,
            updated_at=created_at,
        )

    def append_delta(self, delta: str, *, updated_at: datetime | None = None) -> Message:
        self._ensure_active("追加内容")
        delta_content = _content(
            "delta", delta, required=False, max_length=MESSAGE_CONTENT_MAX_LENGTH
        )
        if not delta_content:
            raise ConversationValidationError("delta", "不能为空")
        changed_at = _transition_timestamp(updated_at, self.updated_at, self.status)
        return replace(
            self,
            content=_content(
                "content",
                self.content + delta_content,
                required=False,
                max_length=MESSAGE_CONTENT_MAX_LENGTH,
            ),
            status=MessageStatus.STREAMING,
            updated_at=changed_at,
        )

    def complete(
        self,
        *,
        citations: Iterable[Citation] = (),
        updated_at: datetime | None = None,
    ) -> Message:
        self._ensure_active("完成")
        changed_at = _transition_timestamp(updated_at, self.updated_at, self.status)
        return replace(
            self,
            status=MessageStatus.COMPLETED,
            citations=tuple(citations),
            error_code=None,
            updated_at=changed_at,
        )

    def fail(self, *, error_code: str, updated_at: datetime | None = None) -> Message:
        self._ensure_active("失败")
        changed_at = _transition_timestamp(updated_at, self.updated_at, self.status)
        return replace(
            self,
            status=MessageStatus.FAILED,
            citations=(),
            error_code=error_code,
            updated_at=changed_at,
        )

    def stop(self, *, updated_at: datetime | None = None) -> Message:
        self._ensure_active("停止")
        changed_at = _transition_timestamp(updated_at, self.updated_at, self.status)
        return replace(
            self,
            status=MessageStatus.STOPPED,
            citations=(),
            error_code=None,
            updated_at=changed_at,
        )

    def retry(self, *, updated_at: datetime | None = None) -> Message:
        if self.role is not MessageRole.ASSISTANT or self.status not in {
            MessageStatus.FAILED,
            MessageStatus.STOPPED,
        }:
            raise MessageTransitionError(self.status, "重试")
        changed_at = _transition_timestamp(updated_at, self.updated_at, self.status)
        return replace(
            self,
            content="",
            status=MessageStatus.PENDING,
            citations=(),
            error_code=None,
            updated_at=changed_at,
        )

    def _ensure_active(self, action: str) -> None:
        if self.role is not MessageRole.ASSISTANT or self.status not in {
            MessageStatus.PENDING,
            MessageStatus.STREAMING,
        }:
            raise MessageTransitionError(self.status, action)


def _validate_assistant_state(
    status: MessageStatus,
    content: str,
    citations: tuple[Citation, ...],
    error_code: str | None,
) -> None:
    if status is MessageStatus.PENDING and content:
        raise ConversationValidationError("content", "待生成消息必须为空")
    if (
        status in {MessageStatus.PENDING, MessageStatus.STREAMING, MessageStatus.STOPPED}
        and citations
    ):
        raise ConversationValidationError("citations", "只有完成的助手消息可以包含引用")
    if status is MessageStatus.FAILED:
        if error_code is None:
            raise ConversationValidationError("error_code", "失败消息必须包含错误码")
        if citations:
            raise ConversationValidationError("citations", "失败消息不能包含引用")
    elif error_code is not None:
        raise ConversationValidationError("error_code", "只有失败消息可以包含错误码")


def _citations(values: Iterable[Citation]) -> tuple[Citation, ...]:
    result = tuple(values)
    if any(not isinstance(value, Citation) for value in result):
        raise ConversationValidationError("citations", "必须只包含 Citation")
    positions = tuple(value.position for value in result)
    if positions != tuple(range(1, len(result) + 1)):
        raise ConversationValidationError("citations", "position 必须从 1 连续递增")
    return result


def _uuid(field: str, value: object) -> UUID:
    if not isinstance(value, UUID):
        raise ConversationValidationError(field, "必须是 UUID")
    return value


def _required_text(field: str, value: object, max_length: int) -> str:
    if not isinstance(value, str):
        raise ConversationValidationError(field, "必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise ConversationValidationError(field, "不能为空")
    if len(normalized) > max_length:
        raise ConversationValidationError(field, f"不能超过 {max_length} 个字符")
    return normalized


def _optional_text(field: str, value: object | None, max_length: int) -> str | None:
    if value is None:
        return None
    return _required_text(field, value, max_length)


def _content(field: str, value: object, *, required: bool, max_length: int) -> str:
    if not isinstance(value, str):
        raise ConversationValidationError(field, "必须是字符串")
    if required and not value.strip():
        raise ConversationValidationError(field, "不能为空")
    if len(value) > max_length:
        raise ConversationValidationError(field, f"不能超过 {max_length} 个字符")
    return value


def _utc_timestamp(field: str, value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ConversationValidationError(field, "必须是时间")
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ConversationValidationError(field, "必须使用 UTC 时区")
    return value


def _transition_timestamp(
    value: datetime | None,
    previous: datetime,
    status: MessageStatus,
) -> datetime:
    changed_at = value or datetime.now(UTC)
    _utc_timestamp("updated_at", changed_at)
    if changed_at < previous:
        raise MessageTransitionError(status, "使用早于当前状态的时间")
    return changed_at
