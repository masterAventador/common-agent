from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from common_agent.employees.service import EmployeeNotFound
from common_agent.knowledge.base import KnowledgeBaseNotFound
from tests.unit.employees.support import employee_configuration, employee_service_with_probes


def test_create_without_binding_does_not_call_knowledge_service() -> None:
    service, units, knowledge = employee_service_with_probes()

    employee = asyncio.run(service.create(employee_configuration()))

    assert employee.knowledge_base_id is None
    assert knowledge.requested_ids == []
    assert units.repository.values[employee.id] == employee
    assert units.commit_count == 1


def test_create_with_binding_validates_exact_knowledge_base_before_commit() -> None:
    service, units, knowledge = employee_service_with_probes()

    employee = asyncio.run(service.create(employee_configuration("kb-valid")))

    assert employee.knowledge_base_id == "kb-valid"
    assert knowledge.requested_ids == ["kb-valid"]
    assert units.commit_count == 1


def test_invalid_binding_fails_before_opening_database_transaction() -> None:
    service, units, knowledge = employee_service_with_probes()

    with pytest.raises(KnowledgeBaseNotFound):
        asyncio.run(service.create(employee_configuration("kb-missing")))

    assert knowledge.requested_ids == ["kb-missing"]
    assert units.units == []
    assert units.repository.values == {}


def test_get_and_update_missing_employee_raise_before_calling_knowledge_service() -> None:
    service, units, knowledge = employee_service_with_probes()
    missing_id = uuid4()

    with pytest.raises(EmployeeNotFound):
        asyncio.run(service.get(missing_id))
    with pytest.raises(EmployeeNotFound):
        asyncio.run(service.update(missing_id, employee_configuration("kb-missing")))

    assert units.commit_count == 0
    assert knowledge.requested_ids == []


def test_update_preserves_identity_and_creation_time() -> None:
    service, units, knowledge = employee_service_with_probes()
    created = asyncio.run(service.create(employee_configuration()))
    before_update = datetime.now(UTC)

    updated = asyncio.run(service.update(created.id, employee_configuration("kb-valid")))

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= before_update
    assert updated.knowledge_base_id == "kb-valid"
    assert knowledge.requested_ids == ["kb-valid"]
    assert units.commit_count == 2
