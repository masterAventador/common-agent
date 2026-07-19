from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from common_agent.domain.conversation import (
    CITATION_CONTENT_MAX_LENGTH,
    CITATION_DOCUMENT_NAME_MAX_LENGTH,
    CITATION_REFERENCE_MAX_LENGTH,
    CONVERSATION_TITLE_MAX_LENGTH,
    MESSAGE_CONTENT_MAX_LENGTH,
    MESSAGE_ERROR_CODE_MAX_LENGTH,
)
from common_agent.domain.employee import (
    EMPLOYEE_DESCRIPTION_MAX_LENGTH,
    EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH,
    EMPLOYEE_NAME_MAX_LENGTH,
    EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH,
)


class PersistenceBase(DeclarativeBase):
    pass


class EmployeeRow(PersistenceBase):
    __tablename__ = "employees"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_employees_id"),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {EMPLOYEE_NAME_MAX_LENGTH} AND name = TRIM(name)",
            name="ck_employees_name",
        ),
        CheckConstraint(
            "CHAR_LENGTH(description) "
            f"<= {EMPLOYEE_DESCRIPTION_MAX_LENGTH} AND description = TRIM(description)",
            name="ck_employees_description",
        ),
        CheckConstraint(
            "CHAR_LENGTH(system_prompt) BETWEEN 1 AND "
            f"{EMPLOYEE_SYSTEM_PROMPT_MAX_LENGTH} AND system_prompt = TRIM(system_prompt)",
            name="ck_employees_system_prompt",
        ),
        CheckConstraint(
            "knowledge_base_id IS NULL OR "
            "(CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND "
            f"{EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH} "
            "AND knowledge_base_id = TRIM(knowledge_base_id))",
            name="ck_employees_knowledge_base_id",
        ),
        CheckConstraint(
            "JSON_TYPE(allowed_workflow_ids) = 'ARRAY'",
            name="ck_employees_allowed_workflow_ids",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_employees_timestamps"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(EMPLOYEE_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(
        String(EMPLOYEE_DESCRIPTION_MAX_LENGTH), nullable=False
    )
    system_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    knowledge_base_id: Mapped[str | None] = mapped_column(
        String(EMPLOYEE_KNOWLEDGE_BASE_ID_MAX_LENGTH), nullable=True
    )
    allowed_workflow_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class ConversationRow(PersistenceBase):
    __tablename__ = "conversations"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_conversations_id"),
        CheckConstraint(
            "CHAR_LENGTH(employee_id) = 36 AND employee_id = TRIM(employee_id)",
            name="ck_conversations_employee_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(title) BETWEEN 1 AND {CONVERSATION_TITLE_MAX_LENGTH} "
            "AND title = TRIM(title)",
            name="ck_conversations_title",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_conversations_timestamps"),
        Index("ix_conversations_employee_updated", "employee_id", "updated_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    employee_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("employees.id", ondelete="RESTRICT", name="fk_conversations_employee_id"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(CONVERSATION_TITLE_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class MessageRow(PersistenceBase):
    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_messages_id"),
        CheckConstraint(
            "CHAR_LENGTH(conversation_id) = 36 AND conversation_id = TRIM(conversation_id)",
            name="ck_messages_conversation_id",
        ),
        CheckConstraint("sequence_number >= 1", name="ck_messages_sequence_number"),
        CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        CheckConstraint(
            "status IN ('pending', 'streaming', 'completed', 'failed', 'stopped')",
            name="ck_messages_status",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(content) <= {MESSAGE_CONTENT_MAX_LENGTH}",
            name="ck_messages_content_length",
        ),
        CheckConstraint(
            "error_code IS NULL OR "
            f"(CHAR_LENGTH(error_code) BETWEEN 1 AND {MESSAGE_ERROR_CODE_MAX_LENGTH} "
            "AND error_code = TRIM(error_code))",
            name="ck_messages_error_code",
        ),
        CheckConstraint(
            "(role = 'user' AND status = 'completed' "
            "AND CHAR_LENGTH(TRIM(content)) >= 1 AND error_code IS NULL) OR "
            "(role = 'assistant' AND ("
            "(status = 'pending' AND CHAR_LENGTH(content) = 0 AND error_code IS NULL) OR "
            "(status = 'streaming' AND error_code IS NULL) OR "
            "(status = 'completed' AND CHAR_LENGTH(TRIM(content)) >= 1 AND error_code IS NULL) OR "
            "(status = 'failed' AND error_code IS NOT NULL) OR "
            "(status = 'stopped' AND error_code IS NULL)))",
            name="ck_messages_role_state",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_messages_timestamps"),
        UniqueConstraint(
            "conversation_id",
            "sequence_number",
            name="uq_messages_conversation_sequence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("conversations.id", ondelete="CASCADE", name="fk_messages_conversation_id"),
        nullable=False,
    )
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(
        String(MESSAGE_ERROR_CODE_MAX_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class MessageCitationRow(PersistenceBase):
    __tablename__ = "message_citations"
    __table_args__ = (
        CheckConstraint("position >= 1", name="ck_message_citations_position"),
        CheckConstraint(
            "CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND "
            f"{CITATION_REFERENCE_MAX_LENGTH} AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_message_citations_knowledge_base_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(chunk_id) BETWEEN 1 AND {CITATION_REFERENCE_MAX_LENGTH} "
            "AND chunk_id = TRIM(chunk_id)",
            name="ck_message_citations_chunk_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(document_id) BETWEEN 1 AND {CITATION_REFERENCE_MAX_LENGTH} "
            "AND document_id = TRIM(document_id)",
            name="ck_message_citations_document_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(document_name) BETWEEN 1 AND {CITATION_DOCUMENT_NAME_MAX_LENGTH} "
            "AND document_name = TRIM(document_name)",
            name="ck_message_citations_document_name",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(TRIM(content)) BETWEEN 1 AND {CITATION_CONTENT_MAX_LENGTH}",
            name="ck_message_citations_content",
        ),
        CheckConstraint("score BETWEEN 0 AND 1", name="ck_message_citations_score"),
    )

    message_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("messages.id", ondelete="CASCADE", name="fk_message_citations_message_id"),
        primary_key=True,
    )
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(CITATION_REFERENCE_MAX_LENGTH), nullable=False
    )
    chunk_id: Mapped[str] = mapped_column(String(CITATION_REFERENCE_MAX_LENGTH), nullable=False)
    document_id: Mapped[str] = mapped_column(String(CITATION_REFERENCE_MAX_LENGTH), nullable=False)
    document_name: Mapped[str] = mapped_column(
        String(CITATION_DOCUMENT_NAME_MAX_LENGTH), nullable=False
    )
    content: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
