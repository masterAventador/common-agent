from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common_agent.application.workflow_service import WorkflowNotFound
from common_agent.domain.knowledge import KnowledgeServiceAvailability
from common_agent.knowledge.base import KnowledgeServiceUnavailable
from common_agent.workflows.validator import WorkflowGraphInvalid, WorkflowValidationCode
from tests.unit.workflows.support import (
    workflow_configuration,
    workflow_service_with_probes,
)


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
