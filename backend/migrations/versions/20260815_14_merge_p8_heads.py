"""P8 并行迁移 head 合并：收敛消息编辑 / 用量统计两条链为唯一 head。

main 上消息编辑（20260814_13_p8_message_edit_delete）与监控阈值
（20260815_13_p8_monitor_thresholds）并行接在 12 之后形成多头；本切片迁移
（20260813_13_p8_model_usage）接在监控阈值链后。此 merge migration 把
消息编辑链与用量统计链合并为单一 head，使 ``alembic upgrade head`` 唯一确定。
"""

from __future__ import annotations

revision = "20260815_14_merge_p8_heads"
down_revision = ("20260814_13_p8_message_edit_delete", "20260813_13_p8_model_usage")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """纯合并点：无 schema 变更。"""
    pass


def downgrade() -> None:
    """纯合并点：无 schema 变更。"""
    pass
