from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from itertools import pairwise
from math import isfinite
from typing import Protocol, runtime_checkable
from uuid import UUID

from common_agent.domain.conversation import (
    CITATION_CONTENT_MAX_LENGTH,
    CITATION_DOCUMENT_NAME_MAX_LENGTH,
    CITATION_REFERENCE_MAX_LENGTH,
    MESSAGE_CONTENT_MAX_LENGTH,
    MESSAGE_ERROR_CODE_MAX_LENGTH,
    MessageRole,
)
from common_agent.domain.employee import EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH
from common_agent.domain.model_configuration import (
    ModelConfigurationValidationError,
    normalize_model_identifier,
)
from common_agent.tools.models import ToolGrantTarget

RUNTIME_HISTORY_MAX_MESSAGES = 100
RUNTIME_HISTORY_MAX_CHARACTERS = 400_000
RUNTIME_KNOWLEDGE_MAX_CHUNKS = 20
RUNTIME_KNOWLEDGE_MAX_CHARACTERS = 120_000
RUNTIME_ALLOWED_WORKFLOWS_MAX_ITEMS = 100


class RuntimeValidationError(ValueError):
    def __init__(self, field: str, reason: str) -> None:
        self.field = field
        self.reason = reason
        super().__init__(f"运行时字段 {field} {reason}")


class RuntimeEventTransitionError(ValueError):
    def __init__(self, terminal_kind: RuntimeEventKind) -> None:
        self.terminal_kind = terminal_kind
        super().__init__(f"运行时事件已经进入 {terminal_kind.value} 终态")


@dataclass(frozen=True, slots=True)
class RuntimeConversationMessage:
    message_id: UUID
    sequence_number: int
    role: MessageRole
    content: str = field(repr=False)

    def __post_init__(self) -> None:
        _uuid("message_id", self.message_id)
        _positive_integer("sequence_number", self.sequence_number)
        if not isinstance(self.role, MessageRole):
            raise RuntimeValidationError("role", "不是支持的会话角色")
        _content("content", self.content, MESSAGE_CONTENT_MAX_LENGTH)


@dataclass(frozen=True, slots=True)
class RuntimeKnowledgeChunk:
    knowledge_base_id: str
    chunk_id: str
    document_id: str
    document_name: str
    content: str = field(repr=False)
    score: float

    def __post_init__(self) -> None:
        knowledge_base_id = _required_text(
            "knowledge_base_id", self.knowledge_base_id, CITATION_REFERENCE_MAX_LENGTH
        )
        chunk_id = _required_text("chunk_id", self.chunk_id, CITATION_REFERENCE_MAX_LENGTH)
        document_id = _required_text("document_id", self.document_id, CITATION_REFERENCE_MAX_LENGTH)
        document_name = _required_text(
            "document_name", self.document_name, CITATION_DOCUMENT_NAME_MAX_LENGTH
        )
        _content("content", self.content, CITATION_CONTENT_MAX_LENGTH)
        if (
            not isinstance(self.score, (int, float))
            or isinstance(self.score, bool)
            or not isfinite(self.score)
            or not 0 <= self.score <= 1
        ):
            raise RuntimeValidationError("score", "必须是 0 到 1 之间的有限数值")

        object.__setattr__(self, "knowledge_base_id", knowledge_base_id)
        object.__setattr__(self, "chunk_id", chunk_id)
        object.__setattr__(self, "document_id", document_id)
        object.__setattr__(self, "document_name", document_name)
        object.__setattr__(self, "score", float(self.score))


