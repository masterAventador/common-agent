from __future__ import annotations

from types import TracebackType
from uuid import UUID

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
from common_agent.employees.service import EmployeeService
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.knowledge.service import KnowledgeBaseService
from common_agent.ports.employees import EmployeeAlreadyExists


class EmployeeRepositoryProbe:
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


class EmployeeUnitOfWorkProbe:
    def __init__(self, repository: EmployeeRepositoryProbe) -> None:
        self.employees = repository
        self.commit_count = 0

    async def __aenter__(self) -> EmployeeUnitOfWorkProbe:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        del exc_type, exc_value, traceback

    async def commit(self) -> None:
        self.commit_count += 1


class EmployeeUnitOfWorkFactoryProbe:
    def __init__(self) -> None:
        self.repository = EmployeeRepositoryProbe()
        self.units: list[EmployeeUnitOfWorkProbe] = []

    def __call__(self) -> EmployeeUnitOfWorkProbe:
        unit = EmployeeUnitOfWorkProbe(self.repository)
        self.units.append(unit)
        return unit

    @property
    def commit_count(self) -> int:
        return sum(unit.commit_count for unit in self.units)


class KnowledgeProbe:
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


def employee_service_with_probes() -> tuple[
    EmployeeService,
    EmployeeUnitOfWorkFactoryProbe,
    KnowledgeProbe,
]:
    units = EmployeeUnitOfWorkFactoryProbe()
    knowledge = KnowledgeProbe()
    return EmployeeService(units, KnowledgeBaseService(knowledge)), units, knowledge


def employee_configuration(knowledge_base_id: str | None = None) -> EmployeeConfiguration:
    return EmployeeConfiguration(
        name="通用助理",
        description="与业务无关的会话角色",
        system_prompt="根据可用信息回答问题。",
        knowledge_base_id=knowledge_base_id,
    )
