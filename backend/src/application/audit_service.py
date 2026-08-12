"""P8 跨服务跨会话审计活动检索用例（只读）。"""

from __future__ import annotations

from datetime import datetime

from src.domain.audit import AuditActivityCursor, AuditActivityData, AuditActivityType, AuditOutcome
from src.domain.records import RepositoryPage
from src.infrastructure.persistence.audit_repositories import SqlAlchemyAuditActivityRepository
from src.infrastructure.persistence.database import SessionFactory


class AuditApplicationService:
    """统一审计流的只读分页检索；窗口校验在路由层映射为明确错误。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

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
        session = self._session_factory()
        try:
            return SqlAlchemyAuditActivityRepository(session).list_activities(
                cursor=cursor,
                limit=limit,
                from_at=from_at,
                to_at=to_at,
                service_id=service_id,
                action_type=action_type,
                outcome=outcome,
            )
        finally:
            session.close()
