from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from common_agent.adapters.persistence.conversations import (
    SqlAlchemyConversationRepository,
    SqlAlchemyConversationUnitOfWorkFactory,
    SqlAlchemyMessageRepository,
)
from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.employees import SqlAlchemyEmployeeRepository
from common_agent.domain.conversation import Citation, Conversation, Message
from common_agent.domain.employee import Employee
from common_agent.ports.conversations import (
    ConversationAlreadyExists,
    MessageAlreadyExists,
    MessageSequenceAlreadyExists,
)
from tests.support.conversations import delete_conversations
from tests.support.employees import delete_employees
from tests.support.settings import TEST_DATABASE_URL


def _database_url() -> str:
    return os.environ.get("TEST_PLATFORM_DATABASE_URL", TEST_DATABASE_URL)


@asynccontextmanager
async def _database() -> AsyncIterator[Database]:
    database = Database(_database_url())
    await database.start()
    try:
        yield database
    finally:
        await database.stop()


def _records() -> tuple[Employee, Conversation, Message, Message]:
    employee = Employee.create(name=f"conversation-{uuid4().hex}", system_prompt="通用指令")
    conversation = Conversation.create(employee_id=employee.id, title="通用会话")
    user = Message.create_user(
        conversation_id=conversation.id,
        sequence_number=1,
        content="第一条问题",
        now=conversation.created_at + timedelta(microseconds=1),
    )
    assistant = Message.create_assistant(
        conversation_id=conversation.id,
        sequence_number=2,
        now=user.created_at + timedelta(microseconds=1),
    )
    assistant = assistant.append_delta(
        "可靠回答",
        updated_at=assistant.updated_at + timedelta(microseconds=1),
    ).complete(
        citations=[
            Citation(
                position=1,
                knowledge_base_id="dataset-1",
                chunk_id="chunk-1",
                document_id="document-1",
                document_name="通用文档.md",
                content="支持该回答的可靠片段",
                score=0.88,
            )
        ],
        updated_at=assistant.updated_at + timedelta(microseconds=2),
    )
    return employee, conversation, user, assistant


def test_conversation_and_messages_survive_database_restart_with_citations() -> None:
    employee, conversation, user, assistant = _records()

    async def exercise() -> tuple[Conversation | None, tuple[Message, ...]]:
        try:
            async with _database() as first, first.session() as session:
                await SqlAlchemyEmployeeRepository(session).add(employee)
                await SqlAlchemyConversationRepository(session).add(conversation)
                messages = SqlAlchemyMessageRepository(session)
                await messages.add(user)
                await messages.add(assistant)
                await session.commit()

            async with _database() as restarted, restarted.session() as session:
                restored_conversation = await SqlAlchemyConversationRepository(session).get(
                    conversation.id
                )
                restored_messages = await SqlAlchemyMessageRepository(
                    session
                ).list_for_conversation(conversation.id)
                return restored_conversation, restored_messages
        finally:
            async with _database() as cleanup_database:
                await delete_conversations(cleanup_database, conversation.id)
                await delete_employees(cleanup_database, employee.id)

    assert asyncio.run(exercise()) == (conversation, (user, assistant))


def test_repositories_list_and_update_without_owning_transactions() -> None:
    employee, conversation, user, assistant = _records()
    renamed = conversation.rename(
        "刷新后的标题",
        updated_at=assistant.updated_at + timedelta(microseconds=1),
    )
    pending = Message.create_assistant(
        conversation_id=conversation.id,
        sequence_number=3,
        now=renamed.updated_at + timedelta(microseconds=1),
    )
    streaming = pending.append_delta(
        "部分内容",
        updated_at=pending.updated_at + timedelta(microseconds=1),
    )

    async def exercise() -> tuple[tuple[Conversation, ...], tuple[Message, ...], Message | None]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    conversation_repository = SqlAlchemyConversationRepository(session)
                    message_repository = SqlAlchemyMessageRepository(session)
                    await conversation_repository.add(conversation)
                    await message_repository.add(assistant)
                    await message_repository.add(user)
                    await message_repository.add(pending)
                    await session.commit()

                async with database.session() as session:
                    assert await SqlAlchemyConversationRepository(session).update(renamed) is True
                    assert await SqlAlchemyMessageRepository(session).update(streaming) is True
                    await session.commit()

                async with database.session() as session:
                    stored_conversations = await SqlAlchemyConversationRepository(
                        session
                    ).list_for_employee(employee.id)
                    stored_messages = await SqlAlchemyMessageRepository(
                        session
                    ).list_for_conversation(conversation.id)
                    missing = await SqlAlchemyMessageRepository(session).get(uuid4())
                    return stored_conversations, stored_messages, missing
            finally:
                await delete_conversations(database, conversation.id)
                await delete_employees(database, employee.id)

    conversations, messages, missing = asyncio.run(exercise())
    assert conversations == (renamed,)
    assert messages == (user, assistant, streaming)
    assert missing is None