@dataclass(frozen=True, slots=True)
class EmployeeRuntimeRequest:
    conversation_id: UUID
    employee_id: UUID
    assistant_message_id: UUID
    assistant_sequence_number: int
    model_identifier: str
    system_instruction: str = field(repr=False)
    history: tuple[RuntimeConversationMessage, ...] = field(repr=False)
    knowledge_base_id: str | None
    knowledge_context: tuple[RuntimeKnowledgeChunk, ...] = field(repr=False)
    allowed_workflow_ids: tuple[UUID, ...]
    streaming_breaks_tool_calls: bool = False
    allowed_tool_capability_ids: tuple[UUID, ...] = ()
    tool_grant_target: ToolGrantTarget | None = None
    workflow_run_id: UUID | None = None

    def __post_init__(self) -> None:
        _uuid("conversation_id", self.conversation_id)
        _uuid("employee_id", self.employee_id)
        _uuid("assistant_message_id", self.assistant_message_id)
        _positive_integer("assistant_sequence_number", self.assistant_sequence_number)
        try:
            model_identifier = normalize_model_identifier(self.model_identifier)
        except ModelConfigurationValidationError as error:
            raise RuntimeValidationError("model_identifier", error.reason) from error
        system_instruction = _required_text(
            "system_instruction",
            self.system_instruction,
            EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH,
        )
        history = _history(self.history)
        if history[-1].role is not MessageRole.USER:
            raise RuntimeValidationError("history", "最后一条必须是当前用户消息")
        if self.assistant_sequence_number != history[-1].sequence_number + 1:
            raise RuntimeValidationError("assistant_sequence_number", "必须紧跟当前用户消息")
        if self.assistant_message_id in {message.message_id for message in history}:
            raise RuntimeValidationError("assistant_message_id", "不能与历史消息重复")

        knowledge_base_id = _optional_reference("knowledge_base_id", self.knowledge_base_id)
        knowledge_context = _knowledge_context(
            self.knowledge_context,
            knowledge_base_id=knowledge_base_id,
        )
        workflow_ids = _workflow_ids(self.allowed_workflow_ids)
        if not isinstance(self.streaming_breaks_tool_calls, bool):
            raise RuntimeValidationError(
                "streaming_breaks_tool_calls",
                "必须是布尔值",
            )
        capability_ids = _capability_ids(self.allowed_tool_capability_ids)
        if capability_ids and self.tool_grant_target is None:
            raise RuntimeValidationError(
                "tool_grant_target",
                "存在工具能力时不能为空",
            )
        if self.tool_grant_target is not None and not isinstance(
            self.tool_grant_target, ToolGrantTarget
        ):
            raise RuntimeValidationError("tool_grant_target", "不是支持的工具授权目标")
        if self.workflow_run_id is not None:
            _uuid("workflow_run_id", self.workflow_run_id)

        object.__setattr__(self, "system_instruction", system_instruction)
        object.__setattr__(self, "model_identifier", model_identifier)
        object.__setattr__(self, "history", history)
        object.__setattr__(self, "knowledge_base_id", knowledge_base_id)
        object.__setattr__(self, "knowledge_context", knowledge_context)
        object.__setattr__(self, "allowed_workflow_ids", workflow_ids)
        object.__setattr__(self, "allowed_tool_capability_ids", capability_ids)


class RuntimeEventKind(StrEnum):
    DELTA = "delta"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    TOOL_FAILED = "tool_failed"
    COMPLETED = "completed"
    FAILED = "failed"
    STOPPED = "stopped"


TERMINAL_RUNTIME_EVENT_KINDS = frozenset(
    {RuntimeEventKind.COMPLETED, RuntimeEventKind.FAILED, RuntimeEventKind.STOPPED}
)


@dataclass(frozen=True, slots=True)
class RuntimeEvent:
    assistant_message_id: UUID
    sequence: int
    kind: RuntimeEventKind
    delta: str | None = field(default=None, repr=False)
    error_code: str | None = None
    tool_call_id: UUID | None = None
    capability_id: UUID | None = None
    capability_name: str | None = None

    def __post_init__(self) -> None:
        _uuid("assistant_message_id", self.assistant_message_id)
        _positive_integer("sequence", self.sequence)
        if not isinstance(self.kind, RuntimeEventKind):
            raise RuntimeValidationError("kind", "不是支持的事件类型")

        if self.kind is RuntimeEventKind.DELTA:
            if self.delta is None:
                raise RuntimeValidationError("delta", "增量事件必须包含文本")
            _content("delta", self.delta, MESSAGE_CONTENT_MAX_LENGTH)
            if self.error_code is not None:
                raise RuntimeValidationError("error_code", "增量事件不能包含错误码")
            self._reject_tool_metadata()
            return

        if self.kind in {
            RuntimeEventKind.TOOL_STARTED,
            RuntimeEventKind.TOOL_COMPLETED,
            RuntimeEventKind.TOOL_FAILED,
        }:
            if self.delta is not None:
                raise RuntimeValidationError("delta", "工具事件不能包含文本增量")
            _uuid("tool_call_id", self.tool_call_id)
            _uuid("capability_id", self.capability_id)
            _required_text("capability_name", self.capability_name, 128)
            if self.kind is RuntimeEventKind.TOOL_FAILED:
                _required_text("error_code", self.error_code, MESSAGE_ERROR_CODE_MAX_LENGTH)
            elif self.error_code is not None:
                raise RuntimeValidationError("error_code", "只有失败工具事件可以包含错误码")
            return

        if self.delta is not None:
            raise RuntimeValidationError("delta", "终态事件不能包含文本增量")
        self._reject_tool_metadata()
        if self.kind is RuntimeEventKind.FAILED:
            _required_text("error_code", self.error_code, MESSAGE_ERROR_CODE_MAX_LENGTH)
        elif self.error_code is not None:
            raise RuntimeValidationError("error_code", "只有失败事件可以包含错误码")

    def _reject_tool_metadata(self) -> None:
        if any(
            value is not None
            for value in (self.tool_call_id, self.capability_id, self.capability_name)
        ):
            raise RuntimeValidationError("tool_call_id", "只有工具事件可以包含工具元数据")


