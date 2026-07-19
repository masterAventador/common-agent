"""建立工作流定义、节点与边持久化模型。

Revision ID: 20260720_0004
Revises: 20260719_0003
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260720_0004"
down_revision: str | None = "20260719_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflows",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1_000), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_workflows_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 128 AND name = TRIM(name)",
            name="ck_workflows_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(description) <= 1000 AND description = TRIM(description)",
            name="ck_workflows_description",
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_workflows_timestamps"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "workflow_nodes",
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=32), nullable=False),
        sa.Column("position_x", mysql.DOUBLE(), nullable=False),
        sa.Column("position_y", mysql.DOUBLE(), nullable=False),
        sa.Column("config", sa.JSON(), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) BETWEEN 1 AND 128 AND id = TRIM(id)",
            name="ck_workflow_nodes_id",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_workflow_nodes_ordinal"),
        sa.CheckConstraint(
            "type IN ('start', 'ai_chat', 'knowledge_retrieval', 'end')",
            name="ck_workflow_nodes_type",
        ),
        sa.CheckConstraint("JSON_TYPE(config) = 'OBJECT'", name="ck_workflow_nodes_config"),
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name="fk_workflow_nodes_workflow_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workflow_id", "id"),
        sa.UniqueConstraint("workflow_id", "ordinal", name="uq_workflow_nodes_ordinal"),
    )
    op.create_table(
        "workflow_edges",
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=128), nullable=False),
        sa.Column("target", sa.String(length=128), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) BETWEEN 1 AND 128 AND id = TRIM(id)",
            name="ck_workflow_edges_id",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_workflow_edges_ordinal"),
        sa.CheckConstraint(
            "CHAR_LENGTH(source) BETWEEN 1 AND 128 AND source = TRIM(source)",
            name="ck_workflow_edges_source",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(target) BETWEEN 1 AND 128 AND target = TRIM(target)",
            name="ck_workflow_edges_target",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "source"],
            ["workflow_nodes.workflow_id", "workflow_nodes.id"],
            name="fk_workflow_edges_source",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "target"],
            ["workflow_nodes.workflow_id", "workflow_nodes.id"],
            name="fk_workflow_edges_target",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("workflow_id", "id"),
        sa.UniqueConstraint("workflow_id", "ordinal", name="uq_workflow_edges_ordinal"),
        sa.UniqueConstraint(
            "workflow_id",
            "source",
            "target",
            name="uq_workflow_edges_connection",
        ),
    )


def downgrade() -> None:
    op.drop_table("workflow_edges")
    op.drop_table("workflow_nodes")
    op.drop_table("workflows")
