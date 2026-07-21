from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from math import inf, nan
from uuid import UUID, uuid4

import pytest

from common_agent.domain.workflow import (
    AI_CHAT_PROMPT_MAX_LENGTH,
    WORKFLOW_DESCRIPTION_MAX_LENGTH,
    WORKFLOW_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    WORKFLOW_NAME_MAX_LENGTH,
    AiChatNodeConfig,
    EmployeeAiChatTarget,
    EndNodeConfig,
    KnowledgeRetrievalNodeConfig,
    ModelAiChatTarget,
    StartNodeConfig,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowNodeType,
    WorkflowValidationError,
)


def _valid_nodes() -> tuple[WorkflowNode, ...]:
    return (
        WorkflowNode(
            id="start",
            type=WorkflowNodeType.START,
            position=WorkflowNodePosition(x=0, y=0),
            config=StartNodeConfig(),
        ),
        WorkflowNode(
            id="chat",
            type=WorkflowNodeType.AI_CHAT,
            position=WorkflowNodePosition(x=240, y=0),
            config=AiChatNodeConfig(prompt="  根据输入回答问题  "),
        ),
        WorkflowNode(
            id="retrieve",
            type=WorkflowNodeType.KNOWLEDGE_RETRIEVAL,
            position=WorkflowNodePosition(x=480, y=0),
            config=KnowledgeRetrievalNodeConfig(knowledge_base_id="  dataset-1  "),
        ),
        WorkflowNode(
            id="end",
            type=WorkflowNodeType.END,
            position=WorkflowNodePosition(x=720, y=0),
            config=EndNodeConfig(),
        ),
    )


def _valid_edges() -> tuple[WorkflowEdge, ...]:
    return (
        WorkflowEdge(id="edge-1", source="start", target="chat"),
        WorkflowEdge(id="edge-2", source="chat", target="retrieve"),
        WorkflowEdge(id="edge-3", source="retrieve", target="end"),
    )


def test_workflow_definition_create_normalizes_fields_and_preserves_schema() -> None:
    now = datetime.now(UTC)

    workflow = WorkflowDefinition.create(
        name="  通用知识问答  ",
        description="  先回答然后检索并输出  ",
        nodes=_valid_nodes(),
        edges=_valid_edges(),
        now=now,
    )

    assert isinstance(workflow.id, UUID)
    assert workflow.name == "通用知识问答"
    assert workflow.description == "先回答然后检索并输出"
    assert workflow.nodes[1].config == AiChatNodeConfig(prompt="根据输入回答问题")
    assert workflow.nodes[2].config == KnowledgeRetrievalNodeConfig(knowledge_base_id="dataset-1")
    assert workflow.created_at == now
    assert workflow.updated_at == now


def test_workflow_reconfigure_preserves_identity_and_creation_time() -> None:
    workflow = WorkflowDefinition.create(
        name="原工作流",
        nodes=_valid_nodes(),
        edges=_valid_edges(),
    )
    changed_at = workflow.updated_at + timedelta(microseconds=1)

    changed = workflow.reconfigure(
        name="  新工作流  ",
        description="  新说明  ",
        nodes=_valid_nodes(),
        edges=_valid_edges(),
        updated_at=changed_at,
    )

    assert changed.id == workflow.id
    assert changed.created_at == workflow.created_at
    assert changed.updated_at == changed_at
    assert changed.name == "新工作流"
    assert changed.description == "新说明"

    with pytest.raises(WorkflowValidationError) as captured:
        changed.reconfigure(
            name="时间倒退",
            description="",
            nodes=_valid_nodes(),
            edges=_valid_edges(),
            updated_at=workflow.updated_at,
        )
    assert captured.value.field == "updated_at"


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"workflow_id": "not-a-uuid"}, "id"),
        ({"name": "   "}, "name"),
        ({"name": "x" * (WORKFLOW_NAME_MAX_LENGTH + 1)}, "name"),
        ({"description": "x" * (WORKFLOW_DESCRIPTION_MAX_LENGTH + 1)}, "description"),
        ({"nodes": ["not-a-node"]}, "nodes"),
        ({"edges": ["not-an-edge"]}, "edges"),
        ({"now": datetime.now(UTC).replace(tzinfo=None)}, "created_at"),
    ],
)
def test_workflow_definition_rejects_invalid_fields(
    overrides: dict[str, object], field: str
) -> None:
    values: dict[str, object] = {
        "name": "通用工作流",
        "nodes": _valid_nodes(),
        "edges": _valid_edges(),
    }
    values.update(overrides)

    with pytest.raises(WorkflowValidationError) as captured:
        WorkflowDefinition.create(**values)  # type: ignore[arg-type]

    assert captured.value.field == field


