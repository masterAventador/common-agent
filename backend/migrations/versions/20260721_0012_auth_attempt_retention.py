"""为登录失败状态增加过期清理索引。

Revision ID: 20260721_0012
Revises: 20260721_0011
Create Date: 2026-07-21
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260721_0012"
down_revision: str | None = "20260721_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "ix_auth_login_attempts_updated_at",
        "auth_login_attempts",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_auth_login_attempts_updated_at", table_name="auth_login_attempts")
