from __future__ import annotations

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
from common_agent.knowledge.base import KnowledgeBaseNotFound
from common_agent.ports.knowledge import (
    DemoKnowledgeBaseAlreadyExists,
    DemoKnowledgeRepository,
    DemoKnowledgeWriteConflict,
    PersistedDemoKnowledgeBase,
    PersistedDemoKnowledgeDocument,
)


class MemoryDemoKnowledgeUnitOfWorkFactory:
    def __init__(self) -> None:
        self.bases: dict[str, PersistedDemoKnowledgeBase] = {}
        self.documents: dict[str, list[PersistedDemoKnowledgeDocument]] = {}

    def __call__(self) -> _MemoryDemoKnowledgeUnitOfWork:
        return _MemoryDemoKnowledgeUnitOfWork(self)


class _MemoryDemoKnowledgeRepository:
    def __init__(self, state: MemoryDemoKnowledgeUnitOfWorkFactory) -> None:
        self._state = state

    async def list_knowledge_bases(self) -> tuple[PersistedDemoKnowledgeBase, ...]:
        values = sorted(
            self._state.bases.values(),
            key=lambda item: (item.created_at, item.summary.id),
            reverse=True,
        )
        return tuple(self._with_counts(value) for value in values)

    async def get_knowledge_base(self, knowledge_base_id: str) -> PersistedDemoKnowledgeBase | None:
        value = self._state.bases.get(knowledge_base_id)
        return None if value is None else self._with_counts(value)

    async def add_knowledge_base(self, value: PersistedDemoKnowledgeBase) -> None:
        if any(
            existing.summary.name == value.summary.name for existing in self._state.bases.values()
        ):
            raise DemoKnowledgeBaseAlreadyExists
        self._state.bases[value.summary.id] = value
        self._state.documents[value.summary.id] = []

    async def delete_knowledge_base(self, knowledge_base_id: str) -> bool:
        if self._state.bases.pop(knowledge_base_id, None) is None:
            return False
        self._state.documents.pop(knowledge_base_id, None)
        return True

    async def list_documents(
        self, knowledge_base_id: str
    ) -> tuple[PersistedDemoKnowledgeDocument, ...]:
        return tuple(self._state.documents.get(knowledge_base_id, ()))

    async def add_document(self, value: PersistedDemoKnowledgeDocument) -> None:
        documents = self._state.documents.get(value.document.knowledge_base_id)
        if documents is None:
            raise DemoKnowledgeWriteConflict
        documents.insert(0, value)

    def _with_counts(self, value: PersistedDemoKnowledgeBase) -> PersistedDemoKnowledgeBase:
        documents = self._state.documents[value.summary.id]
        return PersistedDemoKnowledgeBase(
            summary=KnowledgeBaseSummary(
                id=value.summary.id,
                name=value.summary.name,
                description=value.summary.description,
                document_count=len(documents),
                parsing_count=sum(
                    item.document.parsing_status.value in {"uploaded", "parsing"}
                    for item in documents
                ),
            ),
            created_at=value.created_at,
        )


class _MemoryDemoKnowledgeUnitOfWork:
    def __init__(self, state: MemoryDemoKnowledgeUnitOfWorkFactory) -> None:
        self._repository = _MemoryDemoKnowledgeRepository(state)

    @property
    def knowledge(self) -> DemoKnowledgeRepository:
        return self._repository

    async def __aenter__(self) -> _MemoryDemoKnowledgeUnitOfWork:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: object,
    ) -> None:
        del exc_type, exc_value, traceback

    async def commit(self) -> None:
        return


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
        self.retrieval_requests: list[KnowledgeRetrievalRequest] = []
        self.retrieval_result = KnowledgeRetrievalResult(chunks=())

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

    async def delete_knowledge_base(self, knowledge_base_id: str) -> None:
        if self.values.pop(knowledge_base_id, None) is None:
            raise KnowledgeBaseNotFound

    async def upload_document(
        self, knowledge_base_id: str, upload: DocumentUpload
    ) -> KnowledgeDocument:
        del knowledge_base_id, upload
        raise NotImplementedError

    async def list_documents(self, knowledge_base_id: str) -> tuple[KnowledgeDocument, ...]:
        del knowledge_base_id
        raise NotImplementedError

    async def retrieve(self, request: KnowledgeRetrievalRequest) -> KnowledgeRetrievalResult:
        self.retrieval_requests.append(request)
        return self.retrieval_result
