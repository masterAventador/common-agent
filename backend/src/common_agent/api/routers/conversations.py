from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from common_agent.api.audit import mark_audit_resource
from common_agent.api.errors import ErrorEnvelope
from common_agent.api.routers.conversation_errors import conversation_error
from common_agent.api.routers.conversation_events import router as event_router
from common_agent.api.routers.conversation_history import router as history_router
from common_agent.api.routers.services import conversation_service
from common_agent.api.schemas.conversations import (
    ConversationEventResponse,
    ConversationResponse,
    ConversationTurnAcceptedResponse,
    CreateConversationBody,
    CreateConversationTurnBody,
    MessageResponse,
    SendMessageBody,
    StopAcceptedResponse,
    TurnAcceptedResponse,
    conversation_response,
    conversation_turn_response,
    message_response,
    stop_response,
    turn_response,
)
from common_agent.audit import AuditResourceType
from common_agent.conversations.contracts import (
    ConversationNotFound,
    ConversationServiceError,
    GenerationNotActive,
)
from common_agent.domain.conversation import ConversationValidationError
from common_agent.employees.service import EmployeeNotFound
from common_agent.model_configurations.service import ModelConfigurationNotFound
from common_agent.tools.models import ToolGrantSelection, ToolValidationError
from common_agent.tools.service import ToolServiceError

router = APIRouter(tags=["conversations"])
router.include_router(event_router)
router.include_router(history_router)


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


@router.post(
    "/api/v1/conversation-turns",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=ConversationTurnAcceptedResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def create_conversation_turn(
    request: Request,
    body: CreateConversationTurnBody,
) -> ConversationTurnAcceptedResponse:
    try:
        accepted = await conversation_service(request).create_first_turn(
            conversation_id=body.conversation_id,
            user_message_id=body.message_id,
            employee_id=body.employee_id,
            model_configuration_id=body.model_configuration_id,
            content=body.content,
            tool_selection=ToolGrantSelection(
                collection_ids=tuple(body.tool_collection_ids),
                capability_ids=tuple(body.tool_capability_ids),
            ),
        )
    except (
        ConversationServiceError,
        ConversationValidationError,
        EmployeeNotFound,
        ModelConfigurationNotFound,
        ToolServiceError,
        ToolValidationError,
    ) as error:
        raise conversation_error(error) from error
    mark_audit_resource(request, AuditResourceType.CONVERSATION, accepted.conversation.id)
    return conversation_turn_response(accepted)


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
            model_configuration_id=body.model_configuration_id,
        )
    except (ConversationServiceError, ConversationValidationError) as error:
        raise conversation_error(error) from error
    mark_audit_resource(request, AuditResourceType.CONVERSATION, conversation_id)
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
