from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request, status

from common_agent.api.audit import mark_audit_resource
from common_agent.api.errors import ErrorEnvelope
from common_agent.api.routers.conversation_errors import conversation_error
from common_agent.api.routers.services import conversation_service
from common_agent.api.schemas.conversations import (
    ConversationHistoryItemResponse,
    conversation_history_response,
)
from common_agent.api.schemas.pagination import CursorPageResponse
from common_agent.audit import AuditResourceType
from common_agent.conversations.contracts import ConversationBusy, ConversationNotFound
from common_agent.domain.conversation import ConversationSource
from common_agent.employees.service import EmployeeNotFound
from common_agent.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_CURSOR_LENGTH,
    MAX_PAGE_LIMIT,
    MAX_PAGE_SEARCH_LENGTH,
    InvalidPageCursor,
    ListPageRequest,
)

router = APIRouter()


@router.get(
    "/api/v1/conversations",
    response_model=CursorPageResponse[ConversationHistoryItemResponse],
    responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def list_conversations(
    request: Request,
    employee_id: Annotated[UUID | None, Query()] = None,
    source: Annotated[ConversationSource | None, Query()] = None,
    search: Annotated[str, Query(max_length=MAX_PAGE_SEARCH_LENGTH)] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_PAGE_CURSOR_LENGTH)] = None,
) -> CursorPageResponse[ConversationHistoryItemResponse]:
    try:
        page = await conversation_service(request).page(
            ListPageRequest(limit=limit, search=search, cursor=cursor),
            employee_id=employee_id,
            source=source,
        )
    except InvalidPageCursor as error:
        raise conversation_error(error) from error
    return CursorPageResponse(
        items=[conversation_history_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/api/v1/conversations/{conversation_id}",
    response_model=ConversationHistoryItemResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def get_conversation(
    request: Request,
    conversation_id: UUID,
) -> ConversationHistoryItemResponse:
    try:
        item = await conversation_service(request).get(conversation_id)
    except (ConversationNotFound, EmployeeNotFound) as error:
        raise conversation_error(error) from error
    return conversation_history_response(item)


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
    mark_audit_resource(request, AuditResourceType.CONVERSATION, conversation_id)


__all__ = ["router"]
