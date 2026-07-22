"""增加平台维护的模型工具调用流式兼容表。

Revision ID: 20260723_0026
Revises: 20260722_0025
Create Date: 2026-07-23
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260723_0026"
down_revision: str | None = "20260722_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "model_tool_streaming_capabilities",
        sa.Column("provider", sa.String(length=16), nullable=False),
        sa.Column("model_identifier", sa.String(length=128), nullable=False),
        sa.Column("streaming_breaks_tool_calls", sa.Boolean(), nullable=False),
        sa.Column("evidence_revision", sa.String(length=128), nullable=False),
        sa.Column("observed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "provider = 'bailian'",
            name="ck_model_tool_streaming_capabilities_provider",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(model_identifier) BETWEEN 1 AND 128 "
            "AND model_identifier = TRIM(model_identifier)",
            name="ck_model_tool_streaming_capabilities_identifier",
        ),
        sa.CheckConstraint(
            "CHAR_LENGTH(evidence_revision) BETWEEN 1 AND 128 "
            "AND evidence_revision = TRIM(evidence_revision)",
            name="ck_model_tool_streaming_capabilities_evidence_revision",
        ),
        sa.CheckConstraint(
            "updated_at >= observed_at",
            name="ck_model_tool_streaming_capabilities_timestamps",
        ),
        sa.PrimaryKeyConstraint(
            "provider",
            "model_identifier",
            name="pk_model_tool_streaming_capabilities",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO model_tool_streaming_capabilities "
            "(provider, model_identifier, streaming_breaks_tool_calls, "
            "evidence_revision, observed_at, updated_at) "
            "VALUES ('bailian', :model_identifier, TRUE, :evidence_revision, "
            "UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
        ).bindparams(
            model_identifier="deepseek-v4-pro",
            evidence_revision="bailian-real-trace-2026-07-23",
        )
    )


def downgrade() -> None:
    op.drop_table("model_tool_streaming_capabilities")
