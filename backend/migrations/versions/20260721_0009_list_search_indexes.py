"""为大列表前缀搜索补齐组合索引。

Revision ID: 20260721_0009
Revises: 20260721_0008
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260721_0009"
down_revision: str | None = "20260721_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_employees_name_created",
        "employees",
        ["name", "created_at", "id"],
    )
    op.create_index(
        "ix_conversations_title_created",
        "conversations",
        ["title", "created_at", "id"],
    )
    op.create_index(
        "ix_conversations_employee_title_created",
        "conversations",
        ["employee_id", "title", "created_at", "id"],
    )
    op.create_index(
        "ix_workflows_name_created",
        "workflows",
        ["name", "created_at", "id"],
    )
    op.create_index(
        "ix_workflow_runs_conversation_input_created",
        "workflow_runs",
        ["conversation_id", "input", "created_at", "id"],
        mysql_length={"input": 191},
    )
    op.create_index(
        "ix_workflow_runs_conversation_status_created",
        "workflow_runs",
        ["conversation_id", "status", "created_at", "id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_workflow_runs_conversation_status_created",
        table_name="workflow_runs",
    )
    op.drop_index(
        "ix_workflow_runs_conversation_input_created",
        table_name="workflow_runs",
    )
    op.drop_index("ix_workflows_name_created", table_name="workflows")
    op.drop_index(
        "ix_conversations_employee_title_created",
        table_name="conversations",
    )
    op.drop_index("ix_conversations_title_created", table_name="conversations")
    op.drop_index("ix_employees_name_created", table_name="employees")
