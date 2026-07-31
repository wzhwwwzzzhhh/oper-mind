"""P4.3 服务活动只读模型的 Repository 端口。"""

from __future__ import annotations

from typing import Protocol

from src.domain.records import DiagnosisRunCursor, RepositoryPage
from src.domain.services import ServiceActivityData


class ServiceActivityRepository(Protocol):
    """按静态服务关联范围读取历史调查与修复摘要。"""

    def list_by_service_id(
        self,
        service_id: str,
        cursor: DiagnosisRunCursor | None,
        limit: int,
    ) -> RepositoryPage[ServiceActivityData, DiagnosisRunCursor]:
        """按 Run 创建时间倒序读取服务活动页。"""