class RuntimeEventEmitter:
    def __init__(self, assistant_message_id: UUID) -> None:
        self._assistant_message_id = _uuid("assistant_message_id", assistant_message_id)
        self._next_sequence = 1
        self._terminal_kind: RuntimeEventKind | None = None

    @property
    def is_terminal(self) -> bool:
        return self._terminal_kind is not None

    def delta(self, content: str) -> RuntimeEvent:
        return self._emit(RuntimeEventKind.DELTA, delta=content)

    def tool_started(
        self,
        *,
        tool_call_id: UUID,
        capability_id: UUID,
        capability_name: str,
    ) -> RuntimeEvent:
        return self._emit(
            RuntimeEventKind.TOOL_STARTED,
            tool_call_id=tool_call_id,
            capability_id=capability_id,
            capability_name=capability_name,
        )

    def tool_completed(
        self,
        *,
        tool_call_id: UUID,
        capability_id: UUID,
        capability_name: str,
    ) -> RuntimeEvent:
        return self._emit(
            RuntimeEventKind.TOOL_COMPLETED,
            tool_call_id=tool_call_id,
            capability_id=capability_id,
            capability_name=capability_name,
        )

    def tool_failed(
        self,
        *,
        tool_call_id: UUID,
        capability_id: UUID,
        capability_name: str,
        error_code: str,
    ) -> RuntimeEvent:
        return self._emit(
            RuntimeEventKind.TOOL_FAILED,
            error_code=error_code,
            tool_call_id=tool_call_id,
            capability_id=capability_id,
            capability_name=capability_name,
        )

    def complete(self) -> RuntimeEvent:
        return self._emit(RuntimeEventKind.COMPLETED)

    def fail(self, error_code: str) -> RuntimeEvent:
        return self._emit(RuntimeEventKind.FAILED, error_code=error_code)

    def stop(self) -> RuntimeEvent:
        return self._emit(RuntimeEventKind.STOPPED)

    def _emit(
        self,
        kind: RuntimeEventKind,
        *,
        delta: str | None = None,
        error_code: str | None = None,
        tool_call_id: UUID | None = None,
        capability_id: UUID | None = None,
        capability_name: str | None = None,
    ) -> RuntimeEvent:
        if self._terminal_kind is not None:
            raise RuntimeEventTransitionError(self._terminal_kind)
        event = RuntimeEvent(
            assistant_message_id=self._assistant_message_id,
            sequence=self._next_sequence,
            kind=kind,
            delta=delta,
            error_code=error_code,
            tool_call_id=tool_call_id,
            capability_id=capability_id,
            capability_name=capability_name,
        )
        self._next_sequence += 1
        if kind in TERMINAL_RUNTIME_EVENT_KINDS:
            self._terminal_kind = kind
        return event


@runtime_checkable
class RuntimeStopSignal(Protocol):
    @property
    def is_requested(self) -> bool: ...

    async def wait(self) -> None: ...


class RuntimeStopToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    @property
    def is_requested(self) -> bool:
        return self._event.is_set()

    def request_stop(self) -> bool:
        if self._event.is_set():
            return False
        self._event.set()
        return True

    async def wait(self) -> None:
        await self._event.wait()


@runtime_checkable
class EmployeeRuntime(Protocol):
    def stream(
        self,
        request: EmployeeRuntimeRequest,
        *,
        stop: RuntimeStopSignal,
    ) -> AsyncIterator[RuntimeEvent]: ...

    async def aclose(self) -> None: ...


