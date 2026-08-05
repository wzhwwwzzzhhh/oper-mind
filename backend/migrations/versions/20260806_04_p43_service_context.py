"""P4.3 贯通会话服务上下文到诊断 Run。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260806_04_p43_service_context"
down_revision = "20260802_04_p2_tool_invoked"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """放开已注册 PostgreSQL 实例并保存 Run 来源服务。"""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.drop_constraint("session_service_id_valid", type_="check")
            batch_op.create_check_constraint(
                "session_service_id_valid",
                "service_id IS NULL OR service_id IN ('postgres-production', 'postgres-staging')",
            )
    finally:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    with op.batch_alter_table("diagnosis_runs") as batch_op:
        batch_op.add_column(sa.Column("service_id", sa.String(length=64), nullable=True))
        batch_op.create_index("ix_diagnosis_runs_service_created_at_id", ["service_id", "created_at", "id"], unique=False)


def downgrade() -> None:
    """回滚 P4.3 字段并恢复旧服务约束。"""
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT COUNT(*) FROM sessions "
            "WHERE service_id IN ('postgres-production', 'postgres-staging')"
        )
    ):
        raise RuntimeError("无法回滚：sessions 中仍存在 P4.3 服务上下文数据。")
    with op.batch_alter_table("diagnosis_runs") as batch_op:
        batch_op.drop_index("ix_diagnosis_runs_service_created_at_id")
        batch_op.drop_column("service_id")
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    try:
        with op.batch_alter_table("sessions") as batch_op:
            batch_op.drop_constraint("session_service_id_valid", type_="check")
            batch_op.create_check_constraint(
                "session_service_id_valid",
                "service_id IS NULL OR service_id = 'order-service'",
            )
    finally:
        if connection.dialect.name == "sqlite":
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
