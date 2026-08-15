"""P8 跨服务跨会话审计活动检索与导出用例（只读）。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.application.errors import AuditExportLimitExceededError
from src.domain.audit import AuditActivityCursor, AuditActivityData, AuditActivityType, AuditOutcome
from src.domain.audit_export import AuditExportResult
from src.domain.audit_repositories import AuditActivityRepository
from src.domain.records import RepositoryPage, utc_now


class AuditApplicationService:
    """统一审计流的只读分页检索与导出；仓储经端口注入，装配在 dependencies.py。"""

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

    def export_activities(
        self,
        max_items: int,
        *,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        service_id: str | None = None,
        action_type: AuditActivityType | None = None,
        outcome: AuditOutcome | None = None,
    ) -> AuditExportResult:
        """读取受上限约束的审计活动全量快照；超限抛明确错误，不返回截断数据。"""
        repository = self._repository_factory()
        try:
            items, truncated = repository.list_all_activities(
                max_items,
                from_at=from_at,
                to_at=to_at,
                service_id=service_id,
                action_type=action_type,
                outcome=outcome,
            )
        finally:
            repository.close()
        if truncated:
            raise AuditExportLimitExceededError()
        return AuditExportResult(items=items, truncated=False, exported_at=utc_now())
