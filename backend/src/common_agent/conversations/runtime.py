from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

from common_agent.concurrency import KeyedLockPool
from common_agent.conversations.contracts import (
    GenerationNotActive,
    KnowledgeResolver,
    StopAccepted,
)
from common_agent.conversations.events import ConversationEventBroker, ConversationEventKind
from common_agent.conversations.projection import ConversationMessageProjector, safe_error_code
from common_agent.domain.conversation import Message, MessageRole, MessageStatus
from common_agent.domain.employee import Employee
from common_agent.observability import bind_observation_context, log_event
from common_agent.runtimes.base import (
    RUNTIME_HISTORY_MAX_CHARACTERS,
    RUNTIME_HISTORY_MAX_MESSAGES,
    EmployeeRuntime,
    EmployeeRuntimeRequest,
    RuntimeConversationMessage,
    RuntimeEventKind,
    RuntimeStopToken,
)

_LOGGER = logging.getLogger("common_agent.conversations")


@dataclass(slots=True)
class _ActiveRun:
    turn_id: UUID
    assistant_message_id: UUID
    stop: RuntimeStopToken
    task: asyncio.Task[None] | None = None


class ConversationRuntimeCoordinator:
    def __init__(
        self,
        *,
        knowledge: KnowledgeResolver,
        runtime: EmployeeRuntime,
        events: ConversationEventBroker,
        projector: ConversationMessageProjector,
        locks: KeyedLockPool[UUID],
    ) -> None:
        self._knowledge = knowledge
        self._runtime = runtime
        self._events = events
        self._projector = projector
        self._locks = locks
        self._active: dict[UUID, _ActiveRun] = {}
        self._closed = False

    def ensure_open(self) -> None:
        if self._closed:
            raise RuntimeError("conversation service is closed")

    def is_active(self, conversation_id: UUID) -> bool:
        return conversation_id in self._active

    def stop(self, conversation_id: UUID) -> StopAccepted:
        active = self._active.get(conversation_id)
        if active is None:
            raise GenerationNotActive
        active.stop.request_stop()
        return StopAccepted(
            turn_id=active.turn_id,
            assistant_message_id=active.assistant_message_id,
        )

    async def start(
        self,
        *,
        turn_id: UUID,
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
        self._active[assistant_message.conversation_id] = active
        await self._events.publish(
            turn_id=turn_id,
            message=assistant_message,
            kind=ConversationEventKind.ASSISTANT_STARTED,
            retry=retry,
        )
        active.task = asyncio.create_task(
            self._execute(
                turn_id=turn_id,
                employee=employee,
                history=history,
                user_message=user_message,
                assistant_message=assistant_message,
                stop=stop,
            ),
            name=f"conversation-{assistant_message.conversation_id}-turn-{turn_id}",
        )

    async def aclose(self) -> None:
        if self._closed:
            return
        self._closed = True
        active_runs = tuple(self._active.values())
        for active in active_runs:
            active.stop.request_stop()
        tasks = tuple(active.task for active in active_runs if active.task is not None)
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=10)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
        await self._runtime.aclose()

    async def _execute(
        self,
        *,
        turn_id: UUID,
        employee: Employee,
        history: tuple[Message, ...],
        user_message: Message,
        assistant_message: Message,
        stop: RuntimeStopToken,
    ) -> None:
        started_at = monotonic()
        outcome_status = "failed"
        outcome_error: str | None = "generation_failed"
        conversation_id = assistant_message.conversation_id
        with bind_observation_context(
            conversation_id=conversation_id,
            message_id=assistant_message.id,
            turn_id=turn_id,
        ):
            log_event(_LOGGER, "conversation.turn.started", status="running")
            try:
                resolved = await self._knowledge.resolve(employee, user_message)
                request = EmployeeRuntimeRequest(
                    conversation_id=conversation_id,
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
                        await self._projector.persist_stopped(turn_id, assistant_message.id)
                        return
                    if (
                        event.assistant_message_id != assistant_message.id
                        or event.sequence <= last_sequence
                    ):
                        outcome_error = "runtime_response_invalid"
                        await self._projector.persist_failure(
                            turn_id,
                            assistant_message.id,
                            outcome_error,
                        )
                        return
                    last_sequence = event.sequence
                    terminal_message = await self._projector.persist_runtime_event(
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
                    await self._projector.persist_stopped(turn_id, assistant_message.id)
                else:
                    outcome_error = "runtime_stream_interrupted"
                    await self._projector.persist_failure(
                        turn_id,
                        assistant_message.id,
                        outcome_error,
                    )
            except asyncio.CancelledError:
                outcome_status = "stopped"
                outcome_error = None
                await self._projector.persist_stopped(turn_id, assistant_message.id)
                raise
            except Exception as error:
                if stop.is_requested:
                    outcome_status = "stopped"
                    outcome_error = None
                    await self._projector.persist_stopped(turn_id, assistant_message.id)
                else:
                    outcome_error = safe_error_code(error)
                    await self._projector.persist_failure(
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
                async with self._locks.hold(conversation_id):
                    active = self._active.get(conversation_id)
                    if active is not None and active.turn_id == turn_id:
                        self._active.pop(conversation_id, None)


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


__all__ = ["ConversationRuntimeCoordinator"]
