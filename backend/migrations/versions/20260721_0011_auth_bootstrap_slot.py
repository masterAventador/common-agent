"""为首个 Owner 注册增加并发唯一槽位。

Revision ID: 20260721_0011
Revises: 20260721_0010
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0011"
down_revision: str | None = "20260721_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "auth_users",
        sa.Column("bootstrap_slot", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_auth_users_bootstrap_slot",
        "auth_users",
        "bootstrap_slot IS NULL OR bootstrap_slot = 'owner'",
    )
    op.create_unique_constraint(
        "uq_auth_users_bootstrap_slot",
        "auth_users",
        ["bootstrap_slot"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_auth_users_bootstrap_slot", "auth_users", type_="unique")
    op.drop_constraint("ck_auth_users_bootstrap_slot", "auth_users", type_="check")
    op.drop_column("auth_users", "bootstrap_slot")
