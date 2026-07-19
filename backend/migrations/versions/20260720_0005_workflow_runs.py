"""建立工作流运行摘要持久化模型。

Revision ID: 20260720_0005
Revises: 20260720_0004
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260720_0005"
down_revision: str | None = "20260720_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("input", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("output", mysql.MEDIUMTEXT(), nullable=False),
        sa.Column("current_node_id", sa.String(length=128), nullable=True),
        sa.Column("completed_node_ids", sa.JSON(), nullable=False),
        sa.Column("failed_node_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("started_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("finished_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_workflow_runs_id"),
        sa.CheckConstraint(
            "`trigger` IN ('manual', 'employee')",
            name="ck_workflow_runs_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'completed', 'failed', 'stopped')",
            name="ck_workflow_runs_status",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(TRIM(input)) BETWEEN 1 AND 200000",
            name="ck_workflow_runs_input",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(output) <= 200000 "
            "AND (output = '' OR CHAR_LENGTH(TRIM(output)) >= 1)",
            name="ck_workflow_runs_output",
        ),
        sa.CheckConstraint(
            "current_node_id IS NULL OR "
            "(CHAR_LENGTH(current_node_id) BETWEEN 1 AND 128 "
            "AND current_node_id = TRIM(current_node_id))",
            name="ck_workflow_runs_current_node_id",
        ),
        sa.CheckConstraint(
            "JSON_TYPE(completed_node_ids) = 'ARRAY'",
            name="ck_workflow_runs_nodes",
        ),
        sa.CheckConstraint(
            "failed_node_id IS NULL OR "
            "(CHAR_LENGTH(failed_node_id) BETWEEN 1 AND 128 "
            "AND failed_node_id = TRIM(failed_node_id))",
            name="ck_workflow_runs_failed_node_id",
        ),
        sa.CheckConstraint(
            "error_code IS NULL OR "
            "(CHAR_LENGTH(error_code) BETWEEN 1 AND 128 AND error_code = TRIM(error_code))",
            name="ck_workflow_runs_error_code",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at AND "
            "(started_at IS NULL OR started_at BETWEEN created_at AND updated_at) AND "
            "(finished_at IS NULL OR finished_at = updated_at)",
            name="ck_workflow_runs_timestamps",
        ),
        sa.CheckConstraint(
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
        sa.ForeignKeyConstraint(
            ["workflow_id"],
            ["workflows.id"],
            name="fk_workflow_runs_workflow_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_workflow_runs_workflow_created",
        "workflow_runs",
        ["workflow_id", "created_at"],
    )
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_status", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workflow_created", table_name="workflow_runs")
    op.drop_table("workflow_runs")