@pytest.mark.parametrize("coordinate", [True, "0", nan, inf, -inf])
def test_node_position_rejects_non_finite_numeric_coordinates(coordinate: object) -> None:
    with pytest.raises(WorkflowValidationError) as captured:
        WorkflowNodePosition(x=coordinate, y=0)  # type: ignore[arg-type]

    assert captured.value.field == "position.x"


def test_node_position_normalizes_integer_coordinates_to_float() -> None:
    position = WorkflowNodePosition(x=10, y=-20.5)

    assert position.x == 10.0
    assert position.y == -20.5
    assert isinstance(position.x, float)


@pytest.mark.parametrize(
    ("node_type", "config"),
    [
        (WorkflowNodeType.START, AiChatNodeConfig(prompt="回答")),
        (WorkflowNodeType.AI_CHAT, StartNodeConfig()),
        (
            WorkflowNodeType.KNOWLEDGE_RETRIEVAL,
            EndNodeConfig(),
        ),
        (WorkflowNodeType.END, KnowledgeRetrievalNodeConfig(knowledge_base_id="dataset-1")),
    ],
)
def test_node_rejects_config_that_does_not_match_its_type(
    node_type: WorkflowNodeType,
    config: object,
) -> None:
    with pytest.raises(WorkflowValidationError) as captured:
        WorkflowNode(
            id="node-1",
            type=node_type,
            position=WorkflowNodePosition(x=0, y=0),
            config=config,  # type: ignore[arg-type]
        )

    assert captured.value.field == "config"


def test_node_rejects_unknown_type_and_invalid_position() -> None:
    with pytest.raises(WorkflowValidationError) as unknown_type:
        WorkflowNode(
            id="node-1",
            type="script",  # type: ignore[arg-type]
            position=WorkflowNodePosition(x=0, y=0),
            config=StartNodeConfig(),
        )
    assert unknown_type.value.field == "type"

    with pytest.raises(WorkflowValidationError) as invalid_position:
        WorkflowNode(
            id="node-1",
            type=WorkflowNodeType.START,
            position={"x": 0, "y": 0},  # type: ignore[arg-type]
            config=StartNodeConfig(),
        )
    assert invalid_position.value.field == "position"


@pytest.mark.parametrize(
    ("factory", "field"),
    [
        (lambda: AiChatNodeConfig(prompt="   "), "prompt"),
        (
            lambda: AiChatNodeConfig(prompt="x" * (AI_CHAT_PROMPT_MAX_LENGTH + 1)),
            "prompt",
        ),
        (lambda: KnowledgeRetrievalNodeConfig(knowledge_base_id="   "), "knowledge_base_id"),
        (
            lambda: KnowledgeRetrievalNodeConfig(
                knowledge_base_id="x" * (WORKFLOW_KNOWLEDGE_BASE_ID_MAX_LENGTH + 1)
            ),
            "knowledge_base_id",
        ),
    ],
)
def test_business_node_configs_reject_invalid_values(factory: object, field: str) -> None:
    with pytest.raises(WorkflowValidationError) as captured:
        factory()  # type: ignore[operator]

    assert captured.value.field == field


def test_ai_chat_node_accepts_exactly_one_typed_execution_target() -> None:
    employee_id = uuid4()
    model_configuration_id = uuid4()

    employee = AiChatNodeConfig(
        prompt="使用数字员工回答",
        target=EmployeeAiChatTarget(employee_id=employee_id),
    )
    model = AiChatNodeConfig(
        prompt="使用通用模型回答",
        target=ModelAiChatTarget(model_configuration_id=model_configuration_id),
    )

    assert isinstance(employee.target, EmployeeAiChatTarget)
    assert employee.target.employee_id == employee_id
    assert isinstance(model.target, ModelAiChatTarget)
    assert model.target.model_configuration_id == model_configuration_id


@pytest.mark.parametrize(
    "target",
    [
        {"type": "employee", "employee_id": "not-a-uuid"},
        {"type": "model", "model_configuration_id": "not-a-uuid"},
        object(),
    ],
)
def test_ai_chat_node_rejects_untyped_or_invalid_execution_target(target: object) -> None:
    with pytest.raises(WorkflowValidationError) as captured:
        AiChatNodeConfig(prompt="回答", target=target)  # type: ignore[arg-type]

    assert captured.value.field == "target"


def test_node_and_edge_reject_blank_identifiers() -> None:
    with pytest.raises(WorkflowValidationError) as node_error:
        replace(_valid_nodes()[0], id="   ")
    assert node_error.value.field == "id"

    for values, field in (
        ({"id": " ", "source": "start", "target": "end"}, "id"),
        ({"id": "edge", "source": " ", "target": "end"}, "source"),
        ({"id": "edge", "source": "start", "target": " "}, "target"),
    ):
        with pytest.raises(WorkflowValidationError) as edge_error:
            WorkflowEdge(**values)
        assert edge_error.value.field == field
