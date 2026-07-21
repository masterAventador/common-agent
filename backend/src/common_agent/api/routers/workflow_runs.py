from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse

from common_agent.api.audit import mark_audit_resource
from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.services import workflow_event_broker, workflow_service
from common_agent.api.schemas.pagination import CursorPageResponse
from common_agent.api.schemas.workflow_runs import (
    StartWorkflowRunBody,
    WorkflowRunEventResponse,
    WorkflowRunResponse,
    WorkflowRunStopAcceptedResponse,
    workflow_run_event_response,
    workflow_run_response,
)
from common_agent.api.sse import resume_sequence
from common_agent.application.workflow_service import (
    WorkflowExecutionUnavailable,
    WorkflowNotFound,
    WorkflowRunConflict,
    WorkflowRunNotActive,
    WorkflowRunNotFound,
    WorkflowRunStopAccepted,
    WorkflowServiceError,
)
from common_agent.audit import AuditResourceType
from common_agent.domain.workflow_run import WorkflowRunTrigger, WorkflowRunValidationError
from common_agent.pagination import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_CURSOR_LENGTH,
    MAX_PAGE_LIMIT,
    MAX_PAGE_SEARCH_LENGTH,
    InvalidPageCursor,
    ListPageRequest,
)
from common_agent.workflows.events import (
    WorkflowEventBroker,
    WorkflowEventHistoryUnavailable,
)

router = APIRouter(tags=["workflow-runs"])


def workflow_run_error(error: Exception) -> AppError:
    if isinstance(error, (WorkflowNotFound, WorkflowRunNotFound)):
        return AppError(error.code, str(error), 404, error.retryable)
    if isinstance(error, (WorkflowRunConflict, WorkflowRunNotActive)):
        return AppError(error.code, str(error), 409, error.retryable)
    if isinstance(error, WorkflowExecutionUnavailable):
        return AppError(error.code, str(error), 503, error.retryable)
    if isinstance(error, WorkflowRunValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    if isinstance(error, InvalidPageCursor):
        return AppError(error.code, error.message, 422, error.retryable)
    raise TypeError("unsupported workflow run application error")


@router.post(
    "/api/v1/workflows/{workflow_id}/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WorkflowRunResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def start_workflow_run(
    request: Request,
    workflow_id: UUID,
    body: StartWorkflowRunBody,
) -> WorkflowRunResponse:
    try:
        run = await workflow_service(request).start_run(
            workflow_id,
            run_id=body.run_id,
            input=body.input,
            trigger=WorkflowRunTrigger.MANUAL,
        )
    except (WorkflowServiceError, WorkflowRunValidationError) as error:
        raise workflow_run_error(error) from error
    mark_audit_resource(request, AuditResourceType.WORKFLOW_RUN, run.id)
    return workflow_run_response(run)


@router.get(
    "/api/v1/workflow-runs",
    response_model=CursorPageResponse[WorkflowRunResponse],
    responses={422: {"model": ErrorEnvelope}, 503: {"model": ErrorEnvelope}},
)
async def list_workflow_runs_for_conversation(
    request: Request,
    conversation_id: Annotated[UUID, Query()],
    search: Annotated[str, Query(max_length=MAX_PAGE_SEARCH_LENGTH)] = "",
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_LIMIT)] = DEFAULT_PAGE_LIMIT,
    cursor: Annotated[str | None, Query(max_length=MAX_PAGE_CURSOR_LENGTH)] = None,
) -> CursorPageResponse[WorkflowRunResponse]:
    try:
        page = await workflow_service(request).page_runs_for_conversation(
            conversation_id,
            ListPageRequest(limit=limit, search=search, cursor=cursor),
        )
    except InvalidPageCursor as error:
        raise workflow_run_error(error) from error
    return CursorPageResponse(
        items=[workflow_run_response(item) for item in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/api/v1/workflow-runs/{run_id}",
    response_model=WorkflowRunResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def get_workflow_run(request: Request, run_id: UUID) -> WorkflowRunResponse:
    try:
        run = await workflow_service(request).get_run(run_id)
    except WorkflowRunNotFound as error:
        raise workflow_run_error(error) from error
    return workflow_run_response(run)


@router.post(
    "/api/v1/workflow-runs/{run_id}/stop",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=WorkflowRunStopAcceptedResponse,
    responses={
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def stop_workflow_run(
    request: Request,
    run_id: UUID,
) -> WorkflowRunStopAcceptedResponse:
    try:
        accepted: WorkflowRunStopAccepted = await workflow_service(request).stop_run(run_id)
    except (WorkflowRunNotFound, WorkflowRunNotActive) as error:
        raise workflow_run_error(error) from error
    mark_audit_resource(request, AuditResourceType.WORKFLOW_RUN, run_id)
    return WorkflowRunStopAcceptedResponse.model_validate(accepted)


@router.get(
    "/api/v1/workflow-runs/{run_id}/events",
    response_model=WorkflowRunEventResponse,
    response_class=StreamingResponse,
    responses={
        200: {
            "description": "工作流运行事件流",
            "content": {
                "text/event-stream": {
                    "schema": {"$ref": "#/components/schemas/WorkflowRunEventResponse"}
                }
            },
        },
        404: {"model": ErrorEnvelope},
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def stream_workflow_run_events(
    request: Request,
    run_id: UUID,
    after_sequence: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    try:
        await workflow_service(request).get_run(run_id)
    except WorkflowRunNotFound as error:
        raise workflow_run_error(error) from error
    resume_after = resume_sequence(after_sequence, last_event_id)
    broker = workflow_event_broker(request)
    try:
        await broker.validate_resume(run_id, after_sequence=resume_after)
    except WorkflowEventHistoryUnavailable as error:
        raise AppError(error.code, str(error), 409, error.retryable) from error
    return StreamingResponse(
        _event_source(request, broker, run_id, resume_after),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _event_source(
    request: Request,
    broker: WorkflowEventBroker,
    run_id: UUID,
    after_sequence: int,
) -> AsyncIterator[str]:
    stream = broker.stream(run_id, after_sequence=after_sequence)
    try:
        async for event in stream:
            if await request.is_disconnected():
                return
            response = workflow_run_event_response(event)
            yield (
                f"id: {event.sequence}\n"
                f"event: {event.kind.value}\n"
                f"data: {response.model_dump_json()}\n\n"
            )
    finally:
        await stream.aclose()


__all__ = ["WorkflowRunEventResponse", "WorkflowRunResponse", "router"]
