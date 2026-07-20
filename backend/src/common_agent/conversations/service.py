from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from typing import Protocol
from uuid import UUID, uuid4

from common_agent.concurrency import KeyedLockPool
from common_agent.conversations.events import ConversationEventBroker, ConversationEventKind
from common_agent.domain.conversation import (
    MESSAGE_ERROR_CODE_MAX_LENGTH,
    Citation,
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
)
from common_agent.domain.employee import Employee
from common_agent.knowledge.retrieval import ResolvedKnowledgeContext
from common_agent.observability import bind_observation_context, log_event
from common_agent.ports.conversations import (
    ConversationAlreadyExists,
    ConversationUnitOfWorkFactory,
    MessageAlreadyExists,
    MessageSequenceAlreadyExists,
)
from common_agent.runtimes.base import (
    RUNTIME_HISTORY_MAX_CHARACTERS,
    RUNTIME_HISTORY_MAX_MESSAGES,
    EmployeeRuntime,
    EmployeeRuntimeRequest,
    RuntimeConversationMessage,
    RuntimeEvent,
    RuntimeEventKind,
    RuntimeStopToken,
)

_LOGGER = logging.getLogger("common_agent.conversations")


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


@dataclass(slots=True)
class _ActiveRun:
    turn_id: UUID
    assistant_message_id: UUID
    stop: RuntimeStopToken
    task: asyncio.Task[None] | None = None


