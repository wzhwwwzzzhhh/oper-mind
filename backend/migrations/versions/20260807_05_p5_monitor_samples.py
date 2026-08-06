"""P5 服务历史监控样本表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260807_05_p5_monitor_samples"
down_revision = "20260802_04_p2_tool_invoked"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建只保存脱敏标量的历史样本表。"""
    op.create_table(
        "service_monitor_samples",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("availability", sa.String(length=24), nullable=False),
        sa.Column("p50_ms", sa.Float(), nullable=True),
        sa.Column("p95_ms", sa.Float(), nullable=True),
        sa.Column("slow_query_count", sa.Integer(), nullable=True),
        sa.Column("timeout_count", sa.Integer(), nullable=True),
        sa.Column("performance_signal", sa.String(length=40), nullable=False),
        sa.Column("source_status", sa.String(length=24), nullable=False),
        sa.CheckConstraint(
            "availability IN ('healthy', 'unhealthy', 'unavailable', 'not_configured')",
            name="monitor_sample_availability_valid",
        ),
        sa.CheckConstraint(
            "performance_signal IN ('slow_query_detected', 'no_slow_query_detected', 'insufficient_data', 'unavailable', 'not_configured')",
            name="monitor_sample_performance_signal_valid",
        ),
        sa.CheckConstraint(
            "source_status IN ('available', 'unavailable', 'not_configured')",
            name="monitor_sample_source_status_valid",
        ),
        sa.CheckConstraint("p50_ms IS NULL OR p50_ms >= 0", name="monitor_sample_p50_nonnegative"),
        sa.CheckConstraint("p95_ms IS NULL OR p95_ms >= 0", name="monitor_sample_p95_nonnegative"),
        sa.CheckConstraint("slow_query_count IS NULL OR slow_query_count >= 0", name="monitor_sample_slow_count_nonnegative"),
        sa.CheckConstraint("timeout_count IS NULL OR timeout_count >= 0", name="monitor_sample_timeout_count_nonnegative"),
        sa.PrimaryKeyConstraint("id", name="pk_service_monitor_samples"),
    )
    op.create_index(
        "ix_service_monitor_samples_service_observed_at",
        "service_monitor_samples",
        ["service_id", "observed_at"],
    )
    op.create_index("ix_service_monitor_samples_observed_at", "service_monitor_samples", ["observed_at"])


def downgrade() -> None:
    """删除 P5 历史样本表。"""
    op.drop_index("ix_service_monitor_samples_observed_at", table_name="service_monitor_samples")
    op.drop_index("ix_service_monitor_samples_service_observed_at", table_name="service_monitor_samples")
    op.drop_table("service_monitor_samples")
