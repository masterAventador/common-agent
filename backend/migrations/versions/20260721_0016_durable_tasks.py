"""增加持久任务队列与租约状态。

Revision ID: 20260721_0016
Revises: 20260721_0015
Create Date: 2026-07-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260721_0016"
down_revision: str | None = "20260721_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "durable_tasks",
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("idempotency_key", sa.String(length=191), nullable=False),
        sa.Column("aggregate_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("available_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("lease_owner", sa.String(length=128), nullable=True),
        sa.Column("lease_token", sa.String(length=36), nullable=True),
        sa.Column("lease_until", mysql.DATETIME(fsp=6), nullable=True),
        sa.Column("stop_requested", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(length=128), nullable=True),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("CHAR_LENGTH(task_id) = 36", name="ck_durable_tasks_task_id"),
        sa.CheckConstraint(
            "kind IN ('conversation.reply', 'workflow.run')",
            name="ck_durable_tasks_kind",
        ),
        sa.CheckConstraint(
            "state IN ('pending', 'running', 'retry_wait', 'succeeded', 'failed', 'cancelled')",
            name="ck_durable_tasks_state",
        ),
        sa.CheckConstraint(
            "attempts >= 0 AND max_attempts BETWEEN 1 AND 100 AND attempts <= max_attempts",
            name="ck_durable_tasks_attempts",
        ),
        sa.CheckConstraint(
            "(state = 'running' AND lease_owner IS NOT NULL AND lease_token IS NOT NULL "
            "AND lease_until IS NOT NULL) OR (state <> 'running' AND lease_owner IS NULL "
            "AND lease_token IS NULL AND lease_until IS NULL)",
            name="ck_durable_tasks_lease",
        ),
        sa.CheckConstraint(
            "(state IN ('failed', 'retry_wait') AND error_code IS NOT NULL) OR "
            "(state NOT IN ('failed', 'retry_wait') AND error_code IS NULL)",
            name="ck_durable_tasks_error",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_durable_tasks_tenant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("task_id"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_durable_tasks_tenant_key"),
    )
    op.create_index(
        "ix_durable_tasks_claim",
        "durable_tasks",
        ["state", "available_at", "lease_until", "created_at"],
    )
    op.create_index(
        "ix_durable_tasks_tenant_aggregate",
        "durable_tasks",
        ["tenant_id", "kind", "aggregate_id"],
    )
    op.create_index("ix_durable_tasks_updated", "durable_tasks", ["updated_at"])

    op.create_table(
        "durable_event_streams",
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("stream_kind", sa.String(length=16), nullable=False),
        sa.Column("stream_id", sa.String(length=36), nullable=False),
        sa.Column("next_sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("created_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "stream_kind IN ('conversation', 'workflow')",
            name="ck_durable_event_streams_kind",
        ),
        sa.CheckConstraint(
            "next_sequence >= 1 AND event_count >= 0",
            name="ck_durable_event_streams_counters",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["tenants.id"],
            name="fk_durable_event_streams_tenant_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "stream_kind", "stream_id"),
    )
    op.create_index(
        "ix_durable_event_streams_updated",
        "durable_event_streams",
        ["updated_at"],
    )

    op.create_table(
        "durable_events",
        sa.Column("event_id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=36), nullable=False),
        sa.Column("stream_kind", sa.String(length=16), nullable=False),
        sa.Column("stream_id", sa.String(length=36), nullable=False),
        sa.Column("sequence", sa.BigInteger(), nullable=False),
        sa.Column("event_key", sa.String(length=191), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("occurred_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("retention_until", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="ck_durable_events_sequence"),
        sa.CheckConstraint(
            "stream_kind IN ('conversation', 'workflow')",
            name="ck_durable_events_kind",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "stream_kind", "stream_id"],
            [
                "durable_event_streams.tenant_id",
                "durable_event_streams.stream_kind",
                "durable_event_streams.stream_id",
            ],
            name="fk_durable_events_stream",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "tenant_id",
            "stream_kind",
            "stream_id",
            "sequence",
            name="uq_durable_events_stream_sequence",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "stream_kind",
            "stream_id",
            "event_key",
            name="uq_durable_events_stream_key",
        ),
    )
    op.create_index(
        "ix_durable_events_stream_read",
        "durable_events",
        ["tenant_id", "stream_kind", "stream_id", "sequence"],
    )
    op.create_index(
        "ix_durable_events_retention",
        "durable_events",
        ["retention_until"],
    )


def downgrade() -> None:
    op.drop_index("ix_durable_events_retention", table_name="durable_events")
    op.drop_index("ix_durable_events_stream_read", table_name="durable_events")
    op.drop_table("durable_events")
    op.drop_index(
        "ix_durable_event_streams_updated",
        table_name="durable_event_streams",
    )
    op.drop_table("durable_event_streams")
    op.drop_index("ix_durable_tasks_updated", table_name="durable_tasks")
    op.drop_index("ix_durable_tasks_tenant_aggregate", table_name="durable_tasks")
    op.drop_index("ix_durable_tasks_claim", table_name="durable_tasks")
    op.drop_table("durable_tasks")
