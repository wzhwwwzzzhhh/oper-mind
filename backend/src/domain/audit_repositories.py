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
