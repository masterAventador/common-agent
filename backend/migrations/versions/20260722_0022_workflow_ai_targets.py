"""增加工作流 AI 节点执行目标与运行快照。

Revision ID: 20260722_0022
Revises: 20260722_0021
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0022"
down_revision: str | None = "20260722_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("workflow_runs", sa.Column("ai_targets", sa.JSON(), nullable=True))
    op.execute(sa.text("UPDATE workflow_runs SET ai_targets = JSON_ARRAY()"))
    op.alter_column("workflow_runs", "ai_targets", existing_type=sa.JSON(), nullable=False)
    op.create_check_constraint(
        "ck_workflow_runs_ai_targets",
        "workflow_runs",
        "JSON_TYPE(ai_targets) = 'ARRAY'",
    )

    op.create_table(
        "workflow_ai_chat_targets",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("workflow_id", sa.String(length=36), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("target_type", sa.String(length=16), nullable=False),
        sa.Column("employee_id", sa.String(length=36), nullable=True),
        sa.Column("model_configuration_id", sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            "target_type IN ('employee', 'model')",
            name="ck_workflow_ai_chat_targets_type",
        ),
        sa.CheckConstraint(
            "(target_type = 'employee' AND employee_id IS NOT NULL "
            "AND model_configuration_id IS NULL) OR "
            "(target_type = 'model' AND employee_id IS NULL "
            "AND model_configuration_id IS NOT NULL)",
            name="ck_workflow_ai_chat_targets_value",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "node_id"],
            ["workflow_nodes.workflow_id", "workflow_nodes.id"],
            name="fk_workflow_ai_chat_targets_node",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "workflow_id"],
            ["workflows.tenant_id", "workflows.id"],
            name="fk_workflow_ai_chat_targets_workflow",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "employee_id"],
            ["employees.tenant_id", "employees.id"],
            name="fk_workflow_ai_chat_targets_employee",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "model_configuration_id"],
            ["model_configurations.tenant_id", "model_configurations.id"],
            name="fk_workflow_ai_chat_targets_model",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "workflow_id", "node_id"),
    )
    op.create_index(
        "ix_workflow_ai_chat_targets_employee",
        "workflow_ai_chat_targets",
        ["tenant_id", "employee_id"],
    )
    op.create_index(
        "ix_workflow_ai_chat_targets_model",
        "workflow_ai_chat_targets",
        ["tenant_id", "model_configuration_id"],
    )

    op.execute(
        sa.text(
            "UPDATE workflow_nodes nodes "
            "INNER JOIN workflows ON workflows.id = nodes.workflow_id "
            "INNER JOIN model_configurations models ON "
            "models.tenant_id = workflows.tenant_id "
            "AND models.provider = 'bailian' "
            "AND models.model_identifier = 'qwen-plus' "
            "SET nodes.config = JSON_SET(nodes.config, '$.target', JSON_OBJECT("
            "'type', 'model', 'model_configuration_id', models.id)) "
            "WHERE nodes.type = 'ai_chat'"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO workflow_ai_chat_targets "
            "(tenant_id, workflow_id, node_id, target_type, employee_id, "
            "model_configuration_id) "
            "SELECT workflows.tenant_id, nodes.workflow_id, nodes.id, 'model', NULL, "
            "JSON_UNQUOTE(JSON_EXTRACT(nodes.config, '$.target.model_configuration_id')) "
            "FROM workflow_nodes nodes "
            "INNER JOIN workflows ON workflows.id = nodes.workflow_id "
            "WHERE nodes.type = 'ai_chat'"
        )
    )
    op.execute(
        sa.text(
            "INSERT IGNORE INTO model_configuration_references "
            "(tenant_id, model_configuration_id, resource_type, resource_id, created_at) "
            "SELECT tenant_id, model_configuration_id, 'workflow', workflow_id, "
            "UTC_TIMESTAMP(6) FROM workflow_ai_chat_targets "
            "WHERE target_type = 'model'"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM model_configuration_references WHERE resource_type = 'workflow'")
    )
    op.execute(
        sa.text(
            "UPDATE workflow_nodes SET config = JSON_REMOVE(config, '$.target') "
            "WHERE type = 'ai_chat'"
        )
    )
    op.drop_index(
        "ix_workflow_ai_chat_targets_model",
        table_name="workflow_ai_chat_targets",
    )
    op.drop_index(
        "ix_workflow_ai_chat_targets_employee",
        table_name="workflow_ai_chat_targets",
    )
    op.drop_table("workflow_ai_chat_targets")
    op.drop_constraint("ck_workflow_runs_ai_targets", "workflow_runs", type_="check")
    op.drop_column("workflow_runs", "ai_targets")
