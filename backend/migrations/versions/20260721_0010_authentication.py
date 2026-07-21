"""增加用户、安全会话、恢复码和登录失败状态。

Revision ID: 20260721_0010
Revises: 20260721_0009
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260721_0010"
down_revision: str | None = "20260721_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "auth_users",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("password_changed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_auth_users_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(email) BETWEEN 3 AND 254 AND email = LOWER(TRIM(email))",
            name="ck_auth_users_email",
        ),
        sa.CheckConstraint(
            "password_hash LIKE '$argon2id$%'",
            name="ck_auth_users_password_hash",
        ),
        sa.CheckConstraint(
            "password_changed_at BETWEEN created_at AND updated_at",
            name="ck_auth_users_password_changed_at",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_auth_users_email"),
    )
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("csrf_token", sa.String(length=43), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("last_seen_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("idle_expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("absolute_expires_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("revoked_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint("CHAR_LENGTH(id) = 36 AND id = TRIM(id)", name="ck_auth_sessions_id"),
        sa.CheckConstraint(
            "CHAR_LENGTH(user_id) = 36 AND user_id = TRIM(user_id)",
            name="ck_auth_sessions_user_id",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(token_digest) = 64",
            name="ck_auth_sessions_token_digest",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(csrf_token) = 43",
            name="ck_auth_sessions_csrf_token",
        ),
        sa.CheckConstraint(
            "last_seen_at >= created_at AND idle_expires_at > last_seen_at "
            "AND absolute_expires_at >= idle_expires_at",
            name="ck_auth_sessions_lifetime",
        ),
        sa.CheckConstraint(
            "revoked_at IS NULL OR revoked_at >= created_at",
            name="ck_auth_sessions_revoked_at",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name="fk_auth_sessions_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_auth_sessions_token_digest"),
    )
    op.create_index(
        "ix_auth_sessions_user_active",
        "auth_sessions",
        ["user_id", "revoked_at", "absolute_expires_at"],
    )
    op.create_table(
        "auth_recovery_codes",
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("code_digest", sa.String(length=64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("consumed_at", mysql.DATETIME(fsp=6), nullable=True),
        sa.CheckConstraint(
            "CHAR_LENGTH(code_digest) = 64",
            name="ck_auth_recovery_codes_digest",
        ),
        sa.CheckConstraint(
            "consumed_at IS NULL OR consumed_at >= created_at",
            name="ck_auth_recovery_codes_consumed_at",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["auth_users.id"],
            name="fk_auth_recovery_codes_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id", "code_digest"),
    )
    op.create_table(
        "auth_login_attempts",
        sa.Column("key_digest", sa.String(length=64), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False),
        sa.Column("window_started_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("locked_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "CHAR_LENGTH(key_digest) = 64",
            name="ck_auth_login_attempts_key_digest",
        ),
        sa.CheckConstraint(
            "failure_count >= 0 AND updated_at >= window_started_at",
            name="ck_auth_login_attempts_state",
        ),
        sa.CheckConstraint(
            "locked_until IS NULL OR locked_until >= updated_at",
            name="ck_auth_login_attempts_locked_until",
        ),
        sa.PrimaryKeyConstraint("key_digest"),
    )
    op.create_index(
        "ix_auth_login_attempts_locked_until",
        "auth_login_attempts",
        ["locked_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_login_attempts_locked_until", table_name="auth_login_attempts")
    op.drop_table("auth_login_attempts")
    op.drop_table("auth_recovery_codes")
    op.drop_index("ix_auth_sessions_user_active", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_table("auth_users")
