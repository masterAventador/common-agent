from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, StringConstraints

from common_agent.domain.workflow import AiChatTargetType
from common_agent.domain.workflow_run import (
    WORKFLOW_RUN_INPUT_MAX_LENGTH,
    WorkflowRun,
    WorkflowRunStatus,
    WorkflowRunTrigger,
)
from common_agent.workflows.events import WorkflowEventKind, WorkflowRunEvent

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


class WorkflowAiTargetSummaryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)

    node_id: str
    target_type: AiChatTargetType
    target_id: UUID
    target_name: str
    model_configuration_id: UUID
    model_identifier: str


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
    ai_targets: list[WorkflowAiTargetSummaryResponse]
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


def workflow_run_response(run: WorkflowRun) -> WorkflowRunResponse:
    return WorkflowRunResponse.model_validate(run)


def workflow_run_event_response(event: WorkflowRunEvent) -> WorkflowRunEventResponse:
    return WorkflowRunEventResponse(
        sequence=event.sequence,
        run_id=event.run_id,
        workflow_id=event.workflow_id,
        type=event.kind,
        node_id=event.node_id,
        run=workflow_run_response(event.run),
        occurred_at=event.occurred_at,
    )


__all__ = [
    "StartWorkflowRunBody",
    "WorkflowRunEventResponse",
    "WorkflowRunResponse",
    "WorkflowRunStopAcceptedResponse",
    "workflow_run_event_response",
    "workflow_run_response",
]