def test_repositories_list_all_conversations_and_active_assistant_messages() -> None:
    employee = Employee.create(name=f"conversation-list-{uuid4().hex}", system_prompt="通用指令")
    older = Conversation.create(employee_id=employee.id, title="较早会话")
    newer = Conversation.create(
        employee_id=employee.id,
        title="较新会话",
        now=older.created_at + timedelta(microseconds=1),
    )
    pending = Message.create_assistant(
        conversation_id=older.id,
        sequence_number=2,
        now=newer.created_at + timedelta(microseconds=1),
    )
    streaming = Message.create_assistant(
        conversation_id=newer.id,
        sequence_number=2,
        now=pending.created_at + timedelta(microseconds=1),
    ).append_delta(
        "生成中",
        updated_at=pending.created_at + timedelta(microseconds=2),
    )

    async def exercise() -> tuple[tuple[Conversation, ...], tuple[Message, ...]]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    conversation_repository = SqlAlchemyConversationRepository(session)
                    messages = SqlAlchemyMessageRepository(session)
                    await conversation_repository.add(older)
                    await conversation_repository.add(newer)
                    await messages.add(pending)
                    await messages.add(streaming)
                    await session.commit()

                async with database.session() as session:
                    stored_conversations = await SqlAlchemyConversationRepository(session).list()
                    active = await SqlAlchemyMessageRepository(session).list_active()
                    own_ids = {older.id, newer.id}
                    return (
                        tuple(item for item in stored_conversations if item.id in own_ids),
                        tuple(item for item in active if item.conversation_id in own_ids),
                    )
            finally:
                await delete_conversations(database, older.id, newer.id)
                await delete_employees(database, employee.id)

    conversations, active = asyncio.run(exercise())
    assert conversations == (newer, older)
    assert active == (pending, streaming)


def test_conversation_transaction_rollback_leaves_no_partial_graph() -> None:
    employee, conversation, user, _ = _records()

    async def exercise() -> tuple[Conversation | None, tuple[Message, ...]]:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()

                with pytest.raises(RuntimeError, match="force rollback"):
                    async with database.session() as session:
                        await SqlAlchemyConversationRepository(session).add(conversation)
                        await SqlAlchemyMessageRepository(session).add(user)
                        raise RuntimeError("force rollback")

                async with database.session() as session:
                    conversation_result = await SqlAlchemyConversationRepository(session).get(
                        conversation.id
                    )
                    message_result = await SqlAlchemyMessageRepository(
                        session
                    ).list_for_conversation(conversation.id)
                    return conversation_result, message_result
            finally:
                await delete_conversations(database, conversation.id)
                await delete_employees(database, employee.id)

    assert asyncio.run(exercise()) == (None, ())


def test_repository_maps_duplicate_conversation_message_and_sequence() -> None:
    employee, conversation, user, _ = _records()
    same_sequence = Message.create_assistant(
        conversation_id=conversation.id,
        sequence_number=user.sequence_number,
        now=user.created_at + timedelta(microseconds=1),
    )

    async def exercise() -> None:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await SqlAlchemyConversationRepository(session).add(conversation)
                    await SqlAlchemyMessageRepository(session).add(user)
                    await session.commit()

                with pytest.raises(ConversationAlreadyExists):
                    async with database.session() as session:
                        await SqlAlchemyConversationRepository(session).add(conversation)

                with pytest.raises(MessageAlreadyExists):
                    async with database.session() as session:
                        await SqlAlchemyMessageRepository(session).add(user)

                with pytest.raises(MessageSequenceAlreadyExists):
                    async with database.session() as session:
                        await SqlAlchemyMessageRepository(session).add(same_sequence)
            finally:
                await delete_conversations(database, conversation.id)
                await delete_employees(database, employee.id)

    asyncio.run(exercise())


