from __future__ import annotations

from types import TracebackType
from typing import Protocol
from uuid import UUID

from common_agent.domain.conversation import Conversation, Message


class ConversationAlreadyExists(Exception):
    """Raised when a conversation identity is already persisted."""


class MessageAlreadyExists(Exception):
    """Raised when a message identity is already persisted."""


class MessageSequenceAlreadyExists(Exception):
    """Raised when a conversation already owns the requested message sequence."""


class ConversationRepository(Protocol):
    async def list(self) -> tuple[Conversation, ...]: ...

    async def list_for_employee(self, employee_id: UUID) -> tuple[Conversation, ...]: ...

    async def get(self, conversation_id: UUID) -> Conversation | None: ...

    async def add(self, conversation: Conversation) -> None: ...

    async def update(self, conversation: Conversation) -> bool: ...

    async def delete(self, conversation_id: UUID) -> bool: ...


class MessageRepository(Protocol):
    async def list_for_conversation(self, conversation_id: UUID) -> tuple[Message, ...]: ...

    async def list_active(self) -> tuple[Message, ...]: ...

    async def get(self, message_id: UUID) -> Message | None: ...

    async def add(self, message: Message) -> None: ...

    async def update(self, message: Message) -> bool: ...


class ConversationUnitOfWork(Protocol):
    @property
    def conversations(self) -> ConversationRepository: ...

    @property
    def messages(self) -> MessageRepository: ...

    async def __aenter__(self) -> ConversationUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class ConversationUnitOfWorkFactory(Protocol):
    def __call__(self) -> ConversationUnitOfWork: ...
