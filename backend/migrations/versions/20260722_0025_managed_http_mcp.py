"""增加托管 HTTP MCP 能力映射。

Revision ID: 20260722_0025
Revises: 20260722_0024
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260722_0025"
down_revision: str | None = "20260722_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "managed_http_capabilities",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("http_method", sa.String(length=8), nullable=False),
        sa.Column("path_template", sa.String(length=2048), nullable=False),
        sa.Column("parameter_bindings", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.SmallInteger(), nullable=False),
        sa.Column("response_json_pointer", sa.String(length=1024), nullable=True),
        sa.CheckConstraint(
            "http_method IN ('GET', 'POST', 'PUT', 'PATCH', 'DELETE')",
            name="ck_managed_http_capabilities_method",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(path_template) BETWEEN 1 AND 2048 "
            "AND path_template = TRIM(path_template)",
            name="ck_managed_http_capabilities_path",
        ),
        sa.CheckConstraint(
            "JSON_TYPE(parameter_bindings) = 'ARRAY' "
            "AND JSON_LENGTH(parameter_bindings) <= 256",
            name="ck_managed_http_capabilities_bindings",
        ),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 300",
            name="ck_managed_http_capabilities_timeout",
        ),
        sa.CheckConstraint(
            "response_json_pointer IS NULL OR "
            "(CHAR_LENGTH(response_json_pointer) BETWEEN 1 AND 1024 "
            "AND response_json_pointer = TRIM(response_json_pointer))",
            name="ck_managed_http_capabilities_pointer",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_managed_http_capabilities_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "capability_id"],
            ["tool_capabilities.tenant_id", "tool_capabilities.id"],
            name="fk_managed_http_capabilities_capability",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "capability_id"),
    )
    op.create_index(
        "ix_managed_http_capabilities_tenant",
        "managed_http_capabilities",
        ["tenant_id", "capability_id"],
    )


def downgrade() -> None:
    op.drop_table("managed_http_capabilities")
