"""增加租户级工具目录、集合选择与精确授权。

Revision ID: 20260722_0023
Revises: 20260722_0022
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260722_0023"
down_revision: str | None = "20260722_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_sources",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("source_type", sa.String(length=24), nullable=False),
        sa.Column("endpoint_url", sa.String(length=2048), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) = 36 AND id = TRIM(id)",
            name="ck_mcp_sources_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 128 AND name = TRIM(name)",
            name="ck_mcp_sources_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(description) <= 1000 AND description = TRIM(description)",
            name="ck_mcp_sources_description",
        ),
        sa.CheckConstraint(
            "source_type IN ('platform', 'managed_http', 'external')",
            name="ck_mcp_sources_type",
        ),
        sa.CheckConstraint(
            "(source_type = 'platform' AND endpoint_url IS NULL) OR "
            "(source_type IN ('managed_http', 'external') AND endpoint_url IS NOT NULL)",
            name="ck_mcp_sources_endpoint",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'ready', 'unavailable', 'disabled')",
            name="ck_mcp_sources_status",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_mcp_sources_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_mcp_sources_tenant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_mcp_sources_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_mcp_sources_tenant_name"),
    )
    op.create_index(
        "ix_mcp_sources_tenant_created",
        "mcp_sources",
        ["tenant_id", "created_at", "id"],
    )
    op.create_index(
        "ix_mcp_sources_tenant_type_status",
        "mcp_sources",
        ["tenant_id", "source_type", "status"],
    )

    op.create_table(
        "tool_capabilities",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("remote_name", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("input_schema", sa.JSON(), nullable=False),
        sa.Column("schema_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) = 36 AND id = TRIM(id)",
            name="ck_tool_capabilities_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(remote_name) BETWEEN 1 AND 128 AND remote_name = TRIM(remote_name)",
            name="ck_tool_capabilities_remote_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(display_name) BETWEEN 1 AND 128 "
            "AND display_name = TRIM(display_name)",
            name="ck_tool_capabilities_display_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(description) <= 1000 AND description = TRIM(description)",
            name="ck_tool_capabilities_description",
        ),
        sa.CheckConstraint(
            "JSON_TYPE(input_schema) = 'OBJECT'",
            name="ck_tool_capabilities_schema",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(schema_fingerprint) = 64 AND "
            "schema_fingerprint REGEXP '^[0-9a-f]{64}$'",
            name="ck_tool_capabilities_fingerprint",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'unavailable', 'disabled')",
            name="ck_tool_capabilities_status",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_tool_capabilities_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tool_capabilities_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["mcp_sources.tenant_id", "mcp_sources.id"],
            name="fk_tool_capabilities_source",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tool_capabilities_tenant_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "source_id",
            "remote_name",
            name="uq_tool_capabilities_tenant_source_remote",
        ),
    )
    op.create_index(
        "ix_tool_capabilities_tenant_created",
        "tool_capabilities",
        ["tenant_id", "created_at", "id"],
    )
    op.create_index(
        "ix_tool_capabilities_tenant_source_status",
        "tool_capabilities",
        ["tenant_id", "source_id", "status"],
    )

    op.create_table(
        "tool_collections",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.String(length=1000), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(id) = 36 AND id = TRIM(id)",
            name="ck_tool_collections_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 128 AND name = TRIM(name)",
            name="ck_tool_collections_name",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(description) <= 1000 AND description = TRIM(description)",
            name="ck_tool_collections_description",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_tool_collections_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tool_collections_tenant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_tool_collections_tenant_id"),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tool_collections_tenant_name"),
    )
    op.create_index(
        "ix_tool_collections_tenant_created",
        "tool_collections",
        ["tenant_id", "created_at", "id"],
    )

    op.create_table(
        "tool_collection_sources",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tool_collection_sources_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "collection_id"],
            ["tool_collections.tenant_id", "tool_collections.id"],
            name="fk_tool_collection_sources_collection",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["mcp_sources.tenant_id", "mcp_sources.id"],
            name="fk_tool_collection_sources_source",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "collection_id", "source_id"),
    )
    op.create_index(
        "ix_tool_collection_sources_source",
        "tool_collection_sources",
        ["tenant_id", "source_id"],
    )

    _create_target_tables(
        target="employee",
        target_table="employees",
        target_column="employee_id",
    )
    _create_target_tables(
        target="conversation",
        target_table="conversations",
        target_column="conversation_id",
    )


def _create_target_tables(*, target: str, target_table: str, target_column: str) -> None:
    selection_table = f"{target}_tool_collection_selections"
    grant_table = f"{target}_tool_grants"
    op.create_table(
        selection_table,
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column(target_column, sa.String(length=36), nullable=False),
        sa.Column("collection_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=f"fk_{selection_table}_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", target_column],
            [f"{target_table}.tenant_id", f"{target_table}.id"],
            name=f"fk_{selection_table}_{target}",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "collection_id"],
            ["tool_collections.tenant_id", "tool_collections.id"],
            name=f"fk_{selection_table}_collection",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", target_column, "collection_id"),
    )
    op.create_index(
        f"ix_{selection_table}_collection",
        selection_table,
        ["tenant_id", "collection_id"],
    )

    op.create_table(
        grant_table,
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column(target_column, sa.String(length=36), nullable=False),
        sa.Column("capability_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name=f"fk_{grant_table}_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", target_column],
            [f"{target_table}.tenant_id", f"{target_table}.id"],
            name=f"fk_{grant_table}_{target}",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "capability_id"],
            ["tool_capabilities.tenant_id", "tool_capabilities.id"],
            name=f"fk_{grant_table}_capability",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("tenant_id", target_column, "capability_id"),
    )
    op.create_index(
        f"ix_{grant_table}_capability",
        grant_table,
        ["tenant_id", "capability_id"],
    )


def downgrade() -> None:
    for table in (
        "conversation_tool_grants",
        "conversation_tool_collection_selections",
        "employee_tool_grants",
        "employee_tool_collection_selections",
        "tool_collection_sources",
        "tool_capabilities",
        "tool_collections",
        "mcp_sources",
    ):
        op.drop_table(table)