class ConversationService:
    def __init__(
        self,
        unit_of_work_factory: ConversationUnitOfWorkFactory,
        *,
        employees: EmployeeDirectory,
        knowledge: KnowledgeResolver,
        runtime: EmployeeRuntime,
        events: ConversationEventBroker,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._employees = employees
        self._knowledge = knowledge
        self._runtime = runtime
        self._events = events
        self._locks: KeyedLockPool[UUID] = KeyedLockPool()
        self._active: dict[UUID, _ActiveRun] = {}
        self._closed = False

    async def list(self, *, employee_id: UUID | None = None) -> tuple[Conversation, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            if employee_id is None:
                return await unit_of_work.conversations.list()
            return await unit_of_work.conversations.list_for_employee(employee_id)

    async def create(
        self,
        *,
        employee_id: UUID,
        title: str,
        conversation_id: UUID | None = None,
    ) -> Conversation:
        await self._employees.get(employee_id)
        conversation = Conversation.create(
            employee_id=employee_id,
            title=title,
            conversation_id=conversation_id,
        )
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                await unit_of_work.conversations.add(conversation)
                await unit_of_work.commit()
        except ConversationAlreadyExists:
            raise ConversationRequestConflict from None
        return conversation

    async def list_messages(self, conversation_id: UUID) -> tuple[Message, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            conversation = await unit_of_work.conversations.get(conversation_id)
            if conversation is None:
                raise ConversationNotFound
            return await unit_of_work.messages.list_for_conversation(conversation_id)

    async def send(
        self,
        conversation_id: UUID,
        *,
        user_message_id: UUID,
        content: str,
    ) -> TurnAccepted:
        self._ensure_open()
        async with self._locks.hold(conversation_id):
            if conversation_id in self._active:
                raise ConversationBusy
            conversation, _ = await self._load_conversation(conversation_id)
            employee = await self._employees.get(conversation.employee_id)

            try:
                async with self._unit_of_work_factory() as unit_of_work:
                    current = await unit_of_work.conversations.get(conversation_id)
                    if current is None:
                        raise ConversationNotFound
                    messages = await unit_of_work.messages.list_for_conversation(conversation_id)
                    if _has_active_assistant(messages):
                        raise ConversationBusy
                    next_sequence = messages[-1].sequence_number + 1 if messages else 1
                    user_message = Message.create_user(
                        conversation_id=conversation_id,
                        sequence_number=next_sequence,
                        content=content,
                        message_id=user_message_id,
                    )
                    assistant_message = Message.create_assistant(
                        conversation_id=conversation_id,
                        sequence_number=next_sequence + 1,
                    )
                    await unit_of_work.messages.add(user_message)
                    await unit_of_work.messages.add(assistant_message)
                    await unit_of_work.conversations.update(current.touch())
                    await unit_of_work.commit()
                    persisted_history = (*messages, user_message, assistant_message)
            except MessageAlreadyExists:
                raise MessageRequestConflict from None
            except MessageSequenceAlreadyExists:
                raise ConversationRequestConflict from None

            turn_id = uuid4()
            await self._start_run(
                turn_id=turn_id,
                conversation=current,
                employee=employee,
                history=persisted_history,
                user_message=user_message,
                assistant_message=assistant_message,
                retry=False,
            )
            return TurnAccepted(
                turn_id=turn_id,
                user_message=user_message,
                assistant_message=assistant_message,
                retry=False,
            )

    async def stop(self, conversation_id: UUID) -> StopAccepted:
        async with self._locks.hold(conversation_id):
            active = self._active.get(conversation_id)
            if active is None:
                raise GenerationNotActive
            active.stop.request_stop()
            return StopAccepted(
                turn_id=active.turn_id,
                assistant_message_id=active.assistant_message_id,
            )

    async def retry(self, message_id: UUID) -> TurnAccepted:
        self._ensure_open()
        async with self._unit_of_work_factory() as unit_of_work:
            message = await unit_of_work.messages.get(message_id)
        if message is None:
            raise MessageNotFound
        conversation_id = message.conversation_id

        async with self._locks.hold(conversation_id):
            if conversation_id in self._active:
                raise ConversationBusy
            conversation, messages = await self._load_conversation(conversation_id)
            if (
                not messages
                or messages[-1].id != message_id
                or message.role is not MessageRole.ASSISTANT
                or message.status not in {MessageStatus.FAILED, MessageStatus.STOPPED}
            ):
                raise MessageRetryNotAllowed
            user_message = next(
                (
                    item
                    for item in reversed(messages[:-1])
                    if item.sequence_number == message.sequence_number - 1
                    and item.role is MessageRole.USER
                ),
                None,
            )
            if user_message is None:
                raise MessageRetryNotAllowed
            employee = await self._employees.get(conversation.employee_id)
            retried = message.retry()
            try:
                async with self._unit_of_work_factory() as unit_of_work:
                    current = await unit_of_work.conversations.get(conversation_id)
                    current_message = await unit_of_work.messages.get(message_id)
                    if current is None:
                        raise ConversationNotFound
                    if current_message is None:
                        raise MessageNotFound
                    if current_message.status not in {
                        MessageStatus.FAILED,
                        MessageStatus.STOPPED,
                    }:
                        raise MessageRetryNotAllowed
                    if not await unit_of_work.messages.update(retried):
                        raise MessageNotFound
                    await unit_of_work.conversations.update(current.touch())
                    await unit_of_work.commit()
            except MessageSequenceAlreadyExists:
                raise ConversationRequestConflict from None

            turn_id = uuid4()
            retried_history = (*messages[:-1], retried)
            await self._start_run(
                turn_id=turn_id,
                conversation=conversation,
                employee=employee,
                history=retried_history,
                user_message=user_message,
                assistant_message=retried,
                retry=True,
            )
            return TurnAccepted(
                turn_id=turn_id,
                user_message=user_message,
                assistant_message=retried,
                retry=True,
            )

    async def recover_interrupted(self) -> int:
        async with self._unit_of_work_factory() as unit_of_work:
            active_messages = await unit_of_work.messages.list_active()
            recovered: list[Message] = []
            for message in active_messages:
                failed = message.fail(error_code="generation_interrupted")
                if await unit_of_work.messages.update(failed):
                    recovered.append(failed)
            if recovered:
                await unit_of_work.commit()

        for message in recovered:
            await self._events.publish(
                turn_id=uuid4(),
                message=message,
                kind=ConversationEventKind.ASSISTANT_FAILED,
            )
        return len(recovered)

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        active_runs = tuple(self._active.values())
        for active in active_runs:
            active.stop.request_stop()
        tasks = tuple(active.task for active in active_runs if active.task is not None)
        if tasks:
            done, pending = await asyncio.wait(tasks, timeout=10)
            del done
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        await self._runtime.aclose()

    async def _load_conversation(
        self,
        conversation_id: UUID,
    ) -> tuple[Conversation, tuple[Message, ...]]:
        async with self._unit_of_work_factory() as unit_of_work:
            conversation = await unit_of_work.conversations.get(conversation_id)
            if conversation is None:
                raise ConversationNotFound
            messages = await unit_of_work.messages.list_for_conversation(conversation_id)
            return conversation, messages

    async def _start_run(
        self,
        *,
        turn_id: UUID,
        conversation: Conversation,
        employee: Employee,
        history: tuple[Message, ...],
        user_message: Message,
        assistant_message: Message,
        retry: bool,
    ) -> None:
        stop = RuntimeStopToken()
        active = _ActiveRun(
            turn_id=turn_id,
            assistant_message_id=assistant_message.id,
            stop=stop,
        )
        self._active[conversation.id] = active
        await self._events.publish(
            turn_id=turn_id,
            message=assistant_message,
            kind=ConversationEventKind.ASSISTANT_STARTED,
            retry=retry,
        )
        active.task = asyncio.create_task(
            self._execute_run(
                turn_id=turn_id,
                conversation=conversation,
                employee=employee,
                history=history,
                user_message=user_message,
                assistant_message=assistant_message,
                stop=stop,
            ),
            name=f"conversation-{conversation.id}-turn-{turn_id}",
        )

    async def _execute_run(
        self,
        *,
        turn_id: UUID,
        conversation: Conversation,
        employee: Employee,
        history: tuple[Message, ...],
        user_message: Message,
        assistant_message: Message,
        stop: RuntimeStopToken,
    ) -> None:
        started_at = monotonic()
        outcome_status = "failed"
        outcome_error: str | None = "generation_failed"
        with bind_observation_context(
            conversation_id=conversation.id,
            message_id=assistant_message.id,
            turn_id=turn_id,
        ):
            log_event(_LOGGER, "conversation.turn.started", status="running")
            try:
                resolved = await self._knowledge.resolve(employee, user_message)
                request = EmployeeRuntimeRequest(
                    conversation_id=conversation.id,
                    employee_id=employee.id,
                    assistant_message_id=assistant_message.id,
                    assistant_sequence_number=assistant_message.sequence_number,
                    system_instruction=employee.system_prompt,
                    history=_runtime_history(history, assistant_message),
                    knowledge_base_id=resolved.knowledge_base_id,
                    knowledge_context=resolved.runtime_chunks,
                    allowed_workflow_ids=employee.allowed_workflow_ids,
                )
                last_sequence = 0
                async for event in self._runtime.stream(request, stop=stop):
                    if stop.is_requested and event.kind is not RuntimeEventKind.STOPPED:
                        outcome_status = "stopped"
                        outcome_error = None
                        await self._persist_stopped(turn_id, assistant_message.id)
                        return
                    if (
                        event.assistant_message_id != assistant_message.id
                        or event.sequence <= last_sequence
                    ):
                        outcome_error = "runtime_response_invalid"
                        await self._persist_failure(
                            turn_id,
                            assistant_message.id,
                            outcome_error,
                        )
                        return
                    last_sequence = event.sequence
                    terminal_message = await self._persist_runtime_event(
                        turn_id=turn_id,
                        event=event,
                        citations=resolved.citations,
                    )
                    if terminal_message is not None:
                        outcome_status = terminal_message.status.value
                        outcome_error = terminal_message.error_code
                        return
                if stop.is_requested:
                    outcome_status = "stopped"
                    outcome_error = None
                    await self._persist_stopped(turn_id, assistant_message.id)
                else:
                    outcome_error = "runtime_stream_interrupted"
                    await self._persist_failure(
                        turn_id,
                        assistant_message.id,
                        outcome_error,
                    )
            except asyncio.CancelledError:
                outcome_status = "stopped"
                outcome_error = None
                await self._persist_stopped(turn_id, assistant_message.id)
                raise
            except Exception as error:
                if stop.is_requested:
                    outcome_status = "stopped"
                    outcome_error = None
                    await self._persist_stopped(turn_id, assistant_message.id)
                else:
                    outcome_error = _safe_error_code(error)
                    await self._persist_failure(
                        turn_id,
                        assistant_message.id,
                        outcome_error,
                    )
            finally:
                log_event(
                    _LOGGER,
                    "conversation.turn.finished",
                    level=(logging.ERROR if outcome_status == "failed" else logging.INFO),
                    status=outcome_status,
                    error_code=outcome_error,
                    duration_ms=max(0.0, (monotonic() - started_at) * 1000),
                )
                async with self._locks.hold(conversation.id):
                    active = self._active.get(conversation.id)
                    if active is not None and active.turn_id == turn_id:
                        self._active.pop(conversation.id, None)

    async def _persist_runtime_event(
        self,
        *,
        turn_id: UUID,
        event: RuntimeEvent,
        citations: tuple[Citation, ...],
    ) -> Message | None:
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.messages.get(event.assistant_message_id)
            if current is None:
                raise MessageNotFound
            if current.is_terminal:
                return current

            if event.kind is RuntimeEventKind.DELTA:
                updated = current.append_delta(event.delta or "")
                kind = ConversationEventKind.ASSISTANT_DELTA
            elif event.kind is RuntimeEventKind.COMPLETED:
                updated = current.complete(citations=citations)
                kind = ConversationEventKind.ASSISTANT_COMPLETED
            elif event.kind is RuntimeEventKind.FAILED:
                updated = current.fail(error_code=event.error_code or "generation_failed")
                kind = ConversationEventKind.ASSISTANT_FAILED
            else:
                updated = current.stop()
                kind = ConversationEventKind.ASSISTANT_STOPPED

            if not await unit_of_work.messages.update(updated):
                raise MessageNotFound
            await unit_of_work.commit()

        await self._events.publish(
            turn_id=turn_id,
            message=updated,
            kind=kind,
            delta=event.delta if event.kind is RuntimeEventKind.DELTA else None,
        )
        return updated if event.kind is not RuntimeEventKind.DELTA else None

    async def _persist_failure(
        self,
        turn_id: UUID,
        message_id: UUID,
        error_code: str,
    ) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.messages.get(message_id)
            if current is None or current.is_terminal:
                return
            failed = current.fail(error_code=_normalized_error_code(error_code))
            if not await unit_of_work.messages.update(failed):
                return
            await unit_of_work.commit()
        await self._events.publish(
            turn_id=turn_id,
            message=failed,
            kind=ConversationEventKind.ASSISTANT_FAILED,
        )

    async def _persist_stopped(self, turn_id: UUID, message_id: UUID) -> None:
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.messages.get(message_id)
            if current is None or current.is_terminal:
                return
            stopped = current.stop()
            if not await unit_of_work.messages.update(stopped):
                return
            await unit_of_work.commit()
        await self._events.publish(
            turn_id=turn_id,
            message=stopped,
            kind=ConversationEventKind.ASSISTANT_STOPPED,
        )

    def _ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("conversation service is closed")


def _has_active_assistant(messages: tuple[Message, ...]) -> bool:
    return any(
        message.role is MessageRole.ASSISTANT
        and message.status in {MessageStatus.PENDING, MessageStatus.STREAMING}
        for message in messages
    )


def _runtime_history(
    messages: tuple[Message, ...],
    assistant_message: Message,
) -> tuple[RuntimeConversationMessage, ...]:
    candidates = [
        RuntimeConversationMessage(
            message_id=message.id,
            sequence_number=message.sequence_number,
            role=message.role,
            content=message.content,
        )
        for message in messages
        if message.sequence_number < assistant_message.sequence_number
        and (
            message.role is MessageRole.USER
            or (
                message.content.strip()
                and message.status in {MessageStatus.COMPLETED, MessageStatus.STOPPED}
            )
        )
    ]
    retained: list[RuntimeConversationMessage] = []
    character_count = 0
    for message in reversed(candidates):
        if len(retained) >= RUNTIME_HISTORY_MAX_MESSAGES:
            break
        if character_count + len(message.content) > RUNTIME_HISTORY_MAX_CHARACTERS:
            break
        retained.append(message)
        character_count += len(message.content)
    return tuple(reversed(retained))


def _safe_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    return _normalized_error_code(code if isinstance(code, str) else "generation_failed")


def _normalized_error_code(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > MESSAGE_ERROR_CODE_MAX_LENGTH:
        return "generation_failed"
    return normalized
