"""增加平台工作区到 RAGFlow 技术租户的一对一身份表。

Revision ID: 20260723_0027
Revises: 20260723_0026
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260723_0027"
down_revision: str | None = "20260723_0026"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ragflow_tenant_identities",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("account_email", sa.String(length=254), nullable=False),
        sa.Column("ragflow_tenant_id", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("format_version", sa.SmallInteger(), nullable=True),
        sa.Column("encryption_key_id", sa.String(length=64), nullable=False),
        sa.Column("nonce", sa.LargeBinary(length=12), nullable=True),
        sa.Column("ciphertext", sa.LargeBinary(length=512), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(account_email) BETWEEN 3 AND 254 "
            "AND account_email = LOWER(TRIM(account_email))",
            name="ck_ragflow_tenant_identities_email",
        ),
        sa.CheckConstraint(
            "status IN ('provisioning', 'active')",
            name="ck_ragflow_tenant_identities_status",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(encryption_key_id) BETWEEN 1 AND 64 "
            "AND encryption_key_id = TRIM(encryption_key_id)",
            name="ck_ragflow_tenant_identities_key_id",
        ),
        sa.CheckConstraint(
            "(status = 'provisioning' AND ragflow_tenant_id IS NULL "
            "AND format_version IS NULL AND nonce IS NULL AND ciphertext IS NULL) OR "
            "(status = 'active' AND ragflow_tenant_id IS NOT NULL "
            "AND format_version = 1 AND OCTET_LENGTH(nonce) = 12 "
            "AND OCTET_LENGTH(ciphertext) >= 17)",
            name="ck_ragflow_tenant_identities_state",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_ragflow_tenant_identities_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_ragflow_tenant_identities_tenant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            name="pk_ragflow_tenant_identities",
        ),
        sa.UniqueConstraint(
            "account_email",
            name="uq_ragflow_tenant_identities_email",
        ),
        sa.UniqueConstraint(
            "ragflow_tenant_id",
            name="uq_ragflow_tenant_identities_external_tenant",
        ),
    )


def downgrade() -> None:
    op.drop_table("ragflow_tenant_identities")
