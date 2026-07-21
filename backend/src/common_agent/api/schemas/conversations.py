from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from common_agent.conversations.contracts import (
    ConversationTurnAccepted,
    StopAccepted,
    TurnAccepted,
)
from common_agent.conversations.events import ConversationEvent, ConversationEventKind
from common_agent.domain.conversation import (
    CONVERSATION_TITLE_MAX_LENGTH,
    MESSAGE_CONTENT_MAX_LENGTH,
    Conversation,
    ConversationSource,
    Message,
    MessageRole,
    MessageStatus,
)

ConversationTitle = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=CONVERSATION_TITLE_MAX_LENGTH,
    ),
]
MessageContent = Annotated[
    str,
    StringConstraints(min_length=1, max_length=MESSAGE_CONTENT_MAX_LENGTH),
]


class CreateConversationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    employee_id: UUID
    title: ConversationTitle
    conversation_id: UUID | None = None


class SendMessageBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message_id: UUID
    content: MessageContent
    model_configuration_id: UUID | None = None


class CreateConversationTurnBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation_id: UUID
    message_id: UUID
    employee_id: UUID | None = None
    model_configuration_id: UUID
    content: MessageContent


class ConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    source: ConversationSource
    employee_id: UUID | None
    model_configuration_id: UUID | None
    title: str
    created_at: datetime
    updated_at: datetime


class CitationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    position: int
    knowledge_base_id: str
    chunk_id: str
    document_id: str
    document_name: str
    content: str
    score: float


class MessageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    conversation_id: UUID
    sequence_number: int
    role: MessageRole
    content: str
    status: MessageStatus
    citations: list[CitationResponse]
    error_code: str | None
    model_configuration_id: UUID | None
    model_identifier: str | None
    created_at: datetime
    updated_at: datetime


class TurnAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
    retry: bool


class ConversationTurnAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    conversation: ConversationResponse
    turn: TurnAcceptedResponse


class StopAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    turn_id: UUID
    assistant_message_id: UUID


class ConversationEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    sequence: int
    conversation_id: UUID
    turn_id: UUID
    message_id: UUID
    type: ConversationEventKind
    delta: str | None
    retry: bool
    message: MessageResponse
    occurred_at: datetime


def conversation_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse.model_validate(conversation)


def message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sequence_number=message.sequence_number,
        role=message.role,
        content=message.content,
        status=message.status,
        citations=[CitationResponse.model_validate(citation) for citation in message.citations],
        error_code=message.error_code,
        model_configuration_id=message.model_configuration_id,
        model_identifier=message.model_identifier,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def turn_response(turn: TurnAccepted) -> TurnAcceptedResponse:
    return TurnAcceptedResponse(
        turn_id=turn.turn_id,
        user_message=message_response(turn.user_message),
        assistant_message=message_response(turn.assistant_message),
        retry=turn.retry,
    )


def stop_response(stop: StopAccepted) -> StopAcceptedResponse:
    return StopAcceptedResponse.model_validate(stop)


def conversation_turn_response(
    accepted: ConversationTurnAccepted,
) -> ConversationTurnAcceptedResponse:
    return ConversationTurnAcceptedResponse(
        conversation=conversation_response(accepted.conversation),
        turn=turn_response(accepted.turn),
    )


def conversation_event_response(event: ConversationEvent) -> ConversationEventResponse:
    return ConversationEventResponse(
        sequence=event.sequence,
        conversation_id=event.conversation_id,
        turn_id=event.turn_id,
        message_id=event.message_id,
        type=event.kind,
        delta=event.delta,
        retry=event.retry,
        message=message_response(event.message),
        occurred_at=event.occurred_at,
    )


__all__ = [
    "ConversationEventResponse",
    "ConversationResponse",
    "ConversationTurnAcceptedResponse",
    "CreateConversationBody",
    "CreateConversationTurnBody",
    "MessageResponse",
    "SendMessageBody",
    "StopAcceptedResponse",
    "TurnAcceptedResponse",
    "conversation_event_response",
    "conversation_response",
    "conversation_turn_response",
    "message_response",
    "stop_response",
    "turn_response",
]
