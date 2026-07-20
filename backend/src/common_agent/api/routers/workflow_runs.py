from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Header, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, StringConstraints

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.sse import resume_sequence
from common_agent.application.workflow_service import (
    WorkflowExecutionUnavailable,
    WorkflowNotFound,
    WorkflowRunConflict,
    WorkflowRunNotActive,
    WorkflowRunNotFound,
    WorkflowRunStopAccepted,
    WorkflowService,
    WorkflowServiceError,
)
from common_agent.domain.workflow_run import (
    WORKFLOW_RUN_INPUT_MAX_LENGTH,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunTrigger,
    WorkflowRunValidationError,
)
from common_agent.workflows.events import (
    WorkflowEventBroker,
    WorkflowEventHistoryUnavailable,
    WorkflowEventKind,
    WorkflowRunEvent,
)

router = APIRouter(tags=["workflow-runs"])

WorkflowRunInput = Annotated[
    str,
    StringConstraints(min_length=1, max_length=WORKFLOW_RUN_INPUT_MAX_LENGTH),
]


class StartWorkflowRunBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: UUID
    input: WorkflowRunInput


class WorkflowRunOriginResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    employee_id: UUID
    conversation_id: UUID
    assistant_message_id: UUID


class WorkflowRunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    id: UUID
    workflow_id: UUID
    trigger: WorkflowRunTrigger
    status: WorkflowRunStatus
    input: str
    output: str
    current_node_id: str | None
    completed_node_ids: list[str]
    failed_node_id: str | None
    error_code: str | None
    origin: WorkflowRunOriginResponse | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    updated_at: datetime


class WorkflowRunStopAcceptedResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    run_id: UUID


class WorkflowRunEventResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["1"] = "1"
    sequence: int
    run_id: UUID
    workflow_id: UUID
    type: WorkflowEventKind
    node_id: str | None
    run: WorkflowRunResponse
    occurred_at: datetime


def _application(request: Request) -> WorkflowService:
    application = getattr(request.app.state, "workflows", None)
    if not isinstance(application, WorkflowService):
        raise AppError(
            code="workflow_service_unavailable",
            message="工作流服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return application


def _event_broker(request: Request) -> WorkflowEventBroker:
    broker = getattr(request.app.state, "workflow_events", None)
    if not isinstance(broker, WorkflowEventBroker):
        raise AppError(
            code="workflow_service_unavailable",
            message="工作流服务暂时不可用",
            status_code=503,
            retryable=True,
        )
    return broker


def _run_response(run: WorkflowRun) -> WorkflowRunResponse:
    return WorkflowRunResponse.model_validate(run)


def _event_response(event: WorkflowRunEvent) -> WorkflowRunEventResponse:
    return WorkflowRunEventResponse(
        sequence=event.sequence,
        run_id=event.run_id,
        workflow_id=event.workflow_id,
        type=event.kind,
        node_id=event.node_id,
        run=_run_response(event.run),
        occurred_at=event.occurred_at,
    )


def _service_error(error: Exception) -> AppError:
    if isinstance(error, (WorkflowNotFound, WorkflowRunNotFound)):
        return AppError(error.code, str(error), 404, error.retryable)
    if isinstance(error, (WorkflowRunConflict, WorkflowRunNotActive)):
        return AppError(error.code, str(error), 409, error.retryable)
    if isinstance(error, WorkflowExecutionUnavailable):
        return AppError(error.code, str(error), 503, error.retryable)
    if isinstance(error, WorkflowRunValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
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
        run = await _application(request).start_run(
            workflow_id,
            run_id=body.run_id,
            input=body.input,
            trigger=WorkflowRunTrigger.MANUAL,
        )
    except (WorkflowServiceError, WorkflowRunValidationError) as error:
        raise _service_error(error) from error
    return _run_response(run)


@router.get(
    "/api/v1/workflow-runs",
    response_model=list[WorkflowRunResponse],
    responses={
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def list_workflow_runs_for_conversation(
    request: Request,
    conversation_id: Annotated[UUID, Query()],
) -> list[WorkflowRunResponse]:
    runs = await _application(request).list_runs_for_conversation(conversation_id)
    return [_run_response(run) for run in runs]


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
        run = await _application(request).get_run(run_id)
    except WorkflowRunNotFound as error:
        raise _service_error(error) from error
    return _run_response(run)


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
        accepted: WorkflowRunStopAccepted = await _application(request).stop_run(run_id)
    except (WorkflowRunNotFound, WorkflowRunNotActive) as error:
        raise _service_error(error) from error
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
        await _application(request).get_run(run_id)
    except WorkflowRunNotFound as error:
        raise _service_error(error) from error
    resume_after = resume_sequence(after_sequence, last_event_id)
    broker = _event_broker(request)
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
            response = _event_response(event)
            yield (
                f"id: {event.sequence}\n"
                f"event: {event.kind.value}\n"
                f"data: {response.model_dump_json()}\n\n"
            )
    finally:
        await stream.aclose()
