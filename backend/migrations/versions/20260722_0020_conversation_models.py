"""增加通用会话来源与逐轮实际模型。

Revision ID: 20260722_0020
Revises: 20260722_0019
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0020"
down_revision: str | None = "20260722_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("source", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column("model_configuration_id", sa.String(length=36), nullable=True),
    )
    op.execute(sa.text("UPDATE conversations SET source = 'employee'"))
    op.alter_column(
        "conversations",
        "source",
        existing_type=sa.String(length=16),
        nullable=False,
    )
    op.alter_column(
        "conversations",
        "employee_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )
    op.create_check_constraint(
        "ck_conversations_source_references",
        "conversations",
        "(source = 'employee' AND employee_id IS NOT NULL "
        "AND model_configuration_id IS NULL) OR "
        "(source = 'generic' AND employee_id IS NULL "
        "AND model_configuration_id IS NOT NULL)",
    )
    op.create_foreign_key(
        "fk_conversations_tenant_model_configuration",
        "conversations",
        "model_configurations",
        ["tenant_id", "model_configuration_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_conversations_tenant_source_created",
        "conversations",
        ["tenant_id", "source", "created_at", "id"],
    )
    op.create_index(
        "ix_conversations_tenant_model_configuration",
        "conversations",
        ["tenant_id", "model_configuration_id"],
    )

    op.add_column(
        "messages",
        sa.Column("model_configuration_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "messages",
        sa.Column("model_identifier", sa.String(length=128), nullable=True),
    )
    op.execute(
        sa.text(
            "UPDATE messages "
            "INNER JOIN conversations ON conversations.id = messages.conversation_id "
            "INNER JOIN employees ON employees.tenant_id = conversations.tenant_id "
            "AND employees.id = conversations.employee_id "
            "INNER JOIN model_configurations ON "
            "model_configurations.tenant_id = employees.tenant_id "
            "AND model_configurations.id = employees.default_model_configuration_id "
            "SET messages.model_configuration_id = model_configurations.id, "
            "messages.model_identifier = model_configurations.model_identifier "
            "WHERE messages.role = 'assistant'"
        )
    )
    op.create_check_constraint(
        "ck_messages_model_selection",
        "messages",
        "(role = 'user' AND model_configuration_id IS NULL "
        "AND model_identifier IS NULL) OR "
        "(role = 'assistant' AND ((model_configuration_id IS NULL "
        "AND model_identifier IS NULL) OR (model_configuration_id IS NOT NULL "
        "AND model_identifier IS NOT NULL "
        "AND CHAR_LENGTH(model_identifier) BETWEEN 1 AND 128 "
        "AND model_identifier = TRIM(model_identifier))))",
    )
    op.create_foreign_key(
        "fk_messages_model_configuration_id",
        "messages",
        "model_configurations",
        ["model_configuration_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_messages_model_configuration",
        "messages",
        ["model_configuration_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_messages_model_configuration", table_name="messages")
    op.drop_constraint(
        "fk_messages_model_configuration_id",
        "messages",
        type_="foreignkey",
    )
    op.drop_constraint("ck_messages_model_selection", "messages", type_="check")
    op.drop_column("messages", "model_identifier")
    op.drop_column("messages", "model_configuration_id")

    op.drop_index(
        "ix_conversations_tenant_model_configuration",
        table_name="conversations",
    )
    op.drop_index("ix_conversations_tenant_source_created", table_name="conversations")
    op.drop_constraint(
        "fk_conversations_tenant_model_configuration",
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint("ck_conversations_source_references", "conversations", type_="check")
    op.alter_column(
        "conversations",
        "employee_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.drop_column("conversations", "model_configuration_id")
    op.drop_column("conversations", "source")
