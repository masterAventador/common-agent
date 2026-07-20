from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request
from fastapi.responses import StreamingResponse

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.services import conversation_event_broker, conversation_service
from common_agent.api.schemas.conversations import (
    ConversationEventResponse,
    conversation_event_response,
)
from common_agent.api.sse import resume_sequence
from common_agent.conversations.contracts import ConversationNotFound
from common_agent.conversations.events import ConversationEventBroker, EventHistoryUnavailable

router = APIRouter()


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
        await conversation_service(request).list_messages(conversation_id)
    except ConversationNotFound as error:
        raise AppError(error.code, str(error), 404, error.retryable) from error
    resume_after = resume_sequence(after_sequence, last_event_id)
    broker = conversation_event_broker(request)
    try:
        await broker.validate_resume(conversation_id, after_sequence=resume_after)
    except EventHistoryUnavailable as error:
        raise AppError(error.code, str(error), 409, error.retryable) from error

    return StreamingResponse(
        _event_source(request, broker, conversation_id, resume_after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


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
            response = conversation_event_response(event)
            yield (
                f"id: {event.sequence}\n"
                f"event: {event.kind.value}\n"
                f"data: {response.model_dump_json()}\n\n"
            )
    finally:
        await stream.aclose()
