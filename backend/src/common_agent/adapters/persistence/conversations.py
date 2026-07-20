from __future__ import annotations

from collections import defaultdict
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ConversationRow,
    MessageCitationRow,
    MessageRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.domain.conversation import (
    Citation,
    Conversation,
    Message,
    MessageRole,
    MessageStatus,
)
from common_agent.ports.conversations import (
    ConversationAlreadyExists,
    ConversationRepository,
    MessageAlreadyExists,
    MessageRepository,
    MessageSequenceAlreadyExists,
)


class SqlAlchemyConversationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self) -> tuple[Conversation, ...]:
        result = await self._session.scalars(
            select(ConversationRow).order_by(
                ConversationRow.updated_at.desc(),
                ConversationRow.id,
            )
        )
        return tuple(_to_conversation(row) for row in result)

    async def list_for_employee(self, employee_id: UUID) -> tuple[Conversation, ...]:
        result = await self._session.scalars(
            select(ConversationRow)
            .where(ConversationRow.employee_id == str(employee_id))
            .order_by(ConversationRow.updated_at.desc(), ConversationRow.id)
        )
        return tuple(_to_conversation(row) for row in result)

    async def get(self, conversation_id: UUID) -> Conversation | None:
        row = await self._session.get(ConversationRow, str(conversation_id))
        return None if row is None else _to_conversation(row)

    async def add(self, conversation: Conversation) -> None:
        self._session.add(ConversationRow(**_conversation_values(conversation)))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _is_primary_conflict(error):
                raise ConversationAlreadyExists from None
            raise

    async def update(self, conversation: Conversation) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(ConversationRow)
                .where(ConversationRow.id == str(conversation.id))
                .values(
                    title=conversation.title,
                    updated_at=to_database_datetime(conversation.updated_at),
                )
            ),
        )
        return bool(result.rowcount)

    async def delete(self, conversation_id: UUID) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(ConversationRow).where(ConversationRow.id == str(conversation_id))
            ),
        )
        return bool(result.rowcount)


class SqlAlchemyMessageRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_conversation(self, conversation_id: UUID) -> tuple[Message, ...]:
        rows = tuple(
            await self._session.scalars(
                select(MessageRow)
                .where(MessageRow.conversation_id == str(conversation_id))
                .order_by(MessageRow.sequence_number, MessageRow.id)
            )
        )
        citations = await self._citations_for(rows)
        return tuple(_to_message(row, citations.get(row.id, ())) for row in rows)

    async def list_active(self) -> tuple[Message, ...]:
        rows = tuple(
            await self._session.scalars(
                select(MessageRow)
                .where(
                    MessageRow.role == MessageRole.ASSISTANT.value,
                    MessageRow.status.in_(
                        (MessageStatus.PENDING.value, MessageStatus.STREAMING.value)
                    ),
                )
                .order_by(MessageRow.created_at, MessageRow.id)
            )
        )
        citations = await self._citations_for(rows)
        return tuple(_to_message(row, citations.get(row.id, ())) for row in rows)

    async def get(self, message_id: UUID) -> Message | None:
        row = await self._session.get(MessageRow, str(message_id))
        if row is None:
            return None
        citations = await self._citations_for((row,))
        return _to_message(row, citations.get(row.id, ()))

    async def add(self, message: Message) -> None:
        if await self._session.get(MessageRow, str(message.id)) is not None:
            raise MessageAlreadyExists
        self._session.add(MessageRow(**_message_values(message)))
        try:
            await self._session.flush()
        except IntegrityError as error:
            if _has_constraint(error, "uq_messages_conversation_sequence"):
                raise MessageSequenceAlreadyExists from None
            if _is_primary_conflict(error):
                raise MessageAlreadyExists from None
            raise
        self._session.add_all(_citation_rows(message))
        await self._session.flush()

    async def update(self, message: Message) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                update(MessageRow)
                .where(MessageRow.id == str(message.id))
                .values(
                    content=message.content,
                    status=message.status.value,
                    error_code=message.error_code,
                    updated_at=to_database_datetime(message.updated_at),
                )
            ),
        )
        if not result.rowcount:
            return False
        await self._session.execute(
            delete(MessageCitationRow).where(MessageCitationRow.message_id == str(message.id))
        )
        self._session.add_all(_citation_rows(message))
        await self._session.flush()
        return True

    async def _citations_for(self, rows: tuple[MessageRow, ...]) -> dict[str, tuple[Citation, ...]]:
        if not rows:
            return {}
        message_ids = tuple(row.id for row in rows)
        citation_rows = await self._session.scalars(
            select(MessageCitationRow)
            .where(MessageCitationRow.message_id.in_(message_ids))
            .order_by(MessageCitationRow.message_id, MessageCitationRow.position)
        )
        grouped: dict[str, list[Citation]] = defaultdict(list)
        for row in citation_rows:
            grouped[row.message_id].append(_to_citation(row))
        return {message_id: tuple(values) for message_id, values in grouped.items()}


