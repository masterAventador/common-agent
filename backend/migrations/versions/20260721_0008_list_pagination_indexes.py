"""为稳定列表分页补齐组合索引。

Revision ID: 20260721_0008
Revises: 20260720_0007
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260721_0008"
down_revision: str | None = "20260720_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index("ix_employees_created", "employees", ["created_at", "id"])
    op.create_index("ix_conversations_created", "conversations", ["created_at", "id"])
    op.create_index(
        "ix_conversations_employee_created",
        "conversations",
        ["employee_id", "created_at", "id"],
    )
    op.create_index("ix_workflows_created", "workflows", ["created_at", "id"])
    op.drop_index("ix_workflow_runs_conversation_created", table_name="workflow_runs")
    op.create_index(
        "ix_workflow_runs_conversation_created",
        "workflow_runs",
        ["conversation_id", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_workflow_runs_conversation_created", table_name="workflow_runs")
    op.create_index(
        "ix_workflow_runs_conversation_created",
        "workflow_runs",
        ["conversation_id", "created_at"],
    )
    op.drop_index("ix_workflows_created", table_name="workflows")
    op.drop_index("ix_conversations_employee_created", table_name="conversations")
    op.drop_index("ix_conversations_created", table_name="conversations")
    op.drop_index("ix_employees_created", table_name="employees")