def _history(
    values: Iterable[RuntimeConversationMessage],
) -> tuple[RuntimeConversationMessage, ...]:
    result = tuple(values)
    if not result:
        raise RuntimeValidationError("history", "不能为空")
    if len(result) > RUNTIME_HISTORY_MAX_MESSAGES:
        raise RuntimeValidationError("history", f"不能超过 {RUNTIME_HISTORY_MAX_MESSAGES} 条消息")
    if any(not isinstance(value, RuntimeConversationMessage) for value in result):
        raise RuntimeValidationError("history", "必须只包含 RuntimeConversationMessage")
    sequences = tuple(message.sequence_number for message in result)
    if any(current <= previous for previous, current in pairwise(sequences)):
        raise RuntimeValidationError("history", "消息序号必须严格递增")
    message_ids = tuple(message.message_id for message in result)
    if len(set(message_ids)) != len(message_ids):
        raise RuntimeValidationError("history", "不能包含重复消息")
    if sum(len(message.content) for message in result) > RUNTIME_HISTORY_MAX_CHARACTERS:
        raise RuntimeValidationError(
            "history", f"总内容不能超过 {RUNTIME_HISTORY_MAX_CHARACTERS} 个字符"
        )
    return result


def _knowledge_context(
    values: Iterable[RuntimeKnowledgeChunk],
    *,
    knowledge_base_id: str | None,
) -> tuple[RuntimeKnowledgeChunk, ...]:
    result = tuple(values)
    if len(result) > RUNTIME_KNOWLEDGE_MAX_CHUNKS:
        raise RuntimeValidationError(
            "knowledge_context", f"不能超过 {RUNTIME_KNOWLEDGE_MAX_CHUNKS} 个片段"
        )
    if any(not isinstance(value, RuntimeKnowledgeChunk) for value in result):
        raise RuntimeValidationError("knowledge_context", "必须只包含 RuntimeKnowledgeChunk")
    if knowledge_base_id is None and result:
        raise RuntimeValidationError("knowledge_context", "未绑定知识库时必须为空")
    if any(value.knowledge_base_id != knowledge_base_id for value in result):
        raise RuntimeValidationError("knowledge_context", "片段必须来自当前绑定知识库")
    references = tuple((value.knowledge_base_id, value.chunk_id) for value in result)
    if len(set(references)) != len(references):
        raise RuntimeValidationError("knowledge_context", "不能包含重复片段")
    if sum(len(value.content) for value in result) > RUNTIME_KNOWLEDGE_MAX_CHARACTERS:
        raise RuntimeValidationError(
            "knowledge_context",
            f"总内容不能超过 {RUNTIME_KNOWLEDGE_MAX_CHARACTERS} 个字符",
        )
    return result


def _workflow_ids(values: Sequence[UUID]) -> tuple[UUID, ...]:
    result = tuple(values)
    if len(result) > RUNTIME_ALLOWED_WORKFLOWS_MAX_ITEMS:
        raise RuntimeValidationError(
            "allowed_workflow_ids",
            f"不能超过 {RUNTIME_ALLOWED_WORKFLOWS_MAX_ITEMS} 项",
        )
    if any(not isinstance(value, UUID) for value in result):
        raise RuntimeValidationError("allowed_workflow_ids", "必须只包含 UUID")
    if len(set(result)) != len(result):
        raise RuntimeValidationError("allowed_workflow_ids", "不能包含重复项")
    return result


def _capability_ids(values: Sequence[UUID]) -> tuple[UUID, ...]:
    result = tuple(values)
    if len(result) > 500:
        raise RuntimeValidationError("allowed_tool_capability_ids", "不能超过 500 项")
    if any(not isinstance(value, UUID) for value in result):
        raise RuntimeValidationError("allowed_tool_capability_ids", "必须只包含 UUID")
    if len(set(result)) != len(result):
        raise RuntimeValidationError("allowed_tool_capability_ids", "不能包含重复项")
    return result


def _optional_reference(field: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _required_text(field, value, CITATION_REFERENCE_MAX_LENGTH)


def _uuid(field: str, value: object) -> UUID:
    if not isinstance(value, UUID):
        raise RuntimeValidationError(field, "必须是 UUID")
    return value


def _positive_integer(field: str, value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise RuntimeValidationError(field, "必须是正整数")
    return value


def _required_text(field: str, value: object, max_length: int) -> str:
    if not isinstance(value, str):
        raise RuntimeValidationError(field, "必须是字符串")
    normalized = value.strip()
    if not normalized:
        raise RuntimeValidationError(field, "不能为空")
    if len(normalized) > max_length:
        raise RuntimeValidationError(field, f"不能超过 {max_length} 个字符")
    return normalized


def _content(field: str, value: object, max_length: int) -> str:
    if not isinstance(value, str):
        raise RuntimeValidationError(field, "必须是字符串")
    if not value.strip():
        raise RuntimeValidationError(field, "不能为空")
    if len(value) > max_length:
        raise RuntimeValidationError(field, f"不能超过 {max_length} 个字符")
    return value
