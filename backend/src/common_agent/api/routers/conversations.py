from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.conversations.events import (
    ConversationEvent,
    ConversationEventBroker,
    ConversationEventKind,
    EventHistoryUnavailable,
)
from common_agent.conversations.service import (
    ConversationBusy,
    ConversationNotFound,
    ConversationRequestConflict,
    ConversationService,
    ConversationServiceError,
    GenerationNotActive,
    MessageNotFound,
    MessageRequestConflict,
    MessageRetryNotAllowed,
    StopAccepted,
    TurnAccepted,
)
from common_agent.domain.conversation import (
    CONVERSATION_TITLE_MAX_LENGTH,
    MESSAGE_CONTENT_MAX_LENGTH,
    Citation,
    Conversation,
    ConversationValidationError,
    Message,
    MessageRole,
    MessageStatus,
)
from common_agent.employees.service import EmployeeNotFound

router = APIRouter(tags=["conversations"])

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


class ConversationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    employee_id: UUID
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
    created_at: datetime
    updated_at: datetime


class TurnAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn_id: UUID
    user_message: MessageResponse
    assistant_message: MessageResponse
    retry: bool


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


def _application(request: Request) -> ConversationService:
    application = getattr(request.app.state, "conversations", None)
    if not isinstance(application, ConversationService):
        raise AppError(
            code="conversation_service_unavailable",
            message="会话服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def _event_broker(request: Request) -> ConversationEventBroker:
    broker = getattr(request.app.state, "conversation_events", None)
    if not isinstance(broker, ConversationEventBroker):
        raise AppError(
            code="conversation_service_unavailable",
            message="会话服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return broker


def _conversation_response(conversation: Conversation) -> ConversationResponse:
    return ConversationResponse.model_validate(conversation)


def _citation_response(citation: Citation) -> CitationResponse:
    return CitationResponse.model_validate(citation)


def _message_response(message: Message) -> MessageResponse:
    return MessageResponse(
        id=message.id,
        conversation_id=message.conversation_id,
        sequence_number=message.sequence_number,
        role=message.role,
        content=message.content,
        status=message.status,
        citations=[_citation_response(citation) for citation in message.citations],
        error_code=message.error_code,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


def _turn_response(turn: TurnAccepted) -> TurnAcceptedResponse:
    return TurnAcceptedResponse(
        turn_id=turn.turn_id,
        user_message=_message_response(turn.user_message),
        assistant_message=_message_response(turn.assistant_message),
        retry=turn.retry,
    )


def _stop_response(stop: StopAccepted) -> StopAcceptedResponse:
    return StopAcceptedResponse.model_validate(stop)


def _event_response(event: ConversationEvent) -> ConversationEventResponse:
    return ConversationEventResponse(
        sequence=event.sequence,
        conversation_id=event.conversation_id,
        turn_id=event.turn_id,
        message_id=event.message_id,
        type=event.kind,
        delta=event.delta,
        retry=event.retry,
        message=_message_response(event.message),
        occurred_at=event.occurred_at,
    )


def _service_error(error: Exception) -> AppError:
    if isinstance(error, (ConversationNotFound, MessageNotFound, EmployeeNotFound)):
        return AppError(error.code, str(error), 404, error.retryable)
    if isinstance(
        error,
        (
            ConversationBusy,
            ConversationRequestConflict,
            MessageRequestConflict,
            MessageRetryNotAllowed,
            GenerationNotActive,
        ),
    ):
        return AppError(error.code, str(error), 409, error.retryable)
    if isinstance(error, ConversationValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    raise TypeError("unsupported conversation application error")


@router.get(
    "/api/v1/conversations",
    response_model=list[ConversationResponse],
    responses={503: {"model": ErrorEnvelope}},
)
async def list_conversations(
    request: Request,
    employee_id: Annotated[UUID | None, Query()] = None,
) -> list[ConversationResponse]:
    conversations = await _application(request).list(employee_id=employee_id)
    return [_conversation_response(conversation) for conversation in conversations]


@router.post(
    "/api/v1/conversations",
    status_code=status.HTTP_201_CREATED,
    response_model=ConversationResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def create_conversation(
    request: Request,
    body: CreateConversationBody,
) -> ConversationResponse:
    try:
        conversation = await _application(request).create(
            employee_id=body.employee_id,
            title=body.title,
            conversation_id=body.conversation_id,
        )
    except (ConversationServiceError, ConversationValidationError, EmployeeNotFound) as error:
        raise _service_error(error) from error
    return _conversation_response(conversation)


@router.get(
    "/api/v1/conversations/{conversation_id}/messages",
    response_model=list[MessageResponse],
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def list_messages(request: Request, conversation_id: UUID) -> list[MessageResponse]:
    try:
        messages = await _application(request).list_messages(conversation_id)
    except ConversationNotFound as error:
        raise _service_error(error) from error
    return [_message_response(message) for message in messages]


@router.post(
    "/api/v1/conversations/{conversation_id}/messages",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TurnAcceptedResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def send_message(
    request: Request,
    conversation_id: UUID,
    body: SendMessageBody,
) -> TurnAcceptedResponse:
    try:
        turn = await _application(request).send(
            conversation_id,
            user_message_id=body.message_id,
            content=body.content,
        )
    except (ConversationServiceError, ConversationValidationError) as error:
        raise _service_error(error) from error
    return _turn_response(turn)


@router.post(
    "/api/v1/conversations/{conversation_id}/stop",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=StopAcceptedResponse,
    responses={
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def stop_generation(request: Request, conversation_id: UUID) -> StopAcceptedResponse:
    try:
        stopped = await _application(request).stop(conversation_id)
    except GenerationNotActive as error:
        raise _service_error(error) from error
    return _stop_response(stopped)


@router.post(
    "/api/v1/messages/{message_id}/retry",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=TurnAcceptedResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def retry_message(request: Request, message_id: UUID) -> TurnAcceptedResponse:
    try:
        turn = await _application(request).retry(message_id)
    except ConversationServiceError as error:
        raise _service_error(error) from error
    return _turn_response(turn)


@router.get(
    "/api/v1/conversations/{conversation_id}/events",
    response_model=ConversationEventResponse,
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "会话事件流",
            "content": {
                "text/event-stream": {
                    "schema": {"$ref": "#/components/schemas/ConversationEventResponse"}
                }
            },
        },
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def stream_events(
    request: Request,
    conversation_id: UUID,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    try:
        await _application(request).list_messages(conversation_id)
    except ConversationNotFound as error:
        raise _service_error(error) from error
    resume_after = _resume_sequence(after_sequence, last_event_id)
    broker = _event_broker(request)
    try:
        await broker.validate_resume(conversation_id, after_sequence=resume_after)
    except EventHistoryUnavailable as error:
        raise AppError(error.code, str(error), 409, error.retryable) from error

    return StreamingResponse(
        _event_source(request, broker, conversation_id, resume_after),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


def _resume_sequence(after_sequence: int, last_event_id: str | None) -> int:
    if after_sequence or last_event_id is None:
        return after_sequence
    try:
        parsed = int(last_event_id)
    except ValueError:
        raise AppError("validation_error", "请求参数不合法", 422, False) from None
    if parsed < 0:
        raise AppError("validation_error", "请求参数不合法", 422, False)
    return parsed


async def _event_source(
    request: Request,
    broker: ConversationEventBroker,
    conversation_id: UUID,
    after_sequence: int,
) -> AsyncIterator[str]:
    stream = broker.stream(conversation_id, after_sequence=after_sequence)
    try:
        async for event in stream:
            if await request.is_disconnected():
                return
            response = _event_response(event)
            yield (
                f"id: {event.sequence}\n"
                f"event: {event.kind.value}\n"
                f"data: {response.model_dump_json()}\n\n"
            )
    finally:
        await stream.aclose()
