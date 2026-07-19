from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class KnowledgeServiceAvailability(StrEnum):
    NOT_CONFIGURED = "not_configured"
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class DocumentParsingStatus(StrEnum):
    UPLOADED = "uploaded"
    PARSING = "parsing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class KnowledgeServiceStatus:
    provider: str
    availability: KnowledgeServiceAvailability
    version: str | None
    error_code: str | None = None


@dataclass(frozen=True, slots=True)
class KnowledgeBaseSummary:
    id: str
    name: str
    description: str
    document_count: int
    parsing_count: int


@dataclass(frozen=True, slots=True)
class CreateKnowledgeBaseRequest:
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class DocumentUpload:
    file_name: str
    content_type: str
    content: bytes = field(repr=False)

    @property
    def size_bytes(self) -> int:
        return len(self.content)


@dataclass(frozen=True, slots=True)
class KnowledgeDocument:
    id: str
    knowledge_base_id: str
    name: str
    size_bytes: int
    parsing_status: DocumentParsingStatus
    error_code: str | None


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalRequest:
    knowledge_base_id: str
    query: str
    top_k: int = 5
    similarity_threshold: float = 0.2


@dataclass(frozen=True, slots=True)
class RetrievedChunk:
    id: str
    document_id: str
    document_name: str
    content: str
    score: float


@dataclass(frozen=True, slots=True)
class KnowledgeRetrievalResult:
    chunks: tuple[RetrievedChunk, ...]
