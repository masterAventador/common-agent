from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Request, status
from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints

from common_agent.api.errors import AppError, ErrorEnvelope
from common_agent.api.routers.knowledge import knowledge_error_to_app_error
from common_agent.application.workflow_service import WorkflowNotFound, WorkflowService
from common_agent.domain.workflow import (
    AI_CHAT_PROMPT_MAX_LENGTH,
    WORKFLOW_DESCRIPTION_MAX_LENGTH,
    WORKFLOW_EDGE_ID_MAX_LENGTH,
    WORKFLOW_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    WORKFLOW_NAME_MAX_LENGTH,
    WORKFLOW_NODE_ID_MAX_LENGTH,
    AiChatNodeConfig,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    StartNodeConfig,
    WorkflowConfiguration,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowNodeType,
    WorkflowValidationError,
)
from common_agent.knowledge.base import KnowledgeServiceError
from common_agent.ports.workflows import WorkflowAlreadyExists
from common_agent.workflows.validator import (
    WorkflowGraphInvalid,
    WorkflowValidationCode,
    WorkflowValidationIssue,
)

router = APIRouter(prefix="/api/v1/workflows", tags=["workflows"])

WorkflowName = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=WORKFLOW_NAME_MAX_LENGTH),
]
WorkflowDescription = Annotated[
    str,
    StringConstraints(strip_whitespace=True, max_length=WORKFLOW_DESCRIPTION_MAX_LENGTH),
]
WorkflowNodeId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=WORKFLOW_NODE_ID_MAX_LENGTH,
    ),
]
WorkflowEdgeId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=WORKFLOW_EDGE_ID_MAX_LENGTH,
    ),
]
AiChatPrompt = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=AI_CHAT_PROMPT_MAX_LENGTH,
    ),
]
WorkflowKnowledgeBaseId = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=1,
        max_length=WORKFLOW_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    ),
]


class WorkflowNodePositionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    x: FiniteFloat
    y: FiniteFloat


class StartNodeConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class AiChatNodeConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: AiChatPrompt


class KnowledgeRetrievalNodeConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_base_id: WorkflowKnowledgeBaseId


class EndNodeConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StartWorkflowNodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WorkflowNodeId
    type: Literal["start"]
    position: WorkflowNodePositionBody
    config: StartNodeConfigBody


class AiChatWorkflowNodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WorkflowNodeId
    type: Literal["ai_chat"]
    position: WorkflowNodePositionBody
    config: AiChatNodeConfigBody


class KnowledgeRetrievalWorkflowNodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WorkflowNodeId
    type: Literal["knowledge_retrieval"]
    position: WorkflowNodePositionBody
    config: KnowledgeRetrievalNodeConfigBody


class EndWorkflowNodeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WorkflowNodeId
    type: Literal["end"]
    position: WorkflowNodePositionBody
    config: EndNodeConfigBody


type WorkflowNodeBody = Annotated[
    StartWorkflowNodeBody
    | AiChatWorkflowNodeBody
    | KnowledgeRetrievalWorkflowNodeBody
    | EndWorkflowNodeBody,
    Field(discriminator="type"),
]


class WorkflowEdgeBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: WorkflowEdgeId
    source: WorkflowNodeId
    target: WorkflowNodeId


class WorkflowConfigurationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: WorkflowName
    description: WorkflowDescription = ""
    nodes: list[WorkflowNodeBody]
    edges: list[WorkflowEdgeBody]


class WorkflowValidationIssueResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: WorkflowValidationCode
    message: str
    node_id: str | None
    edge_id: str | None


class WorkflowValidationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    valid: bool
    issues: list[WorkflowValidationIssueResponse]


class WorkflowResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    description: str
    nodes: list[WorkflowNodeBody]
    edges: list[WorkflowEdgeBody]
    created_at: datetime
    updated_at: datetime


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


def _configuration(body: WorkflowConfigurationBody) -> WorkflowConfiguration:
    return WorkflowConfiguration(
        name=body.name,
        description=body.description,
        nodes=tuple(_node_to_domain(node) for node in body.nodes),
        edges=tuple(
            WorkflowEdge(id=edge.id, source=edge.source, target=edge.target) for edge in body.edges
        ),
    )


def _node_to_domain(body: WorkflowNodeBody) -> WorkflowNode:
    position = WorkflowNodePosition(x=body.position.x, y=body.position.y)
    if isinstance(body, StartWorkflowNodeBody):
        return WorkflowNode(
            id=body.id,
            type=WorkflowNodeType.START,
            position=position,
            config=StartNodeConfig(),
        )
    if isinstance(body, AiChatWorkflowNodeBody):
        return WorkflowNode(
            id=body.id,
            type=WorkflowNodeType.AI_CHAT,
            position=position,
            config=AiChatNodeConfig(prompt=body.config.prompt),
        )
    if isinstance(body, KnowledgeRetrievalWorkflowNodeBody):
        return WorkflowNode(
            id=body.id,
            type=WorkflowNodeType.KNOWLEDGE_RETRIEVAL,
            position=position,
            config=KnowledgeRetrievalNodeConfig(knowledge_base_id=body.config.knowledge_base_id),
        )
    return WorkflowNode(
        id=body.id,
        type=WorkflowNodeType.END,
        position=position,
        config=EndNodeConfig(),
    )


