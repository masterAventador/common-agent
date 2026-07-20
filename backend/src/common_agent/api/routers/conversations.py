from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.conversation_events import router as event_router
from common_agent.api.routers.services import conversation_service
from common_agent.api.schemas.conversations import (
    ConversationEventResponse,
    ConversationResponse,
    CreateConversationBody,
    MessageResponse,
    SendMessageBody,
    StopAcceptedResponse,
    TurnAcceptedResponse,
    conversation_response,
    message_response,
    stop_response,
    turn_response,
)
from common_agent.api.schemas.pagination import CursorPageResponse
from common_agent.conversations.service import (
    ConversationBusy,
    ConversationNotFound,
    ConversationRequestConflict,
    ConversationServiceError,
    GenerationNotActive,
    MessageNotFound,
    MessageRequestConflict,
    MessageRetryNotAllowed,
)
from common_agent.domain.conversation import ConversationValidationError
from common_agent.employees.service import EmployeeNotFound
from common_agent.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_CURSOR_LENGTH,
    MAX_PAGE_LIMIT,
    MAX_PAGE_SEARCH_LENGTH,
    InvalidPageCursor,
    ListPageRequest,
)

router = APIRouter(tags=["conversations"])
router.include_router(event_router)


def conversation_error(error: Exception) -> AppError:
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
    if isinstance(error, InvalidPageCursor):
        return AppError(error.code, error.message, 422, error.retryable)
    raise TypeError("unsupported conversation application error")


@router.get(
    "/api/v1/conversations",
    response_model=CursorPageResponse[ConversationResponse],
    responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def list_conversations(
    request: Request,
    employee_id: Annotated[UUID | None, Query()] = None,
    search: Annotated[str, Query(max_length=MAX_PAGE_SEARCH_LENGTH)] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_PAGE_CURSOR_LENGTH)] = None,
) -> CursorPageResponse[ConversationResponse]:
    try:
        page = await conversation_service(request).page(
            ListPageRequest(limit=limit, search=search, cursor=cursor),
            employee_id=employee_id,
        )
    except InvalidPageCursor as error:
        raise conversation_error(error) from error
    return CursorPageResponse(
        items=[conversation_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.delete(
    "/api/v1/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def delete_conversation(request: Request, conversation_id: UUID) -> None:
    try:
        await conversation_service(request).delete(conversation_id)
    except ConversationBusy as error:
        raise conversation_error(error) from error


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
        conversation = await conversation_service(request).create(
            employee_id=body.employee_id,
            title=body.title,
            conversation_id=body.conversation_id,
        )
    except (ConversationServiceError, ConversationValidationError, EmployeeNotFound) as error:
        raise conversation_error(error) from error
    return conversation_response(conversation)


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
        messages = await conversation_service(request).list_messages(conversation_id)
    except ConversationNotFound as error:
        raise conversation_error(error) from error
    return [message_response(message) for message in messages]


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
        turn = await conversation_service(request).send(
            conversation_id,
            user_message_id=body.message_id,
            content=body.content,
        )
    except (ConversationServiceError, ConversationValidationError) as error:
        raise conversation_error(error) from error
    return turn_response(turn)


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
        stopped = await conversation_service(request).stop(conversation_id)
    except GenerationNotActive as error:
        raise conversation_error(error) from error
    return stop_response(stopped)


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
        turn = await conversation_service(request).retry(message_id)
    except ConversationServiceError as error:
        raise conversation_error(error) from error
    return turn_response(turn)


__all__ = ["ConversationEventResponse", "router"]
