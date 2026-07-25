"""数字员工增加是否开启深度思考的开关。

Revision ID: 20260726_0028
Revises: 20260723_0027
Create Date: 2026-07-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import mysql

revision: str = "20260726_0028"
down_revision: str | None = "20260723_0027"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 既有员工按开启补齐: 开关加入之前, 会思考的模型本来就在思考, 默认关掉会改变现状
    op.add_column(
        "employees",
        sa.Column(
            "deep_thinking_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.alter_column(
        "employees",
        "deep_thinking_enabled",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None,
    )


    # 部分模型不接受关闭深度思考。实测: MiniMax-M2.5 传 enable_thinking=false 直接 400,
    # 报 "The value of the enable_thinking parameter is restricted to True"。这类模型
    # 记录在案, 用户把开关关掉时不下发该参数, 免得一关就无法对话。表里没有记录即视为可关闭。
    op.create_table(
        "model_thinking_capabilities",
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("model_identifier", sa.String(128), nullable=False),
        sa.Column("thinking_can_be_disabled", sa.Boolean(), nullable=False),
        sa.Column("evidence_revision", sa.String(128), nullable=False),
        sa.Column("observed_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.Column("updated_at", mysql.DATETIME(fsp=6), nullable=False),
        sa.CheckConstraint(
            "provider = TRIM(provider) AND CHAR_LENGTH(provider) BETWEEN 1 AND 16",
            name="ck_model_thinking_capabilities_provider",
        ),
        sa.CheckConstraint(
            "model_identifier = TRIM(model_identifier) "
            "AND CHAR_LENGTH(model_identifier) BETWEEN 1 AND 128",
            name="ck_model_thinking_capabilities_identifier",
        ),
        sa.CheckConstraint(
            "evidence_revision = TRIM(evidence_revision) "
            "AND CHAR_LENGTH(evidence_revision) BETWEEN 1 AND 128",
            name="ck_model_thinking_capabilities_evidence_revision",
        ),
        sa.CheckConstraint(
            "updated_at >= observed_at",
            name="ck_model_thinking_capabilities_timestamps",
        ),
        sa.PrimaryKeyConstraint(
            "provider", "model_identifier", name="pk_model_thinking_capabilities"
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO model_thinking_capabilities "
            "(provider, model_identifier, thinking_can_be_disabled, "
            "evidence_revision, observed_at, updated_at) "
            "VALUES ('bailian', :model_identifier, FALSE, :evidence_revision, "
            "UTC_TIMESTAMP(6), UTC_TIMESTAMP(6))"
        ).bindparams(
            model_identifier="MiniMax-M2.5",
            evidence_revision="bailian-real-trace-2026-07-26",
        )
    )


def downgrade() -> None:
    op.drop_table("model_thinking_capabilities")
    op.drop_column("employees", "deep_thinking_enabled")
