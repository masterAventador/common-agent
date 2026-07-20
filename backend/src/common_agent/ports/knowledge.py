from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol

from common_agent.domain.knowledge import KnowledgeBaseSummary, KnowledgeDocument


class DemoKnowledgeBaseAlreadyExists(Exception):
    """Raised when a Demo knowledge-base name is already persisted."""


class DemoKnowledgeWriteConflict(Exception):
    """Raised when persisted Demo knowledge state rejects a write."""


@dataclass(frozen=True, slots=True)
class PersistedDemoKnowledgeBase:
    summary: KnowledgeBaseSummary
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PersistedDemoKnowledgeDocument:
    document: KnowledgeDocument
    content: str
    created_at: datetime


class DemoKnowledgeRepository(Protocol):
    async def list_knowledge_bases(self) -> tuple[PersistedDemoKnowledgeBase, ...]: ...

    async def get_knowledge_base(
        self, knowledge_base_id: str
    ) -> PersistedDemoKnowledgeBase | None: ...

    async def add_knowledge_base(self, value: PersistedDemoKnowledgeBase) -> None: ...

    async def delete_knowledge_base(self, knowledge_base_id: str) -> bool: ...

    async def list_documents(
        self, knowledge_base_id: str
    ) -> tuple[PersistedDemoKnowledgeDocument, ...]: ...

    async def add_document(self, value: PersistedDemoKnowledgeDocument) -> None: ...


class DemoKnowledgeUnitOfWork(Protocol):
    @property
    def knowledge(self) -> DemoKnowledgeRepository: ...

    async def __aenter__(self) -> DemoKnowledgeUnitOfWork: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    async def commit(self) -> None: ...


class DemoKnowledgeUnitOfWorkFactory(Protocol):
    def __call__(self) -> DemoKnowledgeUnitOfWork: ...
