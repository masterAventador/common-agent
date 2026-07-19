from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from common_agent.domain.conversation import (
    CITATION_CONTENT_MAX_LENGTH,
    CONVERSATION_TITLE_MAX_LENGTH,
    MESSAGE_CONTENT_MAX_LENGTH,
    Citation,
    Conversation,
    ConversationValidationError,
    Message,
    MessageRole,
    MessageStatus,
    MessageTransitionError,
)


def test_conversation_create_normalizes_title_and_preserves_utc_timestamps() -> None:
    employee_id = uuid4()
    now = datetime.now(UTC)

    conversation = Conversation.create(
        employee_id=employee_id,
        title="  新会话  ",
        now=now,
    )

    assert isinstance(conversation.id, UUID)
    assert conversation.employee_id == employee_id
    assert conversation.title == "新会话"
    assert conversation.created_at == now
    assert conversation.updated_at == now


def test_conversation_rename_preserves_identity_and_rejects_time_reversal() -> None:
    conversation = Conversation.create(employee_id=uuid4(), title="原标题")
    changed_at = conversation.updated_at + timedelta(microseconds=1)

    changed = conversation.rename("  新标题  ", updated_at=changed_at)

    assert changed.id == conversation.id
    assert changed.employee_id == conversation.employee_id
    assert changed.created_at == conversation.created_at
    assert changed.updated_at == changed_at
    assert changed.title == "新标题"

    with pytest.raises(ConversationValidationError) as captured:
        changed.rename("再次修改", updated_at=conversation.updated_at)
    assert captured.value.field == "updated_at"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"conversation_id": "not-a-uuid"}, "id"),
        ({"employee_id": "not-a-uuid"}, "employee_id"),
        ({"title": "   "}, "title"),
        ({"title": "x" * (CONVERSATION_TITLE_MAX_LENGTH + 1)}, "title"),
        ({"now": datetime.now(UTC).replace(tzinfo=None)}, "created_at"),
    ],
)
def test_conversation_rejects_invalid_fields(overrides: dict[str, object], field: str) -> None:
    values: dict[str, object] = {"employee_id": uuid4(), "title": "通用会话"}
    values.update(overrides)

    with pytest.raises(ConversationValidationError) as captured:
        Conversation.create(**values)  # type: ignore[arg-type]

    assert captured.value.field == field


def test_user_message_is_immediately_completed_and_preserves_content() -> None:
    now = datetime.now(UTC)

    message = Message.create_user(
        conversation_id=uuid4(),
        sequence_number=1,
        content="  第一行\n第二行  ",
        now=now,
    )

    assert isinstance(message.id, UUID)
    assert message.role is MessageRole.USER
    assert message.status is MessageStatus.COMPLETED
    assert message.content == "  第一行\n第二行  "
    assert message.citations == ()
    assert message.error_code is None
    assert message.is_terminal is True
    assert message.created_at == now
    assert message.updated_at == now


def test_assistant_message_moves_through_streaming_to_completed_with_citations() -> None:
    created_at = datetime.now(UTC)
    message = Message.create_assistant(
        conversation_id=uuid4(),
        sequence_number=2,
        now=created_at,
    )
    first_delta_at = created_at + timedelta(microseconds=1)
    second_delta_at = first_delta_at + timedelta(microseconds=1)
    completed_at = second_delta_at + timedelta(microseconds=1)
    citation = Citation(
        position=1,
        knowledge_base_id="dataset-1",
        chunk_id="chunk-1",
        document_id="document-1",
        document_name="通用手册.md",
        content="用于回答的可靠片段",
        score=0.91,
    )

    streaming = message.append_delta("第一段", updated_at=first_delta_at)
    streaming = streaming.append_delta("\n第二段", updated_at=second_delta_at)
    completed = streaming.complete(citations=[citation], updated_at=completed_at)

    assert message.status is MessageStatus.PENDING
    assert message.content == ""
    assert streaming.status is MessageStatus.STREAMING
    assert completed.status is MessageStatus.COMPLETED
    assert completed.content == "第一段\n第二段"
    assert completed.citations == (citation,)
    assert completed.updated_at == completed_at
    assert completed.is_terminal is True


def test_assistant_message_records_failed_and_stopped_terminal_states() -> None:
    pending = Message.create_assistant(conversation_id=uuid4(), sequence_number=2)
    changed_at = pending.updated_at + timedelta(microseconds=1)

    failed = pending.fail(error_code="model_unavailable", updated_at=changed_at)
    stopped = pending.stop(updated_at=changed_at)

    assert failed.status is MessageStatus.FAILED
    assert failed.error_code == "model_unavailable"
    assert failed.is_terminal is True
    assert stopped.status is MessageStatus.STOPPED
    assert stopped.error_code is None
    assert stopped.is_terminal is True

    for terminal in (failed, stopped):
        with pytest.raises(MessageTransitionError):
            terminal.append_delta("晚到内容", updated_at=changed_at + timedelta(microseconds=1))


def test_message_rejects_invalid_state_combinations_and_transitions() -> None:
    user = Message.create_user(conversation_id=uuid4(), sequence_number=1, content="问题")
    assistant = Message.create_assistant(conversation_id=user.conversation_id, sequence_number=2)

    with pytest.raises(ConversationValidationError) as invalid_user_state:
        replace(user, status=MessageStatus.PENDING)
    assert invalid_user_state.value.field == "status"

    with pytest.raises(ConversationValidationError) as invalid_sequence:
        replace(assistant, sequence_number=0)
    assert invalid_sequence.value.field == "sequence_number"

    with pytest.raises(MessageTransitionError):
        assistant.append_delta(
            "内容",
            updated_at=assistant.updated_at - timedelta(microseconds=1),
        )


def test_message_rejects_empty_or_oversized_content_and_invalid_failure_code() -> None:
    with pytest.raises(ConversationValidationError) as empty_user:
        Message.create_user(conversation_id=uuid4(), sequence_number=1, content=" \n ")
    assert empty_user.value.field == "content"

    with pytest.raises(ConversationValidationError) as oversized:
        Message.create_user(
            conversation_id=uuid4(),
            sequence_number=1,
            content="x" * (MESSAGE_CONTENT_MAX_LENGTH + 1),
        )
    assert oversized.value.field == "content"

    assistant = Message.create_assistant(conversation_id=uuid4(), sequence_number=2)
    with pytest.raises(ConversationValidationError) as error_code:
        assistant.fail(error_code="   ")
    assert error_code.value.field == "error_code"

    with pytest.raises(ConversationValidationError) as empty_completion:
        assistant.complete()
    assert empty_completion.value.field == "content"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"position": 0}, "position"),
        ({"knowledge_base_id": "   "}, "knowledge_base_id"),
        ({"chunk_id": "   "}, "chunk_id"),
        ({"document_id": "   "}, "document_id"),
        ({"document_name": "   "}, "document_name"),
        ({"content": "   "}, "content"),
        ({"content": "x" * (CITATION_CONTENT_MAX_LENGTH + 1)}, "content"),
        ({"score": -0.01}, "score"),
        ({"score": 1.01}, "score"),
    ],
)
def test_citation_rejects_invalid_fields(overrides: dict[str, object], field: str) -> None:
    values: dict[str, object] = {
        "position": 1,
        "knowledge_base_id": "dataset-1",
        "chunk_id": "chunk-1",
        "document_id": "document-1",
        "document_name": "通用手册.md",
        "content": "可靠片段",
        "score": 0.8,
    }
    values.update(overrides)

    with pytest.raises(ConversationValidationError) as captured:
        Citation(**values)  # type: ignore[arg-type]

    assert captured.value.field == field
