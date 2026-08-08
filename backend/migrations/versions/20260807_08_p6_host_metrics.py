"""P6 主机指标历史监控标量字段。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260807_08_p6_host_metrics"
down_revision = "20260807_07_p6_model_provider"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为 service_monitor_samples 增加主机指标可空标量列（CPU/内存/磁盘）。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("service_monitor_samples") as batch_op:
            batch_op.add_column(sa.Column("host_cpu_percent", sa.Float(), nullable=True))
            batch_op.add_column(sa.Column("host_memory_percent", sa.Float(), nullable=True))
            batch_op.add_column(sa.Column("host_memory_bytes", sa.Integer(), nullable=True))
            batch_op.add_column(sa.Column("host_disk_used_percent", sa.Float(), nullable=True))
            batch_op.create_check_constraint(
                "monitor_sample_host_cpu_nonnegative",
                "host_cpu_percent IS NULL OR host_cpu_percent >= 0",
            )
            batch_op.create_check_constraint(
                "monitor_sample_host_memory_percent_nonnegative",
                "host_memory_percent IS NULL OR host_memory_percent >= 0",
            )
            batch_op.create_check_constraint(
                "monitor_sample_host_memory_bytes_nonnegative",
                "host_memory_bytes IS NULL OR host_memory_bytes >= 0",
            )
            batch_op.create_check_constraint(
                "monitor_sample_host_disk_nonnegative",
                "host_disk_used_percent IS NULL OR host_disk_used_percent >= 0",
            )
    finally:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")


def downgrade() -> None:
    """移除主机指标可空标量列。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("service_monitor_samples") as batch_op:
            batch_op.drop_constraint("monitor_sample_host_cpu_nonnegative", type_="check")
            batch_op.drop_constraint("monitor_sample_host_memory_percent_nonnegative", type_="check")
            batch_op.drop_constraint("monitor_sample_host_memory_bytes_nonnegative", type_="check")
            batch_op.drop_constraint("monitor_sample_host_disk_nonnegative", type_="check")
            batch_op.drop_column("host_cpu_percent")
            batch_op.drop_column("host_memory_percent")
            batch_op.drop_column("host_memory_bytes")
            batch_op.drop_column("host_disk_used_percent")
    finally:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
