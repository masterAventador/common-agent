from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import Any, cast
from uuid import UUID

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    ConversationRow,
    MessageCitationRow,
    MessageRow,
)
from common_agent.adapters.persistence.tasks import SqlAlchemyTaskSubmission
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.domain.conversation import (
    Citation,
    Conversation,
    ConversationSource,
    Message,
    MessageRole,
    MessageStatus,
)
from common_agent.pagination import PageAnchor, PageSlice, canonical_uuid_search
from common_agent.ports.conversations import (
    ConversationAlreadyExists,
    ConversationRepository,
    MessageAlreadyExists,
    MessageRepository,
    MessageSequenceAlreadyExists,
)
from common_agent.tasks import TaskSubmission
from common_agent.tenancy.context import current_tenant


class SqlAlchemyConversationRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self._session = session
        self._tenant_id = str(tenant_id or current_tenant().tenant_id)

    async def list(self) -> tuple[Conversation, ...]:
        result = await self._session.scalars(
            select(ConversationRow)
            .where(ConversationRow.tenant_id == self._tenant_id)
            .order_by(
                ConversationRow.updated_at.desc(),
                ConversationRow.id,
            )
        )
        return tuple(_to_conversation(row) for row in result)

    async def list_for_employee(self, employee_id: UUID) -> tuple[Conversation, ...]:
        result = await self._session.scalars(
            select(ConversationRow)
            .where(
                ConversationRow.employee_id == str(employee_id),
                ConversationRow.tenant_id == self._tenant_id,
            )
            .order_by(ConversationRow.updated_at.desc(), ConversationRow.id)
        )
        return tuple(_to_conversation(row) for row in result)

    async def page(
        self,
        *,
        limit: int,
        search: str,
        after: PageAnchor | None,
        employee_id: UUID | None,
        source: ConversationSource | None = None,
    ) -> PageSlice[Conversation]:
        statement = select(ConversationRow).where(ConversationRow.tenant_id == self._tenant_id)
        if employee_id is not None:
            statement = statement.where(ConversationRow.employee_id == str(employee_id))
        if source is not None:
            statement = statement.where(ConversationRow.source == source.value)
        if search:
            searched_id = canonical_uuid_search(search)
            statement = statement.where(
                ConversationRow.id == searched_id
                if searched_id is not None
                else ConversationRow.title.startswith(search, autoescape=True)
            )
        if after is not None:
            after_time = to_database_datetime(after.created_at)
            statement = statement.where(
                or_(
                    ConversationRow.created_at < after_time,
                    and_(
                        ConversationRow.created_at == after_time,
                        ConversationRow.id < after.id,
                    ),
                )
            )
        rows = tuple(
            await self._session.scalars(
                statement.order_by(
                    ConversationRow.created_at.desc(),
                    ConversationRow.id.desc(),
                ).limit(limit + 1)
            )
        )
        return PageSlice(
            items=tuple(_to_conversation(row) for row in rows[:limit]),
            has_more=len(rows) > limit,
        )

    async def get(self, conversation_id: UUID) -> Conversation | None:
        row = await self._session.scalar(
            select(ConversationRow).where(
                ConversationRow.id == str(conversation_id),
                ConversationRow.tenant_id == self._tenant_id,
            )
        )
        return None if row is None else _to_conversation(row)

    async def add(self, conversation: Conversation) -> None:
        self._session.add(
            ConversationRow(tenant_id=self._tenant_id, **_conversation_values(conversation))
        )
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
                .where(
                    ConversationRow.id == str(conversation.id),
                    ConversationRow.tenant_id == self._tenant_id,
                )
                .values(
                    title=conversation.title,
                    model_configuration_id=(
                        None
                        if conversation.model_configuration_id is None
                        else str(conversation.model_configuration_id)
                    ),
                    updated_at=to_database_datetime(conversation.updated_at),
                )
            ),
        )
        return bool(result.rowcount)

    async def delete(self, conversation_id: UUID) -> bool:
        result = cast(
            CursorResult[Any],
            await self._session.execute(
                delete(ConversationRow).where(
                    ConversationRow.id == str(conversation_id),
                    ConversationRow.tenant_id == self._tenant_id,
                )
            ),
        )
        return bool(result.rowcount)


