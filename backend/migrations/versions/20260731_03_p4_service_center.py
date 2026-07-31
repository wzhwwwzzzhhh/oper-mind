"""为服务中心增加会话静态服务关联。

Revision ID: 20260731_03_p4_service_center
Revises: 20260730_02_p4_actions
Create Date: 2026-07-31
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260731_03_p4_service_center"
down_revision = "20260730_02_p4_actions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """为既有会话增加可空且受限的静态服务键。"""
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.add_column(sa.Column("service_id", sa.String(length=64), nullable=True))
        batch_op.create_check_constraint(
            "session_service_id_valid",
            "service_id IS NULL OR service_id = 'order-service'",
        )
        batch_op.create_index(
            "ix_sessions_service_updated_at_id",
            ["service_id", "updated_at", "id"],
            unique=False,
        )


def downgrade() -> None:
    """删除 P4.3 关联字段，不触碰任何诊断靶场资源。"""
    with op.batch_alter_table("sessions") as batch_op:
        batch_op.drop_index("ix_sessions_service_updated_at_id")
        batch_op.drop_constraint("session_service_id_valid", type_="check")
        batch_op.drop_column("service_id")
