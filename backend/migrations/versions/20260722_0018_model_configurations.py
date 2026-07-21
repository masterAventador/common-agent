"""增加租户隔离的百炼模型配置与通用引用表。

Revision ID: 20260722_0018
Revises: 20260721_0017
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260722_0018"
down_revision: str | None = "20260721_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_configurations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("model_identifier", sa.String(length=128), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) = 36 AND id = TRIM(id)",
            name="ck_model_configurations_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(display_name) BETWEEN 1 AND 128 AND display_name = TRIM(display_name)",
            name="ck_model_configurations_display_name",
        ),
        sa.CheckConstraint(
            "provider = 'bailian'",
            name="ck_model_configurations_provider",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(model_identifier) BETWEEN 1 AND 128 "
            "AND model_identifier = TRIM(model_identifier)",
            name="ck_model_configurations_identifier",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_model_configurations_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_model_configurations_tenant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_model_configurations_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "display_name",
            name="uq_model_configurations_tenant_name",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "provider",
            "model_identifier",
            name="uq_model_configurations_tenant_provider_identifier",
        ),
    )
    op.create_index(
        "ix_model_configurations_tenant_created",
        "model_configurations",
        ["tenant_id", "created_at", "id"],
    )
    op.create_index(
        "ix_model_configurations_tenant_enabled_created",
        "model_configurations",
        ["tenant_id", "enabled", "created_at", "id"],
    )
    op.create_index(
        "ix_model_configurations_tenant_name_created",
        "model_configurations",
        ["tenant_id", "display_name", "created_at", "id"],
    )

    op.create_table(
        "model_configuration_references",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("model_configuration_id", sa.String(length=36), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=False),
        sa.Column("resource_id", sa.String(length=128), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "resource_type IN ('employee', 'workflow', 'conversation')",
            name="ck_model_configuration_references_type",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(resource_id) BETWEEN 1 AND 128 AND resource_id = TRIM(resource_id)",
            name="ck_model_configuration_references_resource_id",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_model_configuration_references_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "model_configuration_id"],
            ["model_configurations.tenant_id", "model_configurations.id"],
            name="fk_model_configuration_references_configuration",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "model_configuration_id",
            "resource_type",
            "resource_id",
        ),
    )
    op.create_index(
        "ix_model_configuration_references_resource",
        "model_configuration_references",
        ["tenant_id", "resource_type", "resource_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_model_configuration_references_resource",
        table_name="model_configuration_references",
    )
    op.drop_table("model_configuration_references")
    op.drop_index(
        "ix_model_configurations_tenant_name_created",
        table_name="model_configurations",
    )
    op.drop_index(
        "ix_model_configurations_tenant_enabled_created",
        table_name="model_configurations",
    )
    op.drop_index(
        "ix_model_configurations_tenant_created",
        table_name="model_configurations",
    )
    op.drop_table("model_configurations")
