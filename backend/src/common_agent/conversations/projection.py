from __future__ import annotations

from uuid import UUID, uuid4

from common_agent.conversations.contracts import MessageNotFound
from common_agent.conversations.events import (
    ConversationEventBroker,
    ConversationEventKind,
    ToolCallEvent,
)
from common_agent.domain.conversation import MESSAGE_ERROR_CODE_MAX_LENGTH, Citation, Message
from common_agent.ports.conversations import ConversationUnitOfWorkFactory
from common_agent.runtimes.base import RuntimeEvent, RuntimeEventKind
from common_agent.tools.models import ToolCallErrorCode


class ConversationMessageProjector:
    def __init__(
        self,
        unit_of_work_factory: ConversationUnitOfWorkFactory,
        events: ConversationEventBroker,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._events = events

    async def recover_interrupted(self) -> int:
        async with self._unit_of_work_factory() as unit_of_work:
            active_messages = await unit_of_work.messages.list_active()

        recovered = 0
        for message in active_messages:
            turn_id = uuid4()
            if await self.prevent_unsafe_tool_replay(
                turn_id,
                message,
            ) or await self.persist_failure(
                turn_id,
                message.id,
                "generation_interrupted",
            ):
                recovered += 1
        return recovered

    async def persist_runtime_event(
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

            if event.kind in {
                RuntimeEventKind.TOOL_STARTED,
                RuntimeEventKind.TOOL_COMPLETED,
                RuntimeEventKind.TOOL_FAILED,
            }:
                if (
                    event.tool_call_id is None
                    or event.capability_id is None
                    or event.capability_name is None
                ):
                    raise ValueError("runtime tool event is missing safe metadata")
                kind = {
                    RuntimeEventKind.TOOL_STARTED: ConversationEventKind.ASSISTANT_TOOL_STARTED,
                    RuntimeEventKind.TOOL_COMPLETED: (
                        ConversationEventKind.ASSISTANT_TOOL_COMPLETED
                    ),
                    RuntimeEventKind.TOOL_FAILED: ConversationEventKind.ASSISTANT_TOOL_FAILED,
                }[event.kind]
                tool_call = ToolCallEvent(
                    tool_call_id=event.tool_call_id,
                    capability_id=event.capability_id,
                    capability_name=event.capability_name,
                    error_code=(
                        event.error_code if event.kind is RuntimeEventKind.TOOL_FAILED else None
                    ),
                )
                await self._events.publish(
                    turn_id=turn_id,
                    message=current,
                    kind=kind,
                    tool_call=tool_call,
                )
                return None

            if event.kind is RuntimeEventKind.REASONING:
                # 思考不属于回复正文, 只作为会话事件广播并进入事件历史, 不改消息本身
                await self._events.publish(
                    turn_id=turn_id,
                    message=current,
                    kind=ConversationEventKind.ASSISTANT_REASONING,
                    delta=event.delta or "",
                )
                return None

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

    async def restart_execution(self, message_id: UUID) -> Message:
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.messages.get(message_id)
            if current is None:
                raise MessageNotFound
            restarted = current.restart_execution()
            if not await unit_of_work.messages.update(restarted):
                raise MessageNotFound
            await unit_of_work.commit()
        return restarted

    async def prevent_unsafe_tool_replay(self, turn_id: UUID, message: Message) -> bool:
        recovery = await self._events.tool_call_recovery_state(
            message.conversation_id,
            message.id,
        )
        if not recovery.attempted:
            return False
        for tool_call in recovery.unresolved:
            await self._events.publish(
                turn_id=turn_id,
                message=message,
                kind=ConversationEventKind.ASSISTANT_TOOL_FAILED,
                tool_call=ToolCallEvent(
                    tool_call_id=tool_call.tool_call_id,
                    capability_id=tool_call.capability_id,
                    capability_name=tool_call.capability_name,
                    error_code=ToolCallErrorCode.RESULT_UNKNOWN.value,
                ),
            )
        return await self.persist_failure(
            turn_id, message.id, ToolCallErrorCode.RESULT_UNKNOWN.value
        )

    async def republish_terminal(self, turn_id: UUID, message: Message) -> None:
        kind = {
            "completed": ConversationEventKind.ASSISTANT_COMPLETED,
            "failed": ConversationEventKind.ASSISTANT_FAILED,
            "stopped": ConversationEventKind.ASSISTANT_STOPPED,
        }.get(message.status.value)
        if kind is None:
            raise ValueError("only terminal messages can be republished")
        await self._events.publish(turn_id=turn_id, message=message, kind=kind)

    async def persist_failure(
        self,
        turn_id: UUID,
        message_id: UUID,
        error_code: str,
    ) -> bool:
        async with self._unit_of_work_factory() as unit_of_work:
            current = await unit_of_work.messages.get(message_id)
            if current is None or current.is_terminal:
                return False
            failed = current.fail(error_code=normalized_error_code(error_code))
            if not await unit_of_work.messages.update(failed):
                return False
            await unit_of_work.commit()
        await self._events.publish(
            turn_id=turn_id,
            message=failed,
            kind=ConversationEventKind.ASSISTANT_FAILED,
        )
        return True

    async def persist_stopped(self, turn_id: UUID, message_id: UUID) -> None:
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


def safe_error_code(error: Exception) -> str:
    code = getattr(error, "code", None)
    return normalized_error_code(code if isinstance(code, str) else "generation_failed")


def normalized_error_code(value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > MESSAGE_ERROR_CODE_MAX_LENGTH:
        return "generation_failed"
    return normalized


__all__ = ["ConversationMessageProjector", "normalized_error_code", "safe_error_code"]
