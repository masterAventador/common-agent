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
