"""为平台资源和 RAGFlow 引用增加租户归属。

Revision ID: 20260721_0014
Revises: 20260721_0013
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260721_0014"
down_revision: str | None = "20260721_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_TENANT_ID = "00000000-0000-4000-8000-000000000002"

_RESOURCE_TABLES = (
    "demo_knowledge_bases",
    "demo_knowledge_documents",
    "employees",
    "conversations",
    "workflows",
    "workflow_runs",
)

_LEGACY_FOREIGN_KEYS = (
    ("demo_knowledge_documents", "fk_demo_knowledge_documents_base_id"),
    ("conversations", "fk_conversations_employee_id"),
    ("workflow_runs", "fk_workflow_runs_workflow_id"),
    ("workflow_runs", "fk_workflow_runs_assistant_message_id"),
)

_LEGACY_INDEXES = (
    ("demo_knowledge_bases", "ix_demo_knowledge_bases_created", ("created_at", "id"), {}),
    (
        "demo_knowledge_documents",
        "ix_demo_knowledge_documents_base_created",
        ("knowledge_base_id", "created_at", "id"),
        {},
    ),
    ("employees", "ix_employees_created", ("created_at", "id"), {}),
    ("employees", "ix_employees_name_created", ("name", "created_at", "id"), {}),
    ("conversations", "ix_conversations_created", ("created_at", "id"), {}),
    (
        "conversations",
        "ix_conversations_employee_created",
        ("employee_id", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_title_created",
        ("title", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_employee_title_created",
        ("employee_id", "title", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_employee_updated",
        ("employee_id", "updated_at", "id"),
        {},
    ),
    ("workflows", "ix_workflows_created", ("created_at", "id"), {}),
    ("workflows", "ix_workflows_name_created", ("name", "created_at", "id"), {}),
    (
        "workflow_runs",
        "ix_workflow_runs_workflow_created",
        ("workflow_id", "created_at"),
        {},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_conversation_created",
        ("conversation_id", "created_at", "id"),
        {},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_conversation_input_created",
        ("conversation_id", "input", "created_at", "id"),
        {"mysql_length": {"input": 191}},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_conversation_status_created",
        ("conversation_id", "status", "created_at", "id"),
        {},
    ),
    ("workflow_runs", "ix_workflow_runs_status", ("status",), {}),
)

_TENANT_INDEXES = (
    (
        "demo_knowledge_bases",
        "ix_demo_knowledge_bases_tenant_created",
        ("tenant_id", "created_at", "id"),
        {},
    ),
    (
        "demo_knowledge_documents",
        "ix_demo_knowledge_documents_tenant_base_created",
        ("tenant_id", "knowledge_base_id", "created_at", "id"),
        {},
    ),
    (
        "employees",
        "ix_employees_tenant_created",
        ("tenant_id", "created_at", "id"),
        {},
    ),
    (
        "employees",
        "ix_employees_tenant_name_created",
        ("tenant_id", "name", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_tenant_created",
        ("tenant_id", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_tenant_employee_created",
        ("tenant_id", "employee_id", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_tenant_title_created",
        ("tenant_id", "title", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_tenant_employee_title_created",
        ("tenant_id", "employee_id", "title", "created_at", "id"),
        {},
    ),
    (
        "conversations",
        "ix_conversations_tenant_employee_updated",
        ("tenant_id", "employee_id", "updated_at", "id"),
        {},
    ),
    (
        "workflows",
        "ix_workflows_tenant_created",
        ("tenant_id", "created_at", "id"),
        {},
    ),
    (
        "workflows",
        "ix_workflows_tenant_name_created",
        ("tenant_id", "name", "created_at", "id"),
        {},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_tenant_workflow_created",
        ("tenant_id", "workflow_id", "created_at"),
        {},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_tenant_conversation_created",
        ("tenant_id", "conversation_id", "created_at", "id"),
        {},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_tenant_conversation_input_created",
        ("tenant_id", "conversation_id", "input", "created_at", "id"),
        {"mysql_length": {"input": 191}},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_tenant_conversation_status_created",
        ("tenant_id", "conversation_id", "status", "created_at", "id"),
        {},
    ),
    (
        "workflow_runs",
        "ix_workflow_runs_tenant_status",
        ("tenant_id", "status"),
        {},
    ),
)


def upgrade() -> None:
    for table in _RESOURCE_TABLES:
        op.add_column(
            table,
            sa.Column(
                "tenant_id",
                sa.String(length=36),
                nullable=False,
                server_default=DEFAULT_TENANT_ID,
            ),
        )
        op.create_foreign_key(
            f"fk_{table}_tenant_id",
            table,
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )
        op.alter_column(table, "tenant_id", server_default=None)

    for table, constraint in _LEGACY_FOREIGN_KEYS:
        op.drop_constraint(constraint, table, type_="foreignkey")
    op.drop_index(
        "fk_workflow_runs_assistant_message_id",
        table_name="workflow_runs",
    )
    for table, index, _columns, _kwargs in _LEGACY_INDEXES:
        op.drop_index(index, table_name=table)
    for table, index, columns, kwargs in _TENANT_INDEXES:
        op.create_index(index, table, list(columns), **kwargs)

    op.drop_constraint("uq_demo_knowledge_bases_name", "demo_knowledge_bases", type_="unique")
    op.create_unique_constraint(
        "uq_demo_knowledge_bases_tenant_name",
        "demo_knowledge_bases",
        ["tenant_id", "name"],
    )
    op.create_unique_constraint(
        "uq_demo_knowledge_bases_tenant_id",
        "demo_knowledge_bases",
        ["tenant_id", "id"],
    )
    op.create_unique_constraint("uq_employees_tenant_id", "employees", ["tenant_id", "id"])
    op.create_unique_constraint(
        "uq_conversations_tenant_id",
        "conversations",
        ["tenant_id", "id"],
    )
    op.create_unique_constraint(
        "uq_conversations_tenant_id_employee",
        "conversations",
        ["tenant_id", "id", "employee_id"],
    )
    op.create_unique_constraint(
        "uq_messages_conversation_id",
        "messages",
        ["conversation_id", "id"],
    )
    op.create_unique_constraint("uq_workflows_tenant_id", "workflows", ["tenant_id", "id"])

    op.create_foreign_key(
        "fk_demo_knowledge_documents_tenant_base",
        "demo_knowledge_documents",
        "demo_knowledge_bases",
        ["tenant_id", "knowledge_base_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_conversations_tenant_employee",
        "conversations",
        "employees",
        ["tenant_id", "employee_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_workflow_runs_tenant_workflow",
        "workflow_runs",
        "workflows",
        ["tenant_id", "workflow_id"],
        ["tenant_id", "id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_workflow_runs_tenant_origin",
        "workflow_runs",
        "conversations",
        ["tenant_id", "conversation_id", "employee_id"],
        ["tenant_id", "id", "employee_id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_workflow_runs_conversation_message",
        "workflow_runs",
        "messages",
        ["conversation_id", "assistant_message_id"],
        ["conversation_id", "id"],
        ondelete="CASCADE",
    )

    op.create_table(
        "ragflow_knowledge_base_ownerships",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("knowledge_base_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(knowledge_base_id) BETWEEN 1 AND 128 "
            "AND knowledge_base_id = TRIM(knowledge_base_id)",
            name="ck_ragflow_knowledge_ownership_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_ragflow_knowledge_ownership_tenant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "knowledge_base_id"),
        sa.UniqueConstraint(
            "knowledge_base_id",
            name="uq_ragflow_knowledge_ownership_external_id",
        ),
    )
    op.create_index(
        "ix_ragflow_knowledge_ownership_tenant",
        "ragflow_knowledge_base_ownerships",
        ["tenant_id", "knowledge_base_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_ragflow_knowledge_ownership_tenant",
        table_name="ragflow_knowledge_base_ownerships",
    )
    op.drop_table("ragflow_knowledge_base_ownerships")

    for constraint in (
        "fk_workflow_runs_conversation_message",
        "fk_workflow_runs_tenant_origin",
        "fk_workflow_runs_tenant_workflow",
    ):
        op.drop_constraint(constraint, "workflow_runs", type_="foreignkey")
    # MySQL keeps automatically-created supporting indexes after the foreign
    # keys are removed.  Drop them explicitly so a later upgrade can recreate
    # the constraints with the same names.
    for index in (
        "fk_workflow_runs_conversation_message",
        "fk_workflow_runs_tenant_origin",
    ):
        op.drop_index(index, table_name="workflow_runs")
    op.drop_constraint(
        "fk_conversations_tenant_employee",
        "conversations",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_demo_knowledge_documents_tenant_base",
        "demo_knowledge_documents",
        type_="foreignkey",
    )

    # MySQL may reuse the first tenant-prefixed index as the supporting index
    # for these direct tenant foreign keys.  Release the foreign keys before
    # replacing the tenant indexes, otherwise DROP INDEX fails with error 1553.
    for table in reversed(_RESOURCE_TABLES):
        op.drop_constraint(f"fk_{table}_tenant_id", table, type_="foreignkey")

    op.drop_constraint("uq_workflows_tenant_id", "workflows", type_="unique")
    op.drop_constraint("uq_messages_conversation_id", "messages", type_="unique")
    op.drop_constraint(
        "uq_conversations_tenant_id_employee",
        "conversations",
        type_="unique",
    )
    op.drop_constraint("uq_conversations_tenant_id", "conversations", type_="unique")
    op.drop_constraint("uq_employees_tenant_id", "employees", type_="unique")
    op.drop_constraint(
        "uq_demo_knowledge_bases_tenant_id",
        "demo_knowledge_bases",
        type_="unique",
    )
    op.drop_constraint(
        "uq_demo_knowledge_bases_tenant_name",
        "demo_knowledge_bases",
        type_="unique",
    )
    op.create_unique_constraint(
        "uq_demo_knowledge_bases_name",
        "demo_knowledge_bases",
        ["name"],
    )

    for table, index, _columns, _kwargs in reversed(_TENANT_INDEXES):
        op.drop_index(index, table_name=table)
    for table, index, columns, kwargs in _LEGACY_INDEXES:
        op.create_index(index, table, list(columns), **kwargs)

    op.create_foreign_key(
        "fk_demo_knowledge_documents_base_id",
        "demo_knowledge_documents",
        "demo_knowledge_bases",
        ["knowledge_base_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_conversations_employee_id",
        "conversations",
        "employees",
        ["employee_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_workflow_runs_workflow_id",
        "workflow_runs",
        "workflows",
        ["workflow_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_foreign_key(
        "fk_workflow_runs_assistant_message_id",
        "workflow_runs",
        "messages",
        ["assistant_message_id"],
        ["id"],
        ondelete="CASCADE",
    )
    for table in reversed(_RESOURCE_TABLES):
        op.drop_column(table, "tenant_id")