def _response(workflow: WorkflowDefinition) -> WorkflowResponse:
    return WorkflowResponse(
        id=workflow.id,
        name=workflow.name,
        description=workflow.description,
        nodes=[_node_response(node) for node in workflow.nodes],
        edges=[
            WorkflowEdgeBody(id=edge.id, source=edge.source, target=edge.target)
            for edge in workflow.edges
        ],
        created_at=workflow.created_at,
        updated_at=workflow.updated_at,
    )


def _node_response(node: WorkflowNode) -> WorkflowNodeBody:
    position = WorkflowNodePositionBody(x=node.position.x, y=node.position.y)
    config = node.config
    if isinstance(config, StartNodeConfig):
        return StartWorkflowNodeBody(
            id=node.id,
            type="start",
            position=position,
            config=StartNodeConfigBody(),
        )
    if isinstance(config, AiChatNodeConfig):
        return AiChatWorkflowNodeBody(
            id=node.id,
            type="ai_chat",
            position=position,
            config=AiChatNodeConfigBody(prompt=config.prompt),
        )
    if isinstance(config, KnowledgeRetrievalNodeConfig):
        return KnowledgeRetrievalWorkflowNodeBody(
            id=node.id,
            type="knowledge_retrieval",
            position=position,
            config=KnowledgeRetrievalNodeConfigBody(knowledge_base_id=config.knowledge_base_id),
        )
    return EndWorkflowNodeBody(
        id=node.id,
        type="end",
        position=position,
        config=EndNodeConfigBody(),
    )


def _validation_response(
    issues: tuple[WorkflowValidationIssue, ...],
) -> WorkflowValidationResponse:
    return WorkflowValidationResponse(
        valid=not issues,
        issues=[
            WorkflowValidationIssueResponse(
                code=issue.code,
                message=issue.message,
                node_id=issue.node_id,
                edge_id=issue.edge_id,
            )
            for issue in issues
        ],
    )


def _workflow_error_to_app_error(error: Exception) -> AppError:
    if isinstance(error, KnowledgeServiceError):
        return knowledge_error_to_app_error(error)
    if isinstance(error, WorkflowNotFound):
        return AppError(error.code, error.message, 404, error.retryable)
    if isinstance(error, WorkflowAlreadyExists):
        return AppError("workflow_conflict", "工作流已存在", 409, False)
    if isinstance(error, WorkflowGraphInvalid):
        return AppError("workflow_invalid", "工作流图校验失败", 422, False)
    if isinstance(error, WorkflowValidationError):
        return AppError("validation_error", "请求参数不合法", 422, False)
    raise TypeError("unsupported workflow application error")


@router.get(
    "",
    response_model=list[WorkflowResponse],
    responses={503: {"model": ErrorEnvelope}},
)
async def list_workflows(request: Request) -> list[WorkflowResponse]:
    return [_response(workflow) for workflow in await _application(request).list()]


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkflowResponse,
    responses={
        409: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def create_workflow(
    request: Request,
    body: WorkflowConfigurationBody,
) -> WorkflowResponse:
    try:
        workflow = await _application(request).create(_configuration(body))
    except (
        KnowledgeServiceError,
        WorkflowAlreadyExists,
        WorkflowGraphInvalid,
        WorkflowValidationError,
    ) as error:
        raise _workflow_error_to_app_error(error) from error
    return _response(workflow)


@router.post(
    "/validate",
    response_model=WorkflowValidationResponse,
    responses={
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def validate_workflow(
    request: Request,
    body: WorkflowConfigurationBody,
) -> WorkflowValidationResponse:
    try:
        issues = await _application(request).validate(_configuration(body))
    except (KnowledgeServiceError, WorkflowValidationError) as error:
        raise _workflow_error_to_app_error(error) from error
    return _validation_response(issues)


@router.get(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def get_workflow(request: Request, workflow_id: UUID) -> WorkflowResponse:
    try:
        workflow = await _application(request).get(workflow_id)
    except WorkflowNotFound as error:
        raise _workflow_error_to_app_error(error) from error
    return _response(workflow)


@router.put(
    "/{workflow_id}",
    response_model=WorkflowResponse,
    responses={
        404: {"model": ErrorEnvelope},
        422: {"model": ErrorEnvelope},
        502: {"model": ErrorEnvelope},
        503: {"model": ErrorEnvelope},
    },
)
async def update_workflow(
    request: Request,
    workflow_id: UUID,
    body: WorkflowConfigurationBody,
) -> WorkflowResponse:
    try:
        workflow = await _application(request).update(workflow_id, _configuration(body))
    except (
        KnowledgeServiceError,
        WorkflowGraphInvalid,
        WorkflowNotFound,
        WorkflowValidationError,
    ) as error:
        raise _workflow_error_to_app_error(error) from error
    return _response(workflow)