def test_conversation_unit_of_work_commits_graph_and_hides_repositories_outside_context() -> None:
    employee, conversation, user, _ = _records()

    async def exercise() -> tuple[Conversation | None, tuple[Message, ...]]:
        async with _database() as database:
            unit_of_work = SqlAlchemyConversationUnitOfWorkFactory(database)()
            with pytest.raises(RuntimeError, match="尚未开始"):
                _ = unit_of_work.conversations
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await session.commit()

                async with unit_of_work:
                    await unit_of_work.conversations.add(conversation)
                    await unit_of_work.messages.add(user)
                    await unit_of_work.commit()

                with pytest.raises(RuntimeError, match="尚未开始"):
                    _ = unit_of_work.messages

                async with database.session() as session:
                    stored_conversation = await SqlAlchemyConversationRepository(session).get(
                        conversation.id
                    )
                    stored_messages = await SqlAlchemyMessageRepository(
                        session
                    ).list_for_conversation(conversation.id)
                    return stored_conversation, stored_messages
            finally:
                await delete_conversations(database, conversation.id)
                await delete_employees(database, employee.id)

    assert asyncio.run(exercise()) == (conversation, (user,))


@pytest.mark.parametrize(
    ("role", "status", "content", "error_code", "sequence_number"),
    [
        ("user", "pending", "问题", None, 1),
        ("assistant", "failed", "", None, 1),
        ("assistant", "pending", "不应存在的内容", None, 1),
        ("assistant", "unknown", "", None, 1),
        ("assistant", "pending", "", None, 0),
    ],
)
def test_mysql_constraints_reject_invalid_direct_message_states(
    role: str,
    status: str,
    content: str,
    error_code: str | None,
    sequence_number: int,
) -> None:
    employee, conversation, _, _ = _records()

    async def exercise() -> None:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await SqlAlchemyConversationRepository(session).add(conversation)
                    await session.commit()

                with pytest.raises(DBAPIError):
                    async with database.session() as session:
                        await session.execute(
                            text(
                                "INSERT INTO messages "
                                "(id, conversation_id, sequence_number, role, content, status, "
                                "error_code, created_at, updated_at) VALUES "
                                "(:id, :conversation_id, :sequence_number, :role, :content, "
                                ":status, :error_code, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
                            ),
                            {
                                "id": str(uuid4()),
                                "conversation_id": str(conversation.id),
                                "sequence_number": sequence_number,
                                "role": role,
                                "content": content,
                                "status": status,
                                "error_code": error_code,
                            },
                        )
            finally:
                await delete_conversations(database, conversation.id)
                await delete_employees(database, employee.id)

    asyncio.run(exercise())


def test_mysql_constraints_reject_invalid_direct_citation_score() -> None:
    employee, conversation, _, assistant = _records()

    async def exercise() -> None:
        async with _database() as database:
            try:
                async with database.session() as session:
                    await SqlAlchemyEmployeeRepository(session).add(employee)
                    await SqlAlchemyConversationRepository(session).add(conversation)
                    await SqlAlchemyMessageRepository(session).add(assistant)
                    await session.commit()

                with pytest.raises(DBAPIError):
                    async with database.session() as session:
                        await session.execute(
                            text(
                                "INSERT INTO message_citations "
                                "(message_id, position, knowledge_base_id, chunk_id, document_id, "
                                "document_name, content, score) VALUES "
                                "(:message_id, 1, 'dataset', 'chunk', 'document', "
                                "'通用文档', '可靠片段', 1.5)"
                            ),
                            {"message_id": str(assistant.id)},
                        )
            finally:
                await delete_conversations(database, conversation.id)
                await delete_employees(database, employee.id)

    asyncio.run(exercise())


def test_mysql_foreign_keys_reject_orphaned_conversations_messages_and_citations() -> None:
    orphaned_conversation = Conversation.create(employee_id=uuid4(), title="孤立会话")
    orphaned_message = Message.create_user(
        conversation_id=uuid4(),
        sequence_number=1,
        content="孤立消息",
    )

    async def exercise() -> None:
        async with _database() as database:
            with pytest.raises(DBAPIError):
                async with database.session() as session:
                    await SqlAlchemyConversationRepository(session).add(orphaned_conversation)

            with pytest.raises(PermissionError, match="tenant_access_denied"):
                async with database.session() as session:
                    await SqlAlchemyMessageRepository(session).add(orphaned_message)

            with pytest.raises(DBAPIError):
                async with database.session() as session:
                    await session.execute(
                        text(
                            "INSERT INTO message_citations "
                            "(message_id, position, knowledge_base_id, chunk_id, document_id, "
                            "document_name, content, score) VALUES "
                            "(:message_id, 1, 'dataset', 'chunk', 'document', "
                            "'通用文档', '可靠片段', 0.8)"
                        ),
                        {"message_id": str(uuid4())},
                    )

    asyncio.run(exercise())
