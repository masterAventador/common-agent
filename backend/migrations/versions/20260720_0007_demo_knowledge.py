"""持久化 Demo 知识库与文档。

Revision ID: 20260720_0007
Revises: 20260720_0006
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260720_0007"
down_revision: str | None = "20260720_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "demo_knowledge_bases",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.String(1024), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) BETWEEN 1 AND 128 AND id = TRIM(id)",
            name="ck_demo_knowledge_bases_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 128 AND name = TRIM(name)",
            name="ck_demo_knowledge_bases_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(description) <= 1024 AND description = TRIM(description)",
            name="ck_demo_knowledge_bases_description",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_demo_knowledge_bases_name"),
    )
    op.create_index(
        "ix_demo_knowledge_bases_created",
        "demo_knowledge_bases",
        ["created_at", "id"],
    )
    op.create_table(
        "demo_knowledge_documents",
        sa.Column("id", sa.String(128), nullable=False),
        sa.Column("knowledge_base_id", sa.String(128), nullable=False),
        sa.Column("name", sa.String(1024), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("parsing_status", sa.String(16), nullable=False),
        sa.Column("error_code", sa.String(128), nullable=True),
        sa.Column("content", mysql.LONGTEXT(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) BETWEEN 1 AND 128 AND id = TRIM(id)",
            name="ck_demo_knowledge_documents_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND 128 "
            "AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_demo_knowledge_documents_base_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 1024 AND name = TRIM(name)",
            name="ck_demo_knowledge_documents_name",
        ),
        sa.CheckConstraint(
            "size_bytes BETWEEN 1 AND 20971520",
            name="ck_demo_knowledge_documents_size",
        ),
        sa.CheckConstraint(
            "parsing_status IN ('uploaded', 'parsing', 'completed', 'failed')",
            name="ck_demo_knowledge_documents_status",
        ),
        sa.CheckConstraint(
            "(parsing_status = 'failed' AND error_code IS NOT NULL) OR "
            "(parsing_status != 'failed' AND error_code IS NULL)",
            name="ck_demo_knowledge_documents_error",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR (CHAR_LENGTH(error_code) BETWEEN 1 AND 128 "
            "AND error_code = TRIM(error_code))",
            name="ck_demo_knowledge_documents_error_code",
        ),
        sa.ForeignKeyConstraint(
            ["knowledge_base_id"],
            ["demo_knowledge_bases.id"],
            name="fk_demo_knowledge_documents_base_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_demo_knowledge_documents_base_created",
        "demo_knowledge_documents",
        ["knowledge_base_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_demo_knowledge_documents_base_created",
        table_name="demo_knowledge_documents",
    )
    op.drop_table("demo_knowledge_documents")
    op.drop_index("ix_demo_knowledge_bases_created", table_name="demo_knowledge_bases")
    op.drop_table("demo_knowledge_bases")
