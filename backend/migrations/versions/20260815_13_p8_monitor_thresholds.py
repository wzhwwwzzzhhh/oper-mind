"""P8 按服务的监控阈值配置表。"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "20260815_13_p8_monitor_thresholds"
down_revision = "20260812_12_p8_run_rerun"
branch_labels = None
depends_on = None


def _raise_if_threshold_rows(bind) -> None:
    """downgrade 前置检查：存在阈值配置行时拒绝回滚，避免静默丢弃用户配置。"""
    if bind.dialect.name == "sqlite":
        value = bind.exec_driver_sql(
            "SELECT COUNT(*) FROM service_monitor_thresholds"
        ).scalar()
    else:
        value = bind.execute(
            sa.text("SELECT COUNT(*) FROM service_monitor_thresholds")
        ).scalar()
    if value and int(value) > 0:
        raise RuntimeError("存在监控阈值配置行，拒绝回滚以保留用户配置。")


def upgrade() -> None:
    """创建只保存白名单标量配置的单行表；未配置不产生记录。"""
    op.create_table(
        "service_monitor_thresholds",
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("slow_query_count_threshold", sa.Integer(), nullable=True),
        sa.Column("timeout_count_threshold", sa.Integer(), nullable=True),
        sa.Column("slowlog_count_threshold", sa.Integer(), nullable=True),
        sa.Column("window_minutes", sa.Integer(), nullable=False),
        sa.Column("count_availability_change", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "slow_query_count_threshold IS NULL OR slow_query_count_threshold >= 0",
            name="monitor_threshold_slow_query_nonnegative",
        ),
        sa.CheckConstraint(
            "timeout_count_threshold IS NULL OR timeout_count_threshold >= 0",
            name="monitor_threshold_timeout_nonnegative",
        ),
        sa.CheckConstraint(
            "slowlog_count_threshold IS NULL OR slowlog_count_threshold >= 0",
            name="monitor_threshold_slowlog_nonnegative",
        ),
        sa.CheckConstraint(
            "window_minutes >= 0 AND window_minutes <= 1440",
            name="monitor_threshold_window_range",
        ),
        sa.PrimaryKeyConstraint("service_id", name="pk_service_monitor_thresholds"),
    )


def downgrade() -> None:
    """删除阈值配置表；存在配置行时拒绝回滚。"""
    connection = op.get_bind()
    _raise_if_threshold_rows(connection)
    op.drop_table("service_monitor_thresholds")
