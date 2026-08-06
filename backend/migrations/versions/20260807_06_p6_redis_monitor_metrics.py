"""P6 Redis 历史监控专用标量字段。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260807_06_p6_redis_monitor_metrics"
down_revision = "20260807_05_p5_monitor_samples"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为 service_monitor_samples 增加 Redis 专用可空标量列。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("service_monitor_samples") as batch_op:
            batch_op.add_column(sa.Column("memory_bytes", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("client_connections", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("slowlog_count", sa.Integer(), nullable=True))
            batch_op.create_check_constraint(
                "monitor_sample_memory_bytes_nonnegative",
                "memory_bytes IS NULL OR memory_bytes >= 0",
            )
            batch_op.create_check_constraint(
                "monitor_sample_client_connections_nonnegative",
                "client_connections IS NULL OR client_connections >= 0",
            )
            batch_op.create_check_constraint(
                "monitor_sample_slowlog_count_nonnegative",
                "slowlog_count IS NULL OR slowlog_count >= 0",
            )
    finally:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    """移除 Redis 专用可空标量列。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("service_monitor_samples") as batch_op:
            batch_op.drop_constraint("monitor_sample_memory_bytes_nonnegative", type_="check")
            batch_op.drop_constraint("monitor_sample_client_connections_nonnegative", type_="check")
            batch_op.drop_constraint("monitor_sample_slowlog_count_nonnegative", type_="check")
            batch_op.drop_column("memory_bytes")
            batch_op.drop_column("client_connections")
            batch_op.drop_column("slowlog_count")
    finally:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