class SqlAlchemyMessageRepository:
    def __init__(self, session: AsyncSession, tenant_id: UUID | None = None) -> None:
        self._session = session
        self._tenant_id = str(tenant_id or current_tenant().tenant_id)

    async def list_for_conversation(self, conversation_id: UUID) -> tuple[Message, ...]:
        rows = tuple(
            await self._session.scalars(
                select(MessageRow)
                .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
                .where(
                    MessageRow.conversation_id == str(conversation_id),
                    ConversationRow.tenant_id == self._tenant_id,
                )
                .order_by(MessageRow.sequence_number, MessageRow.id)
            )
        )
        citations = await self._citations_for(rows)
        return tuple(_to_message(row, citations.get(row.id, ())) for row in rows)

    async def list_active(self) -> tuple[Message, ...]:
        rows = tuple(
            await self._session.scalars(
                select(MessageRow)
                .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
                .where(
                    ConversationRow.tenant_id == self._tenant_id,
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
        row = await self._session.scalar(
            select(MessageRow)
            .join(ConversationRow, ConversationRow.id == MessageRow.conversation_id)
            .where(
                MessageRow.id == str(message_id),
                ConversationRow.tenant_id == self._tenant_id,
            )
        )
        if row is None:
            return None
        citations = await self._citations_for((row,))
        return _to_message(row, citations.get(row.id, ()))

    async def add(self, message: Message) -> None:
        existing = await self.get(message.id)
        if existing is not None:
            raise MessageAlreadyExists
        conversation_exists = await self._session.scalar(
            select(ConversationRow.id).where(
                ConversationRow.id == str(message.conversation_id),
                ConversationRow.tenant_id == self._tenant_id,
            )
        )
        if conversation_exists is None:
            raise PermissionError("tenant_access_denied")
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
                .where(
                    MessageRow.id == str(message.id),
                    MessageRow.conversation_id.in_(
                        select(ConversationRow.id).where(
                            ConversationRow.tenant_id == self._tenant_id
                        )
                    ),
                )
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
    def __init__(self, database: Database, tenant_id: UUID) -> None:
        self._database = database
        self._tenant_id = tenant_id
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._conversations: ConversationRepository | None = None
        self._messages: MessageRepository | None = None
        self._tasks: TaskSubmission | None = None

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

    @property
    def tasks(self) -> TaskSubmission:
        if self._tasks is None:
            raise RuntimeError("会话事务尚未开始")
        return self._tasks

    async def __aenter__(self) -> SqlAlchemyConversationUnitOfWork:
        if self._context is not None:
            raise RuntimeError("会话事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._conversations = SqlAlchemyConversationRepository(session, self._tenant_id)
        self._messages = SqlAlchemyMessageRepository(session, self._tenant_id)
        self._tasks = SqlAlchemyTaskSubmission(session)
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
        self._tasks = None
        if context is None:
            raise RuntimeError("会话事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        session = self._session
        if session is None:
            raise RuntimeError("会话事务尚未开始")
        await session.commit()


class SqlAlchemyConversationUnitOfWorkFactory:
    def __init__(
        self,
        database: Database,
        tenant_id_provider: Callable[[], UUID] | None = None,
    ) -> None:
        self._database = database
        self._tenant_id_provider = tenant_id_provider or (lambda: current_tenant().tenant_id)

    def __call__(self) -> SqlAlchemyConversationUnitOfWork:
        return SqlAlchemyConversationUnitOfWork(self._database, self._tenant_id_provider())


def _conversation_values(conversation: Conversation) -> dict[str, object]:
    return {
        "id": str(conversation.id),
        "source": conversation.source.value,
        "employee_id": (
            None if conversation.employee_id is None else str(conversation.employee_id)
        ),
        "model_configuration_id": (
            None
            if conversation.model_configuration_id is None
            else str(conversation.model_configuration_id)
        ),
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
        "model_configuration_id": (
            None if message.model_configuration_id is None else str(message.model_configuration_id)
        ),
        "model_identifier": message.model_identifier,
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
        source=ConversationSource(row.source),
        employee_id=None if row.employee_id is None else UUID(row.employee_id),
        model_configuration_id=(
            None if row.model_configuration_id is None else UUID(row.model_configuration_id)
        ),
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
        model_configuration_id=(
            None if row.model_configuration_id is None else UUID(row.model_configuration_id)
        ),
        model_identifier=row.model_identifier,
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
