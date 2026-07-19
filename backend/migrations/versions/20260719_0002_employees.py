"""建立通用数字员工持久化模型。

Revision ID: 20260719_0002
Revises: 20260719_0001
Create Date: 2026-07-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260719_0002"
down_revision: str | None = "20260719_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "employees",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1_000), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=128), nullable=True),
        sa.Column("allowed_workflow_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_employees_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 128 AND name = TRIM(name)",
            name="ck_employees_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(description) <= 1000 AND description = TRIM(description)",
            name="ck_employees_description",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(system_prompt) BETWEEN 1 AND 12000 "
            "AND system_prompt = TRIM(system_prompt)",
            name="ck_employees_system_prompt",
        ),
        sa.CheckConstraint(
            "knowledge_base_id IS NULL OR "
            "(CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND 128 "
            "AND knowledge_base_id = TRIM(knowledge_base_id))",
            name="ck_employees_knowledge_base_id",
        ),
        sa.CheckConstraint(
            "JSON_TYPE(allowed_workflow_ids) = 'ARRAY'",
            name="ck_employees_allowed_workflow_ids",
        ),
        sa.CheckConstraint("updated_at >= created_at", name="ck_employees_timestamps"),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("employees")
