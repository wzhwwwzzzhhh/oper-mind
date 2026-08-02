"""为运行事件新增受控的 tool_invoked 类型。

Revision ID: 20260802_04_p2_tool_invoked
Revises: 20260731_03_p4_service_center
Create Date: 2026-08-02

工具网关的每次调用要作为一等运行事件（tool_invoked）持久化并经 SSE 重放，
因此需把 run_events 的 type CHECK 约束扩展一个合法取值。SQLite 不支持直接
ALTER CHECK，故用 batch_alter_table 重建约束；PostgreSQL 走同一 API 亦可。

约束命名陷阱：create_table 内 `name="run_event_type_valid"` 的 CheckConstraint，
SQLAlchemy 建表时自动加 `ck_run_events_` 表前缀，实际名 `ck_run_events_run_event_type_valid`。
而 batch_alter_table 在 drop/create 时**也会**自动加同样的前缀——所以这里必须传
**裸名** `run_event_type_valid`，batch 会解析成真实约束名；传全名会导致双重前缀、
"找不到约束"报错。
"""

from __future__ import annotations

from alembic import op


revision = "20260802_04_p2_tool_invoked"
down_revision = "20260731_03_p4_service_center"
branch_labels = None
depends_on = None


# batch_alter_table 会自动加 `ck_run_events_` 前缀，因此这里用裸名。
_TYPE_CHECK_BARE_NAME = "run_event_type_valid"

# 扩展后（含 tool_invoked）与扩展前（原始 12 类）的合法取值集合。
# 文本与 P2 初始迁移保持一致（单引号、无多余空格）。
_TYPES_WITH_TOOL = (
    "type IN ('run_queued', 'run_started', 'route_decided', 'agent_start', "
    "'agent_done', 'conflict_checked', 'debate_round', 'report', 'reflection', "
    "'run_succeeded', 'run_failed', 'run_cancelled', 'tool_invoked')"
)
_TYPES_ORIGINAL = (
    "type IN ('run_queued', 'run_started', 'route_decided', 'agent_start', "
    "'agent_done', 'conflict_checked', 'debate_round', 'report', 'reflection', "
    "'run_succeeded', 'run_failed', 'run_cancelled')"
)


def upgrade() -> None:
    """把 tool_invoked 加入 run_events.type 的合法取值。"""
    with op.batch_alter_table("run_events", schema=None) as batch_op:
        batch_op.drop_constraint(_TYPE_CHECK_BARE_NAME, type_="check")
        batch_op.create_check_constraint(_TYPE_CHECK_BARE_NAME, _TYPES_WITH_TOOL)


def downgrade() -> None:
    """回退到不含 tool_invoked 的原始合法取值。"""
    with op.batch_alter_table("run_events", schema=None) as batch_op:
        batch_op.drop_constraint(_TYPE_CHECK_BARE_NAME, type_="check")
        batch_op.create_check_constraint(_TYPE_CHECK_BARE_NAME, _TYPES_ORIGINAL)
