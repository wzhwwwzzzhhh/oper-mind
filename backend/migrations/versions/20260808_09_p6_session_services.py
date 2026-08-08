"""P6 会话多服务关联。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260808_09_p6_session_services"
down_revision = "20260807_08_p6_host_metrics"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """建立会话服务关联表，不迁移历史单值服务上下文。"""
    op.create_table(
        "session_services",
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("service_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "service_id IN ('postgres-production', 'postgres-staging', 'postgres-target', 'redis-production')",
            name="session_services_service_id_valid",
        ),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("session_id", "service_id"),
    )
    op.create_index("ix_session_services_service_id", "session_services", ["service_id"])


def downgrade() -> None:
    """关联数据存在时拒绝回滚，避免丢失多服务会话上下文。"""
    if op.get_bind().scalar(sa.text("SELECT COUNT(*) FROM session_services")):
        raise RuntimeError("无法回滚：session_services 中仍存在会话服务关联数据。")
    op.drop_index("ix_session_services_service_id", table_name="session_services")
    op.drop_table("session_services")
