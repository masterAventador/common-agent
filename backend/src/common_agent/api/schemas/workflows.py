from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat, StringConstraints

from common_agent.domain.workflow import (
    AI_CHAT_PROMPT_MAX_LENGTH,
    WORKFLOW_DESCRIPTION_MAX_LENGTH,
    WORKFLOW_EDGE_ID_MAX_LENGTH,
    WORKFLOW_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    WORKFLOW_NAME_MAX_LENGTH,
    WORKFLOW_NODE_ID_MAX_LENGTH,
    AiChatNodeConfig,
    EmployeeAiChatTarget,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    ModelAiChatTarget,
    StartNodeConfig,
    WorkflowConfiguration,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodeConfig,
    WorkflowNodePosition,
    WorkflowNodeType,
)
from common_agent.workflows.validator import WorkflowValidationCode, WorkflowValidationIssue

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


class EmployeeAiChatTargetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["employee"]
    employee_id: UUID


class ModelAiChatTargetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal["model"]
    model_configuration_id: UUID


type AiChatTargetBody = Annotated[
    EmployeeAiChatTargetBody | ModelAiChatTargetBody,
    Field(discriminator="type"),
]


class AiChatNodeConfigBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    prompt: AiChatPrompt
    target: AiChatTargetBody


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


def workflow_configuration(body: WorkflowConfigurationBody) -> WorkflowConfiguration:
    return WorkflowConfiguration(
        name=body.name,
        description=body.description,
        nodes=tuple(_node_to_domain(node) for node in body.nodes),
        edges=tuple(
            WorkflowEdge(id=edge.id, source=edge.source, target=edge.target) for edge in body.edges
        ),
    )


def workflow_response(workflow: WorkflowDefinition) -> WorkflowResponse:
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


def workflow_validation_response(
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


def _node_to_domain(body: WorkflowNodeBody) -> WorkflowNode:
    position = WorkflowNodePosition(x=body.position.x, y=body.position.y)
    config: WorkflowNodeConfig
    if isinstance(body, StartWorkflowNodeBody):
        config = StartNodeConfig()
        node_type = WorkflowNodeType.START
    elif isinstance(body, AiChatWorkflowNodeBody):
        target = body.config.target
        config = AiChatNodeConfig(
            prompt=body.config.prompt,
            target=(
                EmployeeAiChatTarget(employee_id=target.employee_id)
                if isinstance(target, EmployeeAiChatTargetBody)
                else ModelAiChatTarget(model_configuration_id=target.model_configuration_id)
            ),
        )
        node_type = WorkflowNodeType.AI_CHAT
    elif isinstance(body, KnowledgeRetrievalWorkflowNodeBody):
        config = KnowledgeRetrievalNodeConfig(knowledge_base_id=body.config.knowledge_base_id)
        node_type = WorkflowNodeType.KNOWLEDGE_RETRIEVAL
    else:
        config = EndNodeConfig()
        node_type = WorkflowNodeType.END
    return WorkflowNode(id=body.id, type=node_type, position=position, config=config)


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
        if config.target is None:
            raise ValueError("AI 对话节点缺少执行目标")
        target: AiChatTargetBody
        if isinstance(config.target, EmployeeAiChatTarget):
            target = EmployeeAiChatTargetBody(
                type="employee",
                employee_id=config.target.employee_id,
            )
        else:
            target = ModelAiChatTargetBody(
                type="model",
                model_configuration_id=config.target.model_configuration_id,
            )
        return AiChatWorkflowNodeBody(
            id=node.id,
            type="ai_chat",
            position=position,
            config=AiChatNodeConfigBody(prompt=config.prompt, target=target),
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


__all__ = [
    "WorkflowConfigurationBody",
    "WorkflowResponse",
    "WorkflowValidationResponse",
    "workflow_configuration",
    "workflow_response",
    "workflow_validation_response",
]
