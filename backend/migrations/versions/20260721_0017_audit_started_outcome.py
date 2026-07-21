"""Allow durable audit intents before mutation execution.

Revision ID: 20260721_0017
Revises: 20260721_0016
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260721_0017"
down_revision: str | None = "20260721_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_audit_events_error", "audit_events", type_="check")
    op.drop_constraint("ck_audit_events_outcome", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_outcome",
        "audit_events",
        "outcome IN ('started', 'succeeded', 'denied', 'failed')",
    )
    op.create_check_constraint(
        "ck_audit_events_error",
        "audit_events",
        "(outcome IN ('started', 'succeeded') AND error_code IS NULL) OR "
        "(outcome IN ('denied', 'failed') AND error_code IS NOT NULL)",
    )


def downgrade() -> None:
    connection = op.get_bind()
    started_count = connection.scalar(
        sa.text("SELECT COUNT(*) FROM audit_events WHERE outcome = 'started'")
    )
    if int(started_count or 0) > 0:
        raise RuntimeError("cannot downgrade while durable started audit intents are present")
    op.drop_constraint("ck_audit_events_error", "audit_events", type_="check")
    op.drop_constraint("ck_audit_events_outcome", "audit_events", type_="check")
    op.create_check_constraint(
        "ck_audit_events_outcome",
        "audit_events",
        "outcome IN ('succeeded', 'denied', 'failed')",
    )
    op.create_check_constraint(
        "ck_audit_events_error",
        "audit_events",
        "(outcome = 'succeeded' AND error_code IS NULL) OR "
        "(outcome IN ('denied', 'failed') AND error_code IS NOT NULL)",
    )
