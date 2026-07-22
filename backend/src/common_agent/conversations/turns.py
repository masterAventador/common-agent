from __future__ import annotations

from uuid import UUID, uuid4

from common_agent.application.resource_locks import ResourceMutationGuard
from common_agent.concurrency import KeyedLockPool
from common_agent.conversations.contracts import (
    ConversationBusy,
    ConversationExecutionTarget,
    ConversationTurnAccepted,
    TurnAccepted,
)
from common_agent.conversations.durable import ConversationTaskCoordinator
from common_agent.conversations.persistence import (
    ConversationPersistence,
    PreparedRetry,
    PreparedTurn,
)
from common_agent.conversations.runtime import ConversationRuntimeCoordinator
from common_agent.conversations.targets import ConversationExecutionTargetResolver
from common_agent.domain.conversation import CONVERSATION_TITLE_MAX_LENGTH, Conversation
from common_agent.tools.models import ToolGrantSelection, ToolGrantSnapshot


class ConversationTurnCoordinator:
    def __init__(
        self,
        *,
        persistence: ConversationPersistence,
        runtime: ConversationRuntimeCoordinator,
        durable: ConversationTaskCoordinator,
        targets: ConversationExecutionTargetResolver,
        locks: KeyedLockPool[UUID],
        guard: ResourceMutationGuard,
    ) -> None:
        self._persistence = persistence
        self._runtime = runtime
        self._durable = durable
        self._targets = targets
        self._locks = locks
        self._guard = guard

    async def send(
        self,
        conversation_id: UUID,
        *,
        user_message_id: UUID,
        content: str,
        model_configuration_id: UUID | None,
    ) -> TurnAccepted:
        self._runtime.ensure_open()
        async with self._locks.hold(conversation_id):
            if self._runtime.is_active(conversation_id):
                raise ConversationBusy
            conversation, _ = await self._persistence.load(conversation_id)
            keys = self._targets.resource_keys(
                conversation,
                model_configuration_id=model_configuration_id,
            )
            async with self._guard.hold(*keys):
                target = await self._targets.for_selection(
                    conversation,
                    model_configuration_id=model_configuration_id,
                )
                turn_id, prepared = await self._append(
                    conversation,
                    user_message_id=user_message_id,
                    content=content,
                    model_configuration_id=target.model_configuration_id,
                    model_identifier=target.model_identifier,
                )
            await self._start_if_inline(turn_id, target, prepared, retry=False)
            return _accepted(turn_id, prepared, retry=False)

    async def create_first(
        self,
        *,
        conversation_id: UUID,
        user_message_id: UUID,
        employee_id: UUID | None,
        model_configuration_id: UUID,
        content: str,
        tool_selection: ToolGrantSelection,
    ) -> ConversationTurnAccepted:
        self._runtime.ensure_open()
        async with self._locks.hold(conversation_id):
            conversation = _new_conversation(
                conversation_id=conversation_id,
                employee_id=employee_id,
                model_configuration_id=model_configuration_id,
                content=content,
            )
            initial_tool_grants = await self._targets.new_conversation_grants(
                conversation,
                tool_selection,
            )
            keys = self._targets.resource_keys(
                conversation,
                model_configuration_id=model_configuration_id,
            )
            async with self._guard.hold(*keys):
                target = await self._targets.for_selection(
                    conversation,
                    model_configuration_id=model_configuration_id,
                    initial_tool_grants=initial_tool_grants,
                )
                turn_id, prepared = await self._create(
                    conversation,
                    user_message_id=user_message_id,
                    content=content,
                    model_configuration_id=target.model_configuration_id,
                    model_identifier=target.model_identifier,
                    initial_tool_grants=initial_tool_grants,
                )
            await self._start_if_inline(turn_id, target, prepared, retry=False)
            return ConversationTurnAccepted(
                conversation=prepared.conversation,
                turn=_accepted(turn_id, prepared, retry=False),
            )

    async def retry(self, message_id: UUID) -> TurnAccepted:
        self._runtime.ensure_open()
        message = await self._persistence.get_message(message_id)
        async with self._locks.hold(message.conversation_id):
            if self._runtime.is_active(message.conversation_id):
                raise ConversationBusy
            prepared = await self._persistence.prepare_retry(message)
            target = await self._targets.for_message(
                prepared.conversation,
                prepared.assistant_message,
            )
            turn_id = uuid4()
            task_request = self._durable.request(
                conversation_id=prepared.conversation.id,
                turn_id=turn_id,
                user_message_id=prepared.user_message.id,
                assistant_message_id=prepared.assistant_message.id,
                retry=True,
            )
            await self._persistence.commit_retry(
                prepared,
                task_request=task_request,
                task_max_attempts=self._durable.maximum_attempts,
            )
            await self._start_if_inline(turn_id, target, prepared, retry=True)
            return _accepted(turn_id, prepared, retry=True)

    async def _append(
        self,
        conversation: Conversation,
        *,
        user_message_id: UUID,
        content: str,
        model_configuration_id: UUID,
        model_identifier: str,
    ) -> tuple[UUID, PreparedTurn]:
        turn_id = uuid4()
        assistant_message_id = uuid4()
        task_request = self._durable.request(
            conversation_id=conversation.id,
            turn_id=turn_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            retry=False,
        )
        prepared = await self._persistence.append_turn(
            conversation.id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            content=content,
            model_configuration_id=model_configuration_id,
            model_identifier=model_identifier,
            task_request=task_request,
            task_max_attempts=self._durable.maximum_attempts,
        )
        return turn_id, prepared

    async def _create(
        self,
        conversation: Conversation,
        *,
        user_message_id: UUID,
        content: str,
        model_configuration_id: UUID,
        model_identifier: str,
        initial_tool_grants: ToolGrantSnapshot | None,
    ) -> tuple[UUID, PreparedTurn]:
        turn_id = uuid4()
        assistant_message_id = uuid4()
        task_request = self._durable.request(
            conversation_id=conversation.id,
            turn_id=turn_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            retry=False,
        )
        prepared = await self._persistence.create_first_turn(
            conversation,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            content=content,
            model_configuration_id=model_configuration_id,
            model_identifier=model_identifier,
            initial_tool_grants=initial_tool_grants,
            task_request=task_request,
            task_max_attempts=self._durable.maximum_attempts,
        )
        return turn_id, prepared

    async def _start_if_inline(
        self,
        turn_id: UUID,
        target: ConversationExecutionTarget,
        prepared: PreparedTurn | PreparedRetry,
        *,
        retry: bool,
    ) -> None:
        if self._durable.enabled:
            return
        await self._runtime.start(
            turn_id=turn_id,
            target=target,
            history=prepared.history,
            user_message=prepared.user_message,
            assistant_message=prepared.assistant_message,
            retry=retry,
        )


def _accepted(
    turn_id: UUID,
    prepared: PreparedTurn | PreparedRetry,
    *,
    retry: bool,
) -> TurnAccepted:
    return TurnAccepted(
        turn_id=turn_id,
        user_message=prepared.user_message,
        assistant_message=prepared.assistant_message,
        retry=retry,
    )


def _new_conversation(
    *,
    conversation_id: UUID,
    employee_id: UUID | None,
    model_configuration_id: UUID,
    content: str,
) -> Conversation:
    title = " ".join(content.strip().split())[:CONVERSATION_TITLE_MAX_LENGTH] or "新会话"
    if employee_id is None:
        return Conversation.create_generic(
            conversation_id=conversation_id,
            title=title,
            model_configuration_id=model_configuration_id,
        )
    return Conversation.create(
        conversation_id=conversation_id,
        employee_id=employee_id,
        title=title,
    )


__all__ = ["ConversationTurnCoordinator"]
