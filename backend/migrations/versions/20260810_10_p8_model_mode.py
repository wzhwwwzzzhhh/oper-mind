"""P8 应用库通用键值运行时设置表。"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260810_10_p8_model_mode"
down_revision = "20260808_09_p6_session_services"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """创建 app_settings 键值表，用于运行时模式等标量设置。"""
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=100), nullable=False),
        sa.Column("value", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key", name="pk_app_settings"),
    )


def downgrade() -> None:
    """删除 app_settings 表；键值设置丢失为可接受代价。"""
    op.drop_table("app_settings")
