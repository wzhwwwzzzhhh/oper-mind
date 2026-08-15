"""P8 用量与成本统计：model_usage_records 用量记录表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260813_13_p8_model_usage"
down_revision = "20260812_12_p8_run_rerun"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建模型用量记录表；只存聚合计数，不含调用内容与凭据。"""
    op.create_table(
        "model_usage_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model", sa.String(length=120), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        # 预留下钻字段：首版不写入（NULL），后续按会话/Run 明细时再接线。
        sa.Column("run_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("input_tokens >= 0", name="model_usage_input_tokens_nonnegative"),
        sa.CheckConstraint("output_tokens >= 0", name="model_usage_output_tokens_nonnegative"),
        sa.CheckConstraint("total_tokens >= 0", name="model_usage_total_tokens_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_model_usage_records"),
    )
    op.create_index("ix_model_usage_model_created_at", "model_usage_records", ["model", "created_at"])
    op.create_index("ix_model_usage_created_at", "model_usage_records", ["created_at"])


def downgrade() -> None:
    """删除模型用量记录表。"""
    op.drop_index("ix_model_usage_created_at", table_name="model_usage_records")
    op.drop_index("ix_model_usage_model_created_at", table_name="model_usage_records")
    op.drop_table("model_usage_records")
