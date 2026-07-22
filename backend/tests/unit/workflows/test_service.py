from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from itertools import pairwise
from uuid import UUID, uuid4

import pytest

from common_agent.application.workflow_service import WorkflowNotFound, WorkflowService
from common_agent.domain.employee import Employee
from common_agent.domain.knowledge import KnowledgeServiceAvailability
from common_agent.domain.model_configuration import ModelConfiguration, ModelConfigurationInput
from common_agent.domain.workflow import (
    AiChatNodeConfig,
    EmployeeAiChatTarget,
    EndNodeConfig,
    ModelAiChatTarget,
    StartNodeConfig,
    WorkflowConfiguration,
    WorkflowEdge,
    WorkflowNode,
    WorkflowNodePosition,
    WorkflowNodeType,
)
from common_agent.knowledge.base import KnowledgeServiceUnavailable
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.workflows.validator import WorkflowGraphInvalid, WorkflowValidationCode
from tests.unit.workflows.support import (
    workflow_configuration,
    workflow_service_with_probes,
)


class _AiTargetDirectoryProbe:
    def __init__(self, employee: Employee, model: ModelConfiguration) -> None:
        self.employee = employee
        self.model = model
        self.employee_requests: list[UUID] = []
        self.model_requests: list[UUID] = []

    async def get_employee(self, employee_id: UUID) -> Employee:
        self.employee_requests.append(employee_id)
        return self.employee

    async def get_model_configuration(
        self,
        model_configuration_id: UUID,
    ) -> ModelConfiguration:
        self.model_requests.append(model_configuration_id)
        return self.model


def test_validate_accepts_valid_graph_without_knowledge_calls() -> None:
    service, units, knowledge = workflow_service_with_probes()

    issues = asyncio.run(service.validate(workflow_configuration()))

    assert issues == ()
    assert knowledge.requested_ids == []
    assert units.units == []


def test_validate_returns_structural_issues_before_external_calls() -> None:
    service, units, knowledge = workflow_service_with_probes()

    issues = asyncio.run(
        service.validate(workflow_configuration(knowledge_base_id="kb-valid", include_end=False))
    )

    assert WorkflowValidationCode.MISSING_END in {issue.code for issue in issues}
    assert knowledge.requested_ids == []
    assert units.units == []


def test_validate_checks_each_knowledge_reference_and_maps_missing_dataset_to_issue() -> None:
    service, units, knowledge = workflow_service_with_probes()

    valid = asyncio.run(service.validate(workflow_configuration(knowledge_base_id="kb-valid")))
    missing = asyncio.run(service.validate(workflow_configuration(knowledge_base_id="kb-missing")))

    assert valid == ()
    assert knowledge.requested_ids == ["kb-valid", "kb-missing"]
    assert len(missing) == 1
    assert missing[0].code is WorkflowValidationCode.KNOWLEDGE_BASE_NOT_FOUND
    assert missing[0].node_id == "retrieve"
    assert units.units == []


def test_validate_propagates_knowledge_outage_instead_of_marking_graph_valid() -> None:
    service, units, knowledge = workflow_service_with_probes()
    knowledge.availability = KnowledgeServiceAvailability.UNAVAILABLE

    with pytest.raises(KnowledgeServiceUnavailable):
        asyncio.run(service.validate(workflow_configuration(knowledge_base_id="kb-valid")))

    assert knowledge.requested_ids == []
    assert units.units == []


