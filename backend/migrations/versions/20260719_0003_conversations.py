"""建立会话、消息与引用持久化模型。

Revision ID: 20260719_0003
Revises: 20260719_0002
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260719_0003"
down_revision: str | None = "20260719_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("employee_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_conversations_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(employee_id) = 36 AND employee_id = TRIM(employee_id)",
            name="ck_conversations_employee_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(title) BETWEEN 1 AND 200 AND title = TRIM(title)",
            name="ck_conversations_title",
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_conversations_timestamps"),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_conversations_employee_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversations_employee_updated",
        "conversations",
        ["employee_id", "updated_at", "id"],
        unique=False,
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("conversation_id", sa.String(length=36), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_messages_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(conversation_id) = 36 AND conversation_id = TRIM(conversation_id)",
            name="ck_messages_conversation_id",
        ),
        sa.CheckConstraint("sequence_number >= 1", name="ck_messages_sequence_number"),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_messages_role"),
        sa.CheckConstraint(
            "status IN ('pending', 'streaming', 'completed', 'failed', 'stopped')",
            name="ck_messages_status",
        ),
        sa.CheckConstraint("CHAR_LENGTH(content) <= 200000", name="ck_messages_content_length"),
        sa.CheckConstraint(
            "error_code IS NULL OR "
            "(CHAR_LENGTH(error_code) BETWEEN 1 AND 128 AND error_code = TRIM(error_code))",
            name="ck_messages_error_code",
        ),
        sa.CheckConstraint(
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
        sa.CheckConstraint("updated_at >= created_at", name="ck_messages_timestamps"),
        sa.ForeignKeyConstraint(
            ["conversation_id"],
            ["conversations.id"],
            name="fk_messages_conversation_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "conversation_id", "sequence_number", name="uq_messages_conversation_sequence"
        ),
    )
    op.create_table(
        "message_citations",
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=128), nullable=False),
        sa.Column("chunk_id", sa.String(length=128), nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=False),
        sa.Column("document_name", sa.String(length=512), nullable=False),
        sa.Column("content", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.CheckConstraint("position >= 1", name="ck_message_citations_position"),
        sa.CheckConstraint(
            "CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND 128 "
            "AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_message_citations_knowledge_base_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(chunk_id) BETWEEN 1 AND 128 AND chunk_id = TRIM(chunk_id)",
            name="ck_message_citations_chunk_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(document_id) BETWEEN 1 AND 128 AND document_id = TRIM(document_id)",
            name="ck_message_citations_document_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(document_name) BETWEEN 1 AND 512 AND document_name = TRIM(document_name)",
            name="ck_message_citations_document_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(content)) BETWEEN 1 AND 12000",
            name="ck_message_citations_content",
        ),
        sa.CheckConstraint("score BETWEEN 0 AND 1", name="ck_message_citations_score"),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["messages.id"],
            name="fk_message_citations_message_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("message_id", "position"),
    )


def downgrade() -> None:
    op.drop_table("message_citations")
    op.drop_table("messages")
    op.drop_index("ix_conversations_employee_updated", table_name="conversations")
    op.drop_table("conversations")
