"""为数字员工增加默认模型引用并回填平台默认模型。

Revision ID: 20260722_0019
Revises: 20260722_0018
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0019"
down_revision: str | None = "20260722_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DEFAULT_MODEL_IDENTIFIER = "qwen-plus"
_DEFAULT_ID_SQL = (
    "LOWER(CONCAT("
    "SUBSTRING(SHA2(CONCAT('common-agent:platform-default-model:', tenants.id), 256), 1, 8), '-', "
    "SUBSTRING(SHA2(CONCAT('common-agent:platform-default-model:', tenants.id), 256), 9, 4), '-', "
    "SUBSTRING(SHA2(CONCAT('common-agent:platform-default-model:', tenants.id), 256), 13, 4), '-', "
    "SUBSTRING(SHA2(CONCAT('common-agent:platform-default-model:', tenants.id), 256), 17, 4), '-', "
    "SUBSTRING(SHA2(CONCAT('common-agent:platform-default-model:', tenants.id), 256), 21, 12)"
    "))"
)


def upgrade() -> None:
    op.add_column(
        "employees",
        sa.Column("default_model_configuration_id", sa.String(length=36), nullable=True),
    )
    op.execute(
        sa.text(
            "INSERT INTO model_configurations "
            "(id, tenant_id, display_name, provider, model_identifier, enabled, "
            "created_at, updated_at) "
            f"SELECT {_DEFAULT_ID_SQL}, tenants.id, "
            "CASE WHEN EXISTS ("
            "SELECT 1 FROM model_configurations named "
            "WHERE named.tenant_id = tenants.id "
            "AND named.display_name = '平台默认模型'"
            ") THEN CONCAT('平台默认模型-', REPLACE(tenants.id, '-', '')) "
            "ELSE '平台默认模型' END, "
            "'bailian', :model_identifier, TRUE, UTC_TIMESTAMP(6), UTC_TIMESTAMP(6) "
            "FROM tenants "
            "WHERE NOT EXISTS ("
            "SELECT 1 FROM model_configurations existing "
            "WHERE existing.tenant_id = tenants.id "
            "AND existing.provider = 'bailian' "
            "AND existing.model_identifier = :model_identifier"
            ")"
        ).bindparams(model_identifier=_DEFAULT_MODEL_IDENTIFIER)
    )
    op.execute(
        sa.text(
            "UPDATE employees "
            "INNER JOIN model_configurations ON "
            "model_configurations.tenant_id = employees.tenant_id "
            "AND model_configurations.provider = 'bailian' "
            "AND model_configurations.model_identifier = :model_identifier "
            "SET employees.default_model_configuration_id = model_configurations.id"
        ).bindparams(model_identifier=_DEFAULT_MODEL_IDENTIFIER)
    )
    op.alter_column(
        "employees",
        "default_model_configuration_id",
        existing_type=sa.String(length=36),
        nullable=False,
    )
    op.create_foreign_key(
        "fk_employees_tenant_default_model",
        "employees",
        "model_configurations",
        ["tenant_id", "default_model_configuration_id"],
        ["tenant_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_employees_tenant_default_model",
        "employees",
        ["tenant_id", "default_model_configuration_id"],
    )
    op.execute(
        sa.text(
            "DELETE model_configuration_references "
            "FROM model_configuration_references "
            "INNER JOIN employees ON "
            "employees.tenant_id = model_configuration_references.tenant_id "
            "AND employees.id = model_configuration_references.resource_id "
            "WHERE model_configuration_references.resource_type = 'employee'"
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO model_configuration_references "
            "(tenant_id, model_configuration_id, resource_type, resource_id, created_at) "
            "SELECT tenant_id, default_model_configuration_id, 'employee', id, UTC_TIMESTAMP(6) "
            "FROM employees"
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "DELETE model_configuration_references "
            "FROM model_configuration_references "
            "INNER JOIN employees ON "
            "employees.tenant_id = model_configuration_references.tenant_id "
            "AND employees.id = model_configuration_references.resource_id "
            "WHERE model_configuration_references.resource_type = 'employee'"
        )
    )
    op.drop_constraint(
        "fk_employees_tenant_default_model",
        "employees",
        type_="foreignkey",
    )
    op.drop_index("ix_employees_tenant_default_model", table_name="employees")
    op.drop_column("employees", "default_model_configuration_id")
    op.execute(
        sa.text(
            "DELETE model_configurations FROM model_configurations "
            "INNER JOIN tenants ON model_configurations.tenant_id = tenants.id "
            f"WHERE model_configurations.id = {_DEFAULT_ID_SQL} "
            "AND model_configurations.provider = 'bailian' "
            "AND model_configurations.model_identifier = :model_identifier "
            "AND NOT EXISTS ("
            "SELECT 1 FROM model_configuration_references refs "
            "WHERE refs.tenant_id = model_configurations.tenant_id "
            "AND refs.model_configuration_id = model_configurations.id"
            ")"
        ).bindparams(model_identifier=_DEFAULT_MODEL_IDENTIFIER)
    )
