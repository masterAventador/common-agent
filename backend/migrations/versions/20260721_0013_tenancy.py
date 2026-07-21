"""增加组织、租户和成员角色并回填历史 Owner。

Revision ID: 20260721_0013
Revises: 20260721_0012
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260721_0013"
down_revision: str | None = "20260721_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DEFAULT_ORGANIZATION_ID = "00000000-0000-4000-8000-000000000001"
DEFAULT_TENANT_ID = "00000000-0000-4000-8000-000000000002"


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_organizations_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 100 AND name = TRIM(name)",
            name="ck_organizations_name",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "tenants",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("organization_id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_tenants_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(name) BETWEEN 1 AND 100 AND name = TRIM(name)",
            name="ck_tenants_name",
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organizations.id"],
            name="fk_tenants_organization_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("organization_id", "name", name="uq_tenants_organization_name"),
    )
    op.execute(
        sa.text(
            "INSERT INTO organizations (id, name, created_at) "
            "VALUES (:id, '默认组织', UTC_TIMESTAMP(6))"
        ).bindparams(id=DEFAULT_ORGANIZATION_ID)
    )
    op.execute(
        sa.text(
            "INSERT INTO tenants (id, organization_id, name, created_at) "
            "VALUES (:id, :organization_id, '默认工作区', UTC_TIMESTAMP(6))"
        ).bindparams(id=DEFAULT_TENANT_ID, organization_id=DEFAULT_ORGANIZATION_ID)
    )
    op.create_table(
        "tenant_memberships",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "role IN ('owner', 'editor', 'viewer')",
            name="ck_tenant_memberships_role",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_tenant_memberships_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name="fk_tenant_memberships_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "user_id"),
    )
    op.create_index(
        "ix_tenant_memberships_user",
        "tenant_memberships",
        ["user_id", "tenant_id"],
    )
    op.execute(
        sa.text(
            "INSERT INTO tenant_memberships (tenant_id, user_id, role, created_at) "
            "SELECT :tenant_id, id, 'owner', created_at FROM auth_users "
            "WHERE bootstrap_slot = 'owner'"
        ).bindparams(tenant_id=DEFAULT_TENANT_ID)
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_memberships_user", table_name="tenant_memberships")
    op.drop_table("tenant_memberships")
    op.drop_table("tenants")
    op.drop_table("organizations")
