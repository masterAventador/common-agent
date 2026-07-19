from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from common_agent.domain.employee import Employee, EmployeeConfiguration
from common_agent.domain.knowledge import (
    CreateKnowledgeBaseRequest,
    DocumentUpload,
    KnowledgeBaseSummary,
    KnowledgeDocument,
    KnowledgeRetrievalRequest,
    KnowledgeRetrievalResult,
    KnowledgeServiceAvailability,
    KnowledgeServiceStatus,
)
from common_agent.employees.service import EmployeeNotFound, EmployeeService
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.employees import EmployeeAlreadyExists


class _EmployeeRepository:
    def __init__(self) -> None:
        self.values: dict[UUID, Employee] = {}

    async def list(self) -> tuple[Employee, ...]:
        return tuple(self.values.values())

    async def get(self, employee_id: UUID) -> Employee | None:
        return self.values.get(employee_id)

    async def add(self, employee: Employee) -> None:
        if employee.id in self.values:
            raise EmployeeAlreadyExists
        self.values[employee.id] = employee

    async def update(self, employee: Employee) -> bool:
        if employee.id not in self.values:
            return False
        self.values[employee.id] = employee
        return True


class _UnitOfWork:
    def __init__(self, repository: _EmployeeRepository) -> None:
        self.employees = repository
        self.commit_count = 0

    async def __aenter__(self) -> _UnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback

    async def commit(self) -> None:
        self.commit_count += 1


class _UnitOfWorkFactory:
    def __init__(self) -> None:
        self.repository = _EmployeeRepository()
        self.units: list[_UnitOfWork] = []

    def __call__(self) -> _UnitOfWork:
        unit = _UnitOfWork(self.repository)
        self.units.append(unit)
        return unit

    @property
    def commit_count(self) -> int:
        return sum(unit.commit_count for unit in self.units)


class _KnowledgeProbe:
    provider_name = "probe"

    def __init__(self) -> None:
        self.availability = KnowledgeServiceAvailability.AVAILABLE
        self.values = {
            "kb-valid": KnowledgeBaseSummary(
                id="kb-valid",
                name="通用知识库",
                description="",
                document_count=0,
                parsing_count=0,
            )
        }
        self.requested_ids: list[str] = []

    async def status(self) -> KnowledgeServiceStatus:
        return KnowledgeServiceStatus(
            provider=self.provider_name,
            availability=self.availability,
            version=(
                "v0.25.6" if self.availability is KnowledgeServiceAvailability.AVAILABLE else None
            ),
        )

    async def get_knowledge_base(self, knowledge_base_id: str) -> KnowledgeBaseSummary:
        self.requested_ids.append(knowledge_base_id)
        try:
            return self.values[knowledge_base_id]
        except KeyError:
            raise KnowledgeBaseNotFound from None

    async def list_knowledge_bases(self) -> tuple[KnowledgeBaseSummary, ...]:
        return tuple(self.values.values())

    async def create_knowledge_base(
        self, request: CreateKnowledgeBaseRequest
    ) -> KnowledgeBaseSummary:
        del request
        raise NotImplementedError

    async def upload_document(
        self, knowledge_base_id: str, upload: DocumentUpload
    ) -> KnowledgeDocument:
        del knowledge_base_id, upload
        raise NotImplementedError

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        del knowledge_base_id
        raise NotImplementedError

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        del request
        raise NotImplementedError


def _service() -> tuple[EmployeeService, _UnitOfWorkFactory, _KnowledgeProbe]:
    units = _UnitOfWorkFactory()
    knowledge = _KnowledgeProbe()
    return EmployeeService(units, KnowledgeBaseService(knowledge)), units, knowledge


def _configuration(knowledge_base_id: str | None = None) -> EmployeeConfiguration:
    return EmployeeConfiguration(
        name="通用助理",
        description="与业务无关的会话角色",
        system_prompt="根据可用信息回答问题。",
        knowledge_base_id=knowledge_base_id,
    )


def test_create_without_binding_does_not_call_knowledge_service() -> None:
    service, units, knowledge = _service()

    employee = asyncio.run(service.create(_configuration()))

    assert employee.knowledge_base_id is None
    assert knowledge.requested_ids == []
    assert units.repository.values[employee.id] == employee
    assert units.commit_count == 1


def test_create_with_binding_validates_exact_knowledge_base_before_commit() -> None:
    service, units, knowledge = _service()

    employee = asyncio.run(service.create(_configuration("kb-valid")))

    assert employee.knowledge_base_id == "kb-valid"
    assert knowledge.requested_ids == ["kb-valid"]
    assert units.commit_count == 1


def test_invalid_binding_fails_before_opening_database_transaction() -> None:
    service, units, knowledge = _service()

    with pytest.raises(KnowledgeBaseNotFound):
        asyncio.run(service.create(_configuration("kb-missing")))

    assert knowledge.requested_ids == ["kb-missing"]
    assert units.units == []
    assert units.repository.values == {}


def test_get_and_update_missing_employee_raise_before_calling_knowledge_service() -> None:
    service, units, knowledge = _service()
    missing_id = uuid4()

    with pytest.raises(EmployeeNotFound):
        asyncio.run(service.get(missing_id))
    with pytest.raises(EmployeeNotFound):
        asyncio.run(service.update(missing_id, _configuration("kb-missing")))

    assert units.commit_count == 0
    assert knowledge.requested_ids == []


def test_update_preserves_identity_and_creation_time() -> None:
    service, units, knowledge = _service()
    created = asyncio.run(service.create(_configuration()))
    before_update = datetime.now(UTC)

    updated = asyncio.run(service.update(created.id, _configuration("kb-valid")))

    assert updated.id == created.id
    assert updated.created_at == created.created_at
    assert updated.updated_at >= before_update
    assert updated.knowledge_base_id == "kb-valid"
    assert knowledge.requested_ids == ["kb-valid"]
    assert units.commit_count == 2
