from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common_agent.employees.service import EmployeeNotFound
from common_agent.knowledge.base import KnowledgeBaseNotFound
from tests.unit.employees.support import employee_configuration, employee_service_with_probes


def test_create_without_binding_does_not_call_knowledge_service() -> None:
    service, units, knowledge, workflows = employee_service_with_probes()

    employee = asyncio.run(service.create(employee_configuration()))

    assert employee.knowledge_base_id is None
    assert knowledge.requested_ids == []
    assert workflows.requested_ids == []
    assert units.repository.values[employee.id] == employee
    assert units.commit_count == 1


def test_create_with_binding_validates_exact_knowledge_base_before_commit() -> None:
    service, units, knowledge, _ = employee_service_with_probes()

    employee = asyncio.run(service.create(employee_configuration("kb-valid")))

    assert employee.knowledge_base_id == "kb-valid"
    assert knowledge.requested_ids == ["kb-valid"]
    assert units.commit_count == 1


def test_invalid_binding_fails_before_opening_database_transaction() -> None:
    service, units, knowledge, _ = employee_service_with_probes()

    with pytest.raises(KnowledgeBaseNotFound):
        asyncio.run(service.create(employee_configuration("kb-missing")))

    assert knowledge.requested_ids == ["kb-missing"]
    assert units.units == []
    assert units.repository.values == {}


def test_get_and_update_missing_employee_raise_before_calling_knowledge_service() -> None:
    service, units, knowledge, _ = employee_service_with_probes()
    missing_id = uuid4()

    with pytest.raises(EmployeeNotFound):
        asyncio.run(service.get(missing_id))
    with pytest.raises(EmployeeNotFound):
        asyncio.run(service.update(missing_id, employee_configuration("kb-missing")))

    assert units.commit_count == 0
    assert knowledge.requested_ids == []


def test_update_preserves_identity_and_creation_time() -> None:
    service, units, knowledge, _ = employee_service_with_probes()
    created = asyncio.run(service.create(employee_configuration()))
    before_update = datetime.now(UTC)

    updated = asyncio.run(service.update(created.id, employee_configuration("kb-valid")))

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= before_update
    assert updated.knowledge_base_id == "kb-valid"
    assert knowledge.requested_ids == ["kb-valid"]
    assert units.commit_count == 2


def test_create_and_update_validate_workflow_allowlist_before_commit() -> None:
    service, units, _, workflows = employee_service_with_probes()
    first_id = uuid4()
    second_id = uuid4()
    workflows.available_ids.update({first_id, second_id})

    created = asyncio.run(service.create(employee_configuration(allowed_workflow_ids=(first_id,))))
    updated = asyncio.run(
        service.update(
            created.id,
            employee_configuration(allowed_workflow_ids=(second_id, first_id)),
        )
    )

    assert created.allowed_workflow_ids == (first_id,)
    assert updated.allowed_workflow_ids == (second_id, first_id)
    assert workflows.requested_ids == [first_id, second_id, first_id]
    assert units.commit_count == 2


def test_missing_workflow_in_allowlist_fails_before_write() -> None:
    service, units, _, workflows = employee_service_with_probes()
    missing_id = uuid4()

    with pytest.raises(Exception) as captured:
        asyncio.run(service.create(employee_configuration(allowed_workflow_ids=(missing_id,))))

    assert getattr(captured.value, "code", None) == "workflow_not_found"
    assert workflows.requested_ids == [missing_id]
    assert units.units == []
