"""按更新时间索引全局会话历史。

Revision ID: 20260722_0021
Revises: 20260722_0020
Create Date: 2026-07-22
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260722_0021"
down_revision: str | None = "20260722_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    for index_name in (
        "ix_conversations_tenant_created",
        "ix_conversations_tenant_source_created",
        "ix_conversations_tenant_employee_created",
        "ix_conversations_tenant_title_created",
        "ix_conversations_tenant_employee_title_created",
    ):
        op.drop_index(index_name, table_name="conversations")

    op.create_index(
        "ix_conversations_tenant_updated",
        "conversations",
        ["tenant_id", "updated_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_source_updated",
        "conversations",
        ["tenant_id", "source", "updated_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_title_updated",
        "conversations",
        ["tenant_id", "title", "updated_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_employee_title_updated",
        "conversations",
        ["tenant_id", "employee_id", "title", "updated_at", "id"],
    )


def downgrade() -> None:
    for index_name in (
        "ix_conversations_tenant_employee_title_updated",
        "ix_conversations_tenant_title_updated",
        "ix_conversations_tenant_source_updated",
        "ix_conversations_tenant_updated",
    ):
        op.drop_index(index_name, table_name="conversations")

    op.create_index(
        "ix_conversations_tenant_created",
        "conversations",
        ["tenant_id", "created_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_source_created",
        "conversations",
        ["tenant_id", "source", "created_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_employee_created",
        "conversations",
        ["tenant_id", "employee_id", "created_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_title_created",
        "conversations",
        ["tenant_id", "title", "created_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_employee_title_created",
        "conversations",
        ["tenant_id", "employee_id", "title", "created_at", "id"],
    )
