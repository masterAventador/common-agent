from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from types import TracebackType
from typing import cast

from sqlalchemy import case, delete, func, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from common_agent.adapters.persistence.database import Database
from common_agent.adapters.persistence.models import (
    DemoKnowledgeBaseRow,
    DemoKnowledgeDocumentRow,
)
from common_agent.adapters.persistence.timestamps import (
    from_database_datetime,
    to_database_datetime,
)
from common_agent.domain.knowledge import (
    DocumentParsingStatus,
    KnowledgeBaseSummary,
    KnowledgeDocument,
)
from common_agent.ports.knowledge import (
    DemoKnowledgeBaseAlreadyExists,
    DemoKnowledgeRepository,
    DemoKnowledgeWriteConflict,
    PersistedDemoKnowledgeBase,
    PersistedDemoKnowledgeDocument,
)


class SqlAlchemyDemoKnowledgeRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_knowledge_bases(self) -> tuple[PersistedDemoKnowledgeBase, ...]:
        result = await self._session.execute(
            _knowledge_base_statement().order_by(
                DemoKnowledgeBaseRow.created_at.desc(),
                DemoKnowledgeBaseRow.id.desc(),
            )
        )
        return tuple(
            _to_knowledge_base(row, int(document_count), int(parsing_count))
            for row, document_count, parsing_count in result.all()
        )

    async def get_knowledge_base(self, knowledge_base_id: str) -> PersistedDemoKnowledgeBase | None:
        result = await self._session.execute(
            _knowledge_base_statement().where(DemoKnowledgeBaseRow.id == knowledge_base_id)
        )
        value = result.one_or_none()
        if value is None:
            return None
        row, document_count, parsing_count = value
        return _to_knowledge_base(row, int(document_count), int(parsing_count))

    async def add_knowledge_base(self, value: PersistedDemoKnowledgeBase) -> None:
        self._session.add(
            DemoKnowledgeBaseRow(
                id=value.summary.id,
                name=value.summary.name,
                description=value.summary.description,
                created_at=to_database_datetime(value.created_at),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            raise DemoKnowledgeBaseAlreadyExists from None

    async def delete_knowledge_base(self, knowledge_base_id: str) -> bool:
        result = cast(
            CursorResult[object],
            await self._session.execute(
                delete(DemoKnowledgeBaseRow).where(DemoKnowledgeBaseRow.id == knowledge_base_id)
            ),
        )
        return bool(result.rowcount)

    async def list_documents(
        self, knowledge_base_id: str
    ) -> tuple[PersistedDemoKnowledgeDocument, ...]:
        rows = await self._session.scalars(
            select(DemoKnowledgeDocumentRow)
            .where(DemoKnowledgeDocumentRow.knowledge_base_id == knowledge_base_id)
            .order_by(
                DemoKnowledgeDocumentRow.created_at.desc(),
                DemoKnowledgeDocumentRow.id.desc(),
            )
        )
        return tuple(_to_document(row) for row in rows)

    async def add_document(self, value: PersistedDemoKnowledgeDocument) -> None:
        document = value.document
        self._session.add(
            DemoKnowledgeDocumentRow(
                id=document.id,
                knowledge_base_id=document.knowledge_base_id,
                name=document.name,
                size_bytes=document.size_bytes,
                parsing_status=document.parsing_status.value,
                error_code=document.error_code,
                content=value.content,
                created_at=to_database_datetime(value.created_at),
            )
        )
        try:
            await self._session.flush()
        except IntegrityError:
            raise DemoKnowledgeWriteConflict from None


class SqlAlchemyDemoKnowledgeUnitOfWork:
    def __init__(self, database: Database) -> None:
        self._database = database
        self._context: AbstractAsyncContextManager[AsyncSession] | None = None
        self._session: AsyncSession | None = None
        self._knowledge: DemoKnowledgeRepository | None = None

    @property
    def knowledge(self) -> DemoKnowledgeRepository:
        if self._knowledge is None:
            raise RuntimeError("Demo 知识事务尚未开始")
        return self._knowledge

    async def __aenter__(self) -> SqlAlchemyDemoKnowledgeUnitOfWork:
        if self._context is not None:
            raise RuntimeError("Demo 知识事务不能重复进入")
        context = cast(AbstractAsyncContextManager[AsyncSession], self._database.session())
        session = await context.__aenter__()
        self._context = context
        self._session = session
        self._knowledge = SqlAlchemyDemoKnowledgeRepository(session)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        context = self._context
        self._context = None
        self._session = None
        self._knowledge = None
        if context is None:
            raise RuntimeError("Demo 知识事务尚未开始")
        await context.__aexit__(exc_type, exc_value, traceback)

    async def commit(self) -> None:
        session = self._session
        if session is None:
            raise RuntimeError("Demo 知识事务尚未开始")
        await session.commit()


class SqlAlchemyDemoKnowledgeUnitOfWorkFactory:
    def __init__(self, database: Database) -> None:
        self._database = database

    def __call__(self) -> SqlAlchemyDemoKnowledgeUnitOfWork:
        return SqlAlchemyDemoKnowledgeUnitOfWork(self._database)


def _knowledge_base_statement() -> Select[tuple[DemoKnowledgeBaseRow, int, int]]:
    document_count = (
        select(func.count(DemoKnowledgeDocumentRow.id))
        .where(DemoKnowledgeDocumentRow.knowledge_base_id == DemoKnowledgeBaseRow.id)
        .correlate(DemoKnowledgeBaseRow)
        .scalar_subquery()
    )
    parsing_count = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (
                            DemoKnowledgeDocumentRow.parsing_status.in_(
                                (
                                    DocumentParsingStatus.UPLOADED.value,
                                    DocumentParsingStatus.PARSING.value,
                                )
                            ),
                            1,
                        ),
                        else_=0,
                    )
                ),
                0,
            )
        )
        .where(DemoKnowledgeDocumentRow.knowledge_base_id == DemoKnowledgeBaseRow.id)
        .correlate(DemoKnowledgeBaseRow)
        .scalar_subquery()
    )
    return select(DemoKnowledgeBaseRow, document_count, parsing_count)


def _to_knowledge_base(
    row: DemoKnowledgeBaseRow,
    document_count: int,
    parsing_count: int,
) -> PersistedDemoKnowledgeBase:
    return PersistedDemoKnowledgeBase(
        summary=KnowledgeBaseSummary(
            id=row.id,
            name=row.name,
            description=row.description,
            document_count=document_count,
            parsing_count=parsing_count,
        ),
        created_at=from_database_datetime(row.created_at),
    )


def _to_document(row: DemoKnowledgeDocumentRow) -> PersistedDemoKnowledgeDocument:
    return PersistedDemoKnowledgeDocument(
        document=KnowledgeDocument(
            id=row.id,
            knowledge_base_id=row.knowledge_base_id,
            name=row.name,
            size_bytes=row.size_bytes,
            parsing_status=DocumentParsingStatus(row.parsing_status),
            error_code=row.error_code,
        ),
        content=row.content,
        created_at=from_database_datetime(row.created_at),
    )
