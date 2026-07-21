from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from common_agent.conversations.contracts import (
    ConversationBusy,
    ConversationNotFound,
    ConversationRequestConflict,
    MessageNotFound,
    MessageRequestConflict,
    MessageRetryNotAllowed,
)
from common_agent.domain.conversation import (
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
)
from common_agent.pagination import (
    CursorPage,
    ListPageRequest,
    PageAnchor,
    decode_keyset_cursor,
    encode_keyset_cursor,
)
from common_agent.ports.conversations import (
    ConversationAlreadyExists,
    ConversationUnitOfWorkFactory,
    MessageAlreadyExists,
    MessageSequenceAlreadyExists,
)
from common_agent.tasks import TaskRequest


@dataclass(frozen=True, slots=True)
class PreparedTurn:
    conversation: Conversation
    history: tuple[Message, ...]
    user_message: Message
    assistant_message: Message


@dataclass(frozen=True, slots=True)
class PreparedRetry:
    conversation: Conversation
    history: tuple[Message, ...]
    user_message: Message
    assistant_message: Message


class ConversationPersistence:
    def __init__(self, unit_of_work_factory: ConversationUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    async def list(self, *, employee_id: UUID | None = None) -> tuple[Conversation, ...]:
        async with self._unit_of_work_factory() as unit_of_work:
            if employee_id is None:
                return await unit_of_work.conversations.list()
            return await unit_of_work.conversations.list_for_employee(employee_id)

    async def page(
        self,
        page: ListPageRequest,
        *,
        employee_id: UUID | None = None,
    ) -> CursorPage[Conversation]:
        scope = "conversations" if employee_id is None else f"conversations-{employee_id}"
        after = (
            None
            if page.cursor is None
            else decode_keyset_cursor(
                page.cursor,
                scope=scope,
                search=page.search,
                limit=page.limit,
            )
        )
        async with self._unit_of_work_factory() as unit_of_work:
            result = await unit_of_work.conversations.page(
                limit=page.limit,
                search=page.search,
                after=after,
                employee_id=employee_id,
            )
        next_cursor = None
        if result.has_more:
            last = result.items[-1]
            next_cursor = encode_keyset_cursor(
                scope=scope,
                search=page.search,
                limit=page.limit,
                anchor=PageAnchor(created_at=last.created_at, id=str(last.id)),
            )
        return CursorPage(items=result.items, next_cursor=next_cursor)

    async def create(
        self,
        *,
        employee_id: UUID,
        title: str,
        conversation_id: UUID | None,
    ) -> Conversation:
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
        _, messages = await self.load(conversation_id)
        return messages

    async def delete(self, conversation_id: UUID) -> bool:
        async with self._unit_of_work_factory() as unit_of_work:
            messages = await unit_of_work.messages.list_for_conversation(conversation_id)
            if _has_active_assistant(messages):
                raise ConversationBusy
            deleted = await unit_of_work.conversations.delete(conversation_id)
            if deleted:
                await unit_of_work.commit()
        return deleted

    async def load(self, conversation_id: UUID) -> tuple[Conversation, tuple[Message, ...]]:
        async with self._unit_of_work_factory() as unit_of_work:
            conversation = await unit_of_work.conversations.get(conversation_id)
            if conversation is None:
                raise ConversationNotFound
            messages = await unit_of_work.messages.list_for_conversation(conversation_id)
            return conversation, messages

    async def get_message(self, message_id: UUID) -> Message:
        async with self._unit_of_work_factory() as unit_of_work:
            message = await unit_of_work.messages.get(message_id)
        if message is None:
            raise MessageNotFound
        return message

    async def append_turn(
        self,
        conversation_id: UUID,
        *,
        user_message_id: UUID,
        assistant_message_id: UUID | None = None,
        content: str,
        task_request: TaskRequest | None = None,
        task_max_attempts: int = 3,
    ) -> PreparedTurn:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                conversation = await unit_of_work.conversations.get(conversation_id)
                if conversation is None:
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
                    message_id=assistant_message_id,
                )
                if task_request is not None:
                    payload = task_request.payload
                    if (
                        task_request.aggregate_id != conversation_id
                        or getattr(payload, "user_message_id", None) != user_message.id
                        or getattr(payload, "assistant_message_id", None) != assistant_message.id
                    ):
                        raise ValueError("conversation task does not match prepared turn")
                await unit_of_work.messages.add(user_message)
                await unit_of_work.messages.add(assistant_message)
                await unit_of_work.conversations.update(conversation.touch())
                if task_request is not None:
                    await unit_of_work.tasks.enqueue(
                        task_request,
                        max_attempts=task_max_attempts,
                    )
                await unit_of_work.commit()
        except MessageAlreadyExists:
            raise MessageRequestConflict from None
        except MessageSequenceAlreadyExists:
            raise ConversationRequestConflict from None
        return PreparedTurn(
            conversation=conversation,
            history=(*messages, user_message, assistant_message),
            user_message=user_message,
            assistant_message=assistant_message,
        )

    async def prepare_retry(self, message: Message) -> PreparedRetry:
        conversation, messages = await self.load(message.conversation_id)
        if (
            not messages
            or messages[-1].id != message.id
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
        retried = message.retry()
        return PreparedRetry(
            conversation=conversation,
            history=(*messages[:-1], retried),
            user_message=user_message,
            assistant_message=retried,
        )

    async def commit_retry(
        self,
        prepared: PreparedRetry,
        *,
        task_request: TaskRequest | None = None,
        task_max_attempts: int = 3,
    ) -> None:
        try:
            async with self._unit_of_work_factory() as unit_of_work:
                current = await unit_of_work.conversations.get(prepared.conversation.id)
                current_message = await unit_of_work.messages.get(prepared.assistant_message.id)
                if current is None:
                    raise ConversationNotFound
                if current_message is None:
                    raise MessageNotFound
                if current_message.status not in {MessageStatus.FAILED, MessageStatus.STOPPED}:
                    raise MessageRetryNotAllowed
                if not await unit_of_work.messages.update(prepared.assistant_message):
                    raise MessageNotFound
                await unit_of_work.conversations.update(current.touch())
                if task_request is not None:
                    payload = task_request.payload
                    if (
                        task_request.aggregate_id != prepared.conversation.id
                        or getattr(payload, "user_message_id", None) != prepared.user_message.id
                        or getattr(payload, "assistant_message_id", None)
                        != prepared.assistant_message.id
                    ):
                        raise ValueError("conversation task does not match prepared retry")
                    await unit_of_work.tasks.enqueue(
                        task_request,
                        max_attempts=task_max_attempts,
                    )
                await unit_of_work.commit()
        except MessageSequenceAlreadyExists:
            raise ConversationRequestConflict from None


def _has_active_assistant(messages: tuple[Message, ...]) -> bool:
    return any(
        message.role is MessageRole.ASSISTANT
        and message.status in {MessageStatus.PENDING, MessageStatus.STREAMING}
        for message in messages
    )


__all__ = ["ConversationPersistence", "PreparedRetry", "PreparedTurn"]
