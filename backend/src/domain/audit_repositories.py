"""P8 审计活动只读检索的 Repository 端口。"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from src.domain.audit import AuditActivityCursor, AuditActivityData, AuditActivityType, AuditOutcome
from src.domain.records import RepositoryPage


class AuditActivityRepository(Protocol):
    """跨服务跨会话读取统一审计流的安全摘要页。"""

    def list_activities(
        self,
        cursor: AuditActivityCursor | None,
        limit: int,
        *,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        service_id: str | None = None,
        action_type: AuditActivityType | None = None,
        outcome: AuditOutcome | None = None,
    ) -> RepositoryPage[AuditActivityData, AuditActivityCursor]:
        """按 (time desc, id desc) 键集读取一页审计活动。"""

    def list_all_activities(
        self,
        max_items: int,
        *,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        service_id: str | None = None,
        action_type: AuditActivityType | None = None,
        outcome: AuditOutcome | None = None,
    ) -> tuple[list[AuditActivityData], bool]:
        """读取受上限约束的审计活动全量快照，返回 (items, truncated)。

        truncated 为 True 表示结果超过 max_items（两侧各取 max_items+1 归并判定），
        由应用层转为明确错误，不返回截断未标明的半截数据。
        """

    def close(self) -> None:
        """释放本次调用持有的数据库会话。"""
