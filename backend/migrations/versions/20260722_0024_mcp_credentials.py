"""增加租户绑定的 MCP 凭据密文表。

Revision ID: 20260722_0024
Revises: 20260722_0023
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260722_0024"
down_revision: str | None = "20260722_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_source_credentials",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("credential_type", sa.String(length=24), nullable=False),
        sa.Column("format_version", sa.SmallInteger(), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("nonce", mysql.TINYBLOB(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(length=65535), nullable=False),
        sa.Column("header_names", sa.JSON(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "credential_type IN ('bearer', 'custom_headers')",
            name="ck_mcp_source_credentials_type",
        ),
        sa.CheckConstraint(
            "format_version = 1",
            name="ck_mcp_source_credentials_format",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(key_id) BETWEEN 1 AND 64 AND key_id = TRIM(key_id)",
            name="ck_mcp_source_credentials_key_id",
        ),
        sa.CheckConstraint(
            "OCTET_LENGTH(nonce) = 12",
            name="ck_mcp_source_credentials_nonce",
        ),
        sa.CheckConstraint(
            "OCTET_LENGTH(ciphertext) BETWEEN 16 AND 65535",
            name="ck_mcp_source_credentials_ciphertext",
        ),
        sa.CheckConstraint(
            "JSON_TYPE(header_names) = 'ARRAY' AND JSON_LENGTH(header_names) <= 16",
            name="ck_mcp_source_credentials_header_names",
        ),
        sa.CheckConstraint(
            "(credential_type = 'bearer' AND JSON_LENGTH(header_names) = 0) OR "
            "(credential_type = 'custom_headers' AND JSON_LENGTH(header_names) BETWEEN 1 AND 16)",
            name="ck_mcp_source_credentials_shape",
        ),
        sa.CheckConstraint(
            "updated_at >= created_at",
            name="ck_mcp_source_credentials_timestamps",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_mcp_source_credentials_tenant_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "source_id"],
            ["mcp_sources.tenant_id", "mcp_sources.id"],
            name="fk_mcp_source_credentials_source",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "source_id"),
    )
    op.create_index(
        "ix_mcp_source_credentials_key_id",
        "mcp_source_credentials",
        ["key_id", "tenant_id"],
    )


def downgrade() -> None:
    op.drop_table("mcp_source_credentials")
