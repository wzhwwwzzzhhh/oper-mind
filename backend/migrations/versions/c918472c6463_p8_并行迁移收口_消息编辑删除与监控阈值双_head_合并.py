"""P8 并行迁移收口——消息编辑删除与监控阈值双 head 合并

Revision ID: c918472c6463
Revises: 20260814_13_p8_message_edit_delete, 20260815_13_p8_monitor_thresholds
Create Date: 2026-08-15 13:25:06.785193
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = 'c918472c6463'
down_revision = ('20260814_13_p8_message_edit_delete', '20260815_13_p8_monitor_thresholds')
branch_labels = None
depends_on = None


def upgrade() -> None:
    """应用迁移。"""
    pass


def downgrade() -> None:
    """回滚迁移。"""
    pass
