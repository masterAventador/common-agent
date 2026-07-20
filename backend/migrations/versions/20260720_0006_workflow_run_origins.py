"""关联员工工作流运行与会话消息。

Revision ID: 20260720_0006
Revises: 20260720_0005
Create Date: 2026-07-20
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260720_0006"
down_revision: str | None = "20260720_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("employee_id", sa.String(36), nullable=True))
    op.add_column("workflow_runs", sa.Column("conversation_id", sa.String(36), nullable=True))
    op.add_column(
        "workflow_runs",
        sa.Column("assistant_message_id", sa.String(36), nullable=True),
    )
    op.create_foreign_key(
        "fk_workflow_runs_assistant_message_id",
        "workflow_runs",
        "messages",
        ["assistant_message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_workflow_runs_origin",
        "workflow_runs",
        "(`trigger` = 'manual' AND employee_id IS NULL "
        "AND conversation_id IS NULL AND assistant_message_id IS NULL) OR "
        "(`trigger` = 'employee' AND employee_id IS NOT NULL "
        "AND conversation_id IS NOT NULL AND assistant_message_id IS NOT NULL)",
    )
    op.create_index(
        "ix_workflow_runs_conversation_created",
        "workflow_runs",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_conversation_created", table_name="workflow_runs")
    op.drop_constraint("ck_workflow_runs_origin", "workflow_runs", type_="check")
    op.drop_constraint(
        "fk_workflow_runs_assistant_message_id",
        "workflow_runs",
        type_="foreignkey",
    )
    op.drop_column("workflow_runs", "assistant_message_id")
    op.drop_column("workflow_runs", "conversation_id")
    op.drop_column("workflow_runs", "employee_id")
