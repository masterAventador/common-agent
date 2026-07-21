"""增加只追加、可验证的审计与安全事件。

Revision ID: 20260721_0015
Revises: 20260721_0014
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260721_0015"
down_revision: str | None = "20260721_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "audit_chain_heads",
        sa.Column("scope_key", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("event_count", sa.BigInteger(), nullable=False),
        sa.Column("last_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "(scope_key = 'platform' AND tenant_id IS NULL) OR "
            "(scope_key = CONCAT('tenant:', tenant_id) AND tenant_id IS NOT NULL)",
            name="ck_audit_chain_heads_scope",
        ),
        sa.CheckConstraint("event_count >= 0", name="ck_audit_chain_heads_count"),
        sa.CheckConstraint(
            "CHAR_LENGTH(last_hash) = 64",
            name="ck_audit_chain_heads_last_hash",
        ),
        sa.PrimaryKeyConstraint("scope_key"),
        sa.UniqueConstraint("tenant_id", name="uq_audit_chain_heads_tenant_id"),
    )
    op.create_table(
        "audit_events",
        sa.Column("storage_id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("scope_key", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("outcome", sa.String(length=16), nullable=False),
        sa.Column("request_id", sa.String(length=36), nullable=False),
        sa.Column("trace_id", sa.String(length=32), nullable=False),
        sa.Column("resource_type", sa.String(length=32), nullable=True),
        sa.Column("resource_id", sa.String(length=128), nullable=True),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("retention_until", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("previous_hash", sa.String(length=64), nullable=False),
        sa.Column("event_hash", sa.String(length=64), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(event_id) = 36", name="ck_audit_events_event_id"),
        sa.CheckConstraint("sequence > 0", name="ck_audit_events_sequence"),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'denied', 'failed')",
            name="ck_audit_events_outcome",
        ),
        sa.CheckConstraint(
            "(resource_type IS NULL AND resource_id IS NULL) OR "
            "(resource_type IS NOT NULL AND resource_id IS NOT NULL)",
            name="ck_audit_events_resource",
        ),
        sa.CheckConstraint(
            "(outcome = 'succeeded' AND error_code IS NULL) OR "
            "(outcome IN ('denied', 'failed') AND error_code IS NOT NULL)",
            name="ck_audit_events_error",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(trace_id) = 32 AND CHAR_LENGTH(previous_hash) = 64 "
            "AND CHAR_LENGTH(event_hash) = 64",
            name="ck_audit_events_hashes",
        ),
        sa.CheckConstraint(
            "retention_until > occurred_at",
            name="ck_audit_events_retention",
        ),
        sa.ForeignKeyConstraint(
            ["scope_key"],
            ["audit_chain_heads.scope_key"],
            name="fk_audit_events_scope_key",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("storage_id"),
        sa.UniqueConstraint("event_id", name="uq_audit_events_event_id"),
        sa.UniqueConstraint("scope_key", "sequence", name="uq_audit_events_scope_sequence"),
    )
    op.create_index(
        "ix_audit_events_tenant_occurred",
        "audit_events",
        ["tenant_id", "occurred_at", "sequence"],
    )
    op.create_index(
        "ix_audit_events_tenant_actor_occurred",
        "audit_events",
        ["tenant_id", "actor_user_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_tenant_resource_occurred",
        "audit_events",
        ["tenant_id", "resource_type", "resource_id", "occurred_at"],
    )
    op.create_index(
        "ix_audit_events_retention_until",
        "audit_events",
        ["retention_until"],
    )
    op.execute(
        "CREATE TRIGGER trg_audit_events_no_update BEFORE UPDATE ON audit_events "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' "
        "SET MESSAGE_TEXT = 'audit_events are append-only'"
    )
    op.execute(
        "CREATE TRIGGER trg_audit_events_no_delete BEFORE DELETE ON audit_events "
        "FOR EACH ROW SIGNAL SQLSTATE '45000' "
        "SET MESSAGE_TEXT = 'audit_events are append-only'"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_delete")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_events_no_update")
    op.drop_index("ix_audit_events_retention_until", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_resource_occurred", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_actor_occurred", table_name="audit_events")
    op.drop_index("ix_audit_events_tenant_occurred", table_name="audit_events")
    op.drop_table("audit_events")
    op.drop_table("audit_chain_heads")
