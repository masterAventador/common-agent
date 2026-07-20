from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
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
from common_agent.domain.knowledge import (
    KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH,
    KNOWLEDGE_BASE_ID_MAX_LENGTH,
    KNOWLEDGE_BASE_NAME_MAX_LENGTH,
    KNOWLEDGE_DOCUMENT_ERROR_CODE_MAX_LENGTH,
    KNOWLEDGE_DOCUMENT_ID_MAX_LENGTH,
    KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH,
)
from common_agent.domain.workflow import (
    WORKFLOW_DESCRIPTION_MAX_LENGTH,
    WORKFLOW_EDGE_ID_MAX_LENGTH,
    WORKFLOW_NAME_MAX_LENGTH,
    WORKFLOW_NODE_ID_MAX_LENGTH,
)
from common_agent.domain.workflow_run import (
    WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH,
    WORKFLOW_RUN_INPUT_MAX_LENGTH,
    WORKFLOW_RUN_OUTPUT_MAX_LENGTH,
)


class PersistenceBase(DeclarativeBase):
    pass


class DemoKnowledgeBaseRow(PersistenceBase):
    __tablename__ = "demo_knowledge_bases"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {KNOWLEDGE_BASE_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_demo_knowledge_bases_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {KNOWLEDGE_BASE_NAME_MAX_LENGTH} "
            "AND name = TRIM(name)",
            name="ck_demo_knowledge_bases_name",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(description) <= {KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH} "
            "AND description = TRIM(description)",
            name="ck_demo_knowledge_bases_description",
        ),
        UniqueConstraint("name", name="uq_demo_knowledge_bases_name"),
        Index("ix_demo_knowledge_bases_created", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(KNOWLEDGE_BASE_ID_MAX_LENGTH), primary_key=True)
    name: Mapped[str] = mapped_column(String(KNOWLEDGE_BASE_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(
        String(KNOWLEDGE_BASE_DESCRIPTION_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class DemoKnowledgeDocumentRow(PersistenceBase):
    __tablename__ = "demo_knowledge_documents"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {KNOWLEDGE_DOCUMENT_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_demo_knowledge_documents_id",
        ),
        CheckConstraint(
            "CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND "
            f"{KNOWLEDGE_BASE_ID_MAX_LENGTH} AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_demo_knowledge_documents_base_id",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH} "
            "AND name = TRIM(name)",
            name="ck_demo_knowledge_documents_name",
        ),
        CheckConstraint(
            "size_bytes BETWEEN 1 AND 20971520",
            name="ck_demo_knowledge_documents_size",
        ),
        CheckConstraint(
            "parsing_status IN ('uploaded', 'parsing', 'completed', 'failed')",
            name="ck_demo_knowledge_documents_status",
        ),
        CheckConstraint(
            "(parsing_status = 'failed' AND error_code IS NOT NULL) OR "
            "(parsing_status != 'failed' AND error_code IS NULL)",
            name="ck_demo_knowledge_documents_error",
        ),
        CheckConstraint(
            "error_code IS NULL OR "
            f"(CHAR_LENGTH(error_code) BETWEEN 1 AND {KNOWLEDGE_DOCUMENT_ERROR_CODE_MAX_LENGTH} "
            "AND error_code = TRIM(error_code))",
            name="ck_demo_knowledge_documents_error_code",
        ),
        Index(
            "ix_demo_knowledge_documents_base_created",
            "knowledge_base_id",
            "created_at",
            "id",
        ),
    )

    id: Mapped[str] = mapped_column(String(KNOWLEDGE_DOCUMENT_ID_MAX_LENGTH), primary_key=True)
    knowledge_base_id: Mapped[str] = mapped_column(
        String(KNOWLEDGE_BASE_ID_MAX_LENGTH),
        ForeignKey(
            "demo_knowledge_bases.id",
            ondelete="CASCADE",
            name="fk_demo_knowledge_documents_base_id",
        ),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(KNOWLEDGE_DOCUMENT_NAME_MAX_LENGTH), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    parsing_status: Mapped[str] = mapped_column(String(16), nullable=False)
    error_code: Mapped[str | None] = mapped_column(
        String(KNOWLEDGE_DOCUMENT_ERROR_CODE_MAX_LENGTH), nullable=True
    )
    content: Mapped[str] = mapped_column(mysql.LONGTEXT(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


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
        Index("ix_employees_created", "created_at", "id"),
        Index("ix_employees_name_created", "name", "created_at", "id"),
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
        Index("ix_conversations_created", "created_at", "id"),
        Index("ix_conversations_employee_created", "employee_id", "created_at", "id"),
        Index("ix_conversations_title_created", "title", "created_at", "id"),
        Index(
            "ix_conversations_employee_title_created",
            "employee_id",
            "title",
            "created_at",
            "id",
        ),
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


class WorkflowRow(PersistenceBase):
    __tablename__ = "workflows"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_workflows_id"),
        CheckConstraint(
            f"CHAR_LENGTH(name) BETWEEN 1 AND {WORKFLOW_NAME_MAX_LENGTH} AND name = TRIM(name)",
            name="ck_workflows_name",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(description) <= {WORKFLOW_DESCRIPTION_MAX_LENGTH} "
            "AND description = TRIM(description)",
            name="ck_workflows_description",
        ),
        CheckConstraint("updated_at >= created_at", name="ck_workflows_timestamps"),
        Index("ix_workflows_created", "created_at", "id"),
        Index("ix_workflows_name_created", "name", "created_at", "id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(WORKFLOW_NAME_MAX_LENGTH), nullable=False)
    description: Mapped[str] = mapped_column(
        String(WORKFLOW_DESCRIPTION_MAX_LENGTH), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)


class WorkflowNodeRow(PersistenceBase):
    __tablename__ = "workflow_nodes"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_workflow_nodes_id",
        ),
        CheckConstraint("ordinal >= 0", name="ck_workflow_nodes_ordinal"),
        CheckConstraint(
            "type IN ('start', 'ai_chat', 'knowledge_retrieval', 'end')",
            name="ck_workflow_nodes_type",
        ),
        CheckConstraint("JSON_TYPE(config) = 'OBJECT'", name="ck_workflow_nodes_config"),
        UniqueConstraint("workflow_id", "ordinal", name="uq_workflow_nodes_ordinal"),
    )

    workflow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflows.id", ondelete="CASCADE", name="fk_workflow_nodes_workflow_id"),
        primary_key=True,
    )
    id: Mapped[str] = mapped_column(String(WORKFLOW_NODE_ID_MAX_LENGTH), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    position_x: Mapped[float] = mapped_column(mysql.DOUBLE(asdecimal=False), nullable=False)
    position_y: Mapped[float] = mapped_column(mysql.DOUBLE(asdecimal=False), nullable=False)
    config: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)


class WorkflowEdgeRow(PersistenceBase):
    __tablename__ = "workflow_edges"
    __table_args__ = (
        CheckConstraint(
            f"CHAR_LENGTH(id) BETWEEN 1 AND {WORKFLOW_EDGE_ID_MAX_LENGTH} AND id = TRIM(id)",
            name="ck_workflow_edges_id",
        ),
        CheckConstraint("ordinal >= 0", name="ck_workflow_edges_ordinal"),
        CheckConstraint(
            f"CHAR_LENGTH(source) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND source = TRIM(source)",
            name="ck_workflow_edges_source",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(target) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND target = TRIM(target)",
            name="ck_workflow_edges_target",
        ),
        ForeignKeyConstraint(
            ["workflow_id", "source"],
            ["workflow_nodes.workflow_id", "workflow_nodes.id"],
            name="fk_workflow_edges_source",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["workflow_id", "target"],
            ["workflow_nodes.workflow_id", "workflow_nodes.id"],
            name="fk_workflow_edges_target",
            ondelete="CASCADE",
        ),
        UniqueConstraint("workflow_id", "ordinal", name="uq_workflow_edges_ordinal"),
        UniqueConstraint(
            "workflow_id",
            "source",
            "target",
            name="uq_workflow_edges_connection",
        ),
    )

    workflow_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    id: Mapped[str] = mapped_column(String(WORKFLOW_EDGE_ID_MAX_LENGTH), primary_key=True)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    source: Mapped[str] = mapped_column(String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=False)
    target: Mapped[str] = mapped_column(String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=False)


class WorkflowRunRow(PersistenceBase):
    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_workflow_runs_id"),
        CheckConstraint(
            "`trigger` IN ('manual', 'employee')",
            name="ck_workflow_runs_trigger",
        ),
        CheckConstraint(
            "(`trigger` = 'manual' AND employee_id IS NULL "
            "AND conversation_id IS NULL AND assistant_message_id IS NULL) OR "
            "(`trigger` = 'employee' AND employee_id IS NOT NULL "
            "AND conversation_id IS NOT NULL AND assistant_message_id IS NOT NULL)",
            name="ck_workflow_runs_origin",
        ),
        CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'stopped')",
            name="ck_workflow_runs_status",
        ),
        CheckConstraint(
            "current_node_id IS NULL OR "
            f"(CHAR_LENGTH(current_node_id) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND current_node_id = TRIM(current_node_id))",
            name="ck_workflow_runs_current_node_id",
        ),
        CheckConstraint("JSON_TYPE(completed_node_ids) = 'ARRAY'", name="ck_workflow_runs_nodes"),
        CheckConstraint(
            f"CHAR_LENGTH(TRIM(input)) BETWEEN 1 AND {WORKFLOW_RUN_INPUT_MAX_LENGTH}",
            name="ck_workflow_runs_input",
        ),
        CheckConstraint(
            f"CHAR_LENGTH(output) <= {WORKFLOW_RUN_OUTPUT_MAX_LENGTH} "
            "AND (output = '' OR CHAR_LENGTH(TRIM(output)) >= 1)",
            name="ck_workflow_runs_output",
        ),
        CheckConstraint(
            "failed_node_id IS NULL OR "
            f"(CHAR_LENGTH(failed_node_id) BETWEEN 1 AND {WORKFLOW_NODE_ID_MAX_LENGTH} "
            "AND failed_node_id = TRIM(failed_node_id))",
            name="ck_workflow_runs_failed_node_id",
        ),
        CheckConstraint(
            "error_code IS NULL OR "
            f"(CHAR_LENGTH(error_code) BETWEEN 1 AND {WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH} "
            "AND error_code = TRIM(error_code))",
            name="ck_workflow_runs_error_code",
        ),
        CheckConstraint(
            "updated_at >= created_at AND "
            "(started_at IS NULL OR started_at BETWEEN created_at AND updated_at) AND "
            "(finished_at IS NULL OR finished_at = updated_at)",
            name="ck_workflow_runs_timestamps",
        ),
        CheckConstraint(
            "(status = 'pending' AND started_at IS NULL AND finished_at IS NULL "
            "AND current_node_id IS NULL AND JSON_LENGTH(completed_node_ids) = 0 "
            "AND output = '' AND failed_node_id IS NULL AND error_code IS NULL) OR "
            "(status = 'running' AND started_at IS NOT NULL AND finished_at IS NULL "
            "AND output = '' AND failed_node_id IS NULL AND error_code IS NULL) OR "
            "(status = 'completed' AND started_at IS NOT NULL AND finished_at IS NOT NULL "
            "AND CHAR_LENGTH(TRIM(output)) >= 1 AND failed_node_id IS NULL "
            "AND error_code IS NULL) OR "
            "(status = 'failed' AND finished_at IS NOT NULL AND output = '' "
            "AND error_code IS NOT NULL AND "
            "((failed_node_id IS NULL AND current_node_id IS NULL) "
            "OR failed_node_id = current_node_id)) OR "
            "(status = 'stopped' AND finished_at IS NOT NULL AND output = '' "
            "AND failed_node_id IS NULL AND error_code IS NULL)",
            name="ck_workflow_runs_state",
        ),
        Index("ix_workflow_runs_workflow_created", "workflow_id", "created_at"),
        Index(
            "ix_workflow_runs_conversation_created",
            "conversation_id",
            "created_at",
            "id",
        ),
        Index(
            "ix_workflow_runs_conversation_input_created",
            "conversation_id",
            "input",
            "created_at",
            "id",
            mysql_length={"input": 191},
        ),
        Index(
            "ix_workflow_runs_conversation_status_created",
            "conversation_id",
            "status",
            "created_at",
            "id",
        ),
        Index("ix_workflow_runs_status", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("workflows.id", ondelete="CASCADE", name="fk_workflow_runs_workflow_id"),
        nullable=False,
    )
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    employee_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    conversation_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    assistant_message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey(
            "messages.id",
            ondelete="CASCADE",
            name="fk_workflow_runs_assistant_message_id",
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    input: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    output: Mapped[str] = mapped_column(mysql.MEDIUMTEXT(), nullable=False)
    current_node_id: Mapped[str | None] = mapped_column(
        String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=True
    )
    completed_node_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    failed_node_id: Mapped[str | None] = mapped_column(
        String(WORKFLOW_NODE_ID_MAX_LENGTH), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(
        String(WORKFLOW_RUN_ERROR_CODE_MAX_LENGTH), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(mysql.DATETIME(fsp=6), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(mysql.DATETIME(fsp=6), nullable=False)
