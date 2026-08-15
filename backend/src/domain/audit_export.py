"""P8 审计导出的领域模型：格式枚举与导出结果。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field

from src.domain.audit import AuditActivityData
from src.domain.records import DomainRecord

# 单次导出条数上限（Design §6 决策 2，用户已确认）。
EXPORT_MAX_ITEMS: int = 5000


class AuditExportFormat(StrEnum):
    """导出文件格式。"""

    CSV = "csv"
    MD = "md"


class AuditExportResult(DomainRecord):
    """一次审计导出的只读快照结果。"""

    items: list[AuditActivityData]
    truncated: bool = Field(description="结果是否超过上限被截断（超限时由应用层转为明确错误，不落文件）")
    exported_at: datetime = Field(description="导出时刻（UTC aware，元信息如实标注）")