class SqlAlchemyConversationUnitOfWork:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._conversations: ConversationRepository | None = None
        self._messages: MessageRepository | None = None

    @property
    def conversations(self) -> ConversationRepository:
        if self._conversations is None:
            raise RuntimeError("会话事务尚未开始")
        return self._conversations

    @property
    def messages(self) -> MessageRepository:
        if self._messages is None:
            raise RuntimeError("会话事务尚未开始")
        return self._messages

    async def __aenter__(self) -> SqlAlchemyConversationUnitOfWork:
        if self._context is not None:
            raise RuntimeError("会话事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._conversations = SqlAlchemyConversationRepository(session)
        self._messages = SqlAlchemyMessageRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._context
        self._context = None
        self._session = None
        self._conversations = None
        self._messages = None
        if context is None:
            raise RuntimeError("会话事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        session = self._session
        if session is None:
            raise RuntimeError("会话事务尚未开始")
        await session.commit()


class SqlAlchemyConversationUnitOfWorkFactory:
    def __init__(self, database: Database) -> None:
        self._database = database

    def __call__(self) -> SqlAlchemyConversationUnitOfWork:
        return SqlAlchemyConversationUnitOfWork(self._database)


def _conversation_values(conversation: Conversation) -> dict[str, object]:
    return {
        "id": str(conversation.id),
        "employee_id": str(conversation.employee_id),
        "title": conversation.title,
        "created_at": to_database_datetime(conversation.created_at),
        "updated_at": to_database_datetime(conversation.updated_at),
    }


def _message_values(message: Message) -> dict[str, object]:
    return {
        "id": str(message.id),
        "conversation_id": str(message.conversation_id),
        "sequence_number": message.sequence_number,
        "role": message.role.value,
        "content": message.content,
        "status": message.status.value,
        "error_code": message.error_code,
        "created_at": to_database_datetime(message.created_at),
        "updated_at": to_database_datetime(message.updated_at),
    }


def _citation_rows(message: Message) -> list[MessageCitationRow]:
    return [
        MessageCitationRow(
            message_id=str(message.id),
            position=citation.position,
            knowledge_base_id=citation.knowledge_base_id,
            chunk_id=citation.chunk_id,
            document_id=citation.document_id,
            document_name=citation.document_name,
            content=citation.content,
            score=citation.score,
        )
        for citation in message.citations
    ]


def _to_conversation(row: ConversationRow) -> Conversation:
    return Conversation(
        id=UUID(row.id),
        employee_id=UUID(row.employee_id),
        title=row.title,
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )


def _to_message(row: MessageRow, citations: tuple[Citation, ...]) -> Message:
    return Message(
        id=UUID(row.id),
        conversation_id=UUID(row.conversation_id),
        sequence_number=row.sequence_number,
        role=MessageRole(row.role),
        content=row.content,
        status=MessageStatus(row.status),
        citations=citations,
        error_code=row.error_code,
        created_at=from_database_datetime(row.created_at),
        updated_at=from_database_datetime(row.updated_at),
    )


def _to_citation(row: MessageCitationRow) -> Citation:
    return Citation(
        position=row.position,
        knowledge_base_id=row.knowledge_base_id,
        chunk_id=row.chunk_id,
        document_id=row.document_id,
        document_name=row.document_name,
        content=row.content,
        score=row.score,
    )


def _is_primary_conflict(error: IntegrityError) -> bool:
    return _has_constraint(error, "PRIMARY")


def _has_constraint(error: IntegrityError, constraint: str) -> bool:
    return constraint in str(error.orig)