def test_validate_reuses_repeated_employee_and_model_target_lookups() -> None:
    _, units, knowledge = workflow_service_with_probes()
    model = ModelConfiguration.create(
        configuration=ModelConfigurationInput(
            display_name="共享模型",
            model_identifier="qwen-plus",
            enabled=True,
        )
    )
    employee = Employee.create(
        name="共享员工",
        system_prompt="按工作流要求回答",
        default_model_configuration_id=model.id,
        default_model_identifier=model.model_identifier,
    )
    targets = _AiTargetDirectoryProbe(employee, model)
    service = WorkflowService(
        units,
        KnowledgeBaseService(knowledge),
        ai_targets=targets,
    )
    target_configs = (
        AiChatNodeConfig(
            prompt="员工节点一",
            target=EmployeeAiChatTarget(employee_id=employee.id),
        ),
        AiChatNodeConfig(
            prompt="员工节点二",
            target=EmployeeAiChatTarget(employee_id=employee.id),
        ),
        AiChatNodeConfig(
            prompt="模型节点一",
            target=ModelAiChatTarget(model_configuration_id=model.id),
        ),
        AiChatNodeConfig(
            prompt="模型节点二",
            target=ModelAiChatTarget(model_configuration_id=model.id),
        ),
    )
    processing_nodes = tuple(
        WorkflowNode(
            id=f"chat-{index}",
            type=WorkflowNodeType.AI_CHAT,
            position=WorkflowNodePosition(x=index * 200, y=80),
            config=config,
        )
        for index, config in enumerate(target_configs, start=1)
    )
    nodes = (
        WorkflowNode(
            id="start",
            type=WorkflowNodeType.START,
            position=WorkflowNodePosition(x=0, y=0),
            config=StartNodeConfig(),
        ),
        *processing_nodes,
        WorkflowNode(
            id="end",
            type=WorkflowNodeType.END,
            position=WorkflowNodePosition(x=1000, y=0),
            config=EndNodeConfig(),
        ),
    )
    edges = tuple(
        WorkflowEdge(id=f"edge-{index}", source=source.id, target=target.id)
        for index, (source, target) in enumerate(pairwise(nodes), start=1)
    )
    configuration = WorkflowConfiguration(
        name="复用目标校验",
        description="相同目标只查询一次",
        nodes=nodes,
        edges=edges,
    )

    issues = asyncio.run(service.validate(configuration))

    assert issues == ()
    assert targets.employee_requests == [employee.id]
    assert targets.model_requests == [model.id]


def test_create_validates_before_transaction_and_persists_once() -> None:
    service, units, knowledge = workflow_service_with_probes()

    workflow = asyncio.run(service.create(workflow_configuration(knowledge_base_id="kb-valid")))

    assert units.repository.values[workflow.id] == workflow
    assert units.commit_count == 1
    assert knowledge.requested_ids == ["kb-valid"]


def test_create_invalid_graph_does_not_open_transaction() -> None:
    service, units, knowledge = workflow_service_with_probes()

    with pytest.raises(WorkflowGraphInvalid) as captured:
        asyncio.run(service.create(workflow_configuration(include_end=False)))

    assert WorkflowValidationCode.MISSING_END in {issue.code for issue in captured.value.issues}
    assert units.units == []
    assert knowledge.requested_ids == []


def test_get_and_update_missing_workflow_fail_before_knowledge_call() -> None:
    service, units, knowledge = workflow_service_with_probes()
    workflow_id = uuid4()

    with pytest.raises(WorkflowNotFound):
        asyncio.run(service.get(workflow_id))
    with pytest.raises(WorkflowNotFound):
        asyncio.run(
            service.update(
                workflow_id,
                workflow_configuration(knowledge_base_id="kb-missing"),
            )
        )

    assert units.commit_count == 0
    assert knowledge.requested_ids == []


def test_update_preserves_identity_and_creation_time_after_external_validation() -> None:
    service, units, knowledge = workflow_service_with_probes()
    created = asyncio.run(service.create(workflow_configuration()))
    before_update = datetime.now(UTC)
    configuration = workflow_configuration(knowledge_base_id="kb-valid")

    updated = asyncio.run(service.update(created.id, configuration))

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= before_update
    assert updated.nodes == configuration.nodes
    assert units.commit_count == 2
    assert knowledge.requested_ids == ["kb-valid"]
