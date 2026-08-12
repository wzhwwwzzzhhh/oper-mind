"""P8 跨服务跨会话审计活动检索用例（只读）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.domain.audit import AuditActivityCursor, AuditActivityData, AuditActivityType, AuditOutcome
from src.domain.audit_repositories import AuditActivityRepository
from src.domain.records import RepositoryPage


class AuditApplicationService:
    """统一审计流的只读分页检索；仓储经端口注入，装配在 dependencies.py。"""

    def __init__(self, repository_factory: Callable[[], AuditActivityRepository]) -> None:
        self._repository_factory = repository_factory

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
        """读取统一审计流的一页安全摘要（Run + action 事件双源归并）。"""
        repository = self._repository_factory()
        try:
            return repository.list_activities(
                cursor=cursor,
                limit=limit,
                from_at=from_at,
                to_at=to_at,
                service_id=service_id,
                action_type=action_type,
                outcome=outcome,
            )
        finally:
            repository.close()
