"""P8 审计导出渲染：CSV / Markdown 确定性输出 + 元信息块 + 兜底脱敏。"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import datetime

from src.core.tool_gateway import desensitize
from src.domain.audit import AuditActivityData
from src.domain.audit_export import AuditExportFormat, AuditExportResult

# 与 AuditActivityResource 完全一致（Design D2，18 字段同投影）。
_EXPORT_FIELDS: tuple[str, ...] = (
    "id",
    "kind",
    "type",
    "occurred_at",
    "service_id",
    "session_id",
    "session_title",
    "outcome",
    "summary",
    "run_id",
    "severity",
    "confidence",
    "proposal_status",
    "verification_status",
    "proposal_id",
    "action_id",
    "mode",
    "approval_actor",
)

_META_LABELS: dict[str, str] = {
    "exported_at": "导出时间",
    "filters": "过滤条件",
    "count": "条数",
    "note": "说明",
}

_NOTE_TEXT = "只读快照，不含原始证据、工具输出与凭据"


def _format_timestamp(value: datetime) -> str:
    """与列表资源同款 UTC 时间格式（毫秒 + Z），保证确定性。"""
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _filter_description(
    *,
    from_at: datetime | None,
    to_at: datetime | None,
    service_id: str | None,
    action_type: str | None,
    outcome: str | None,
) -> str:
    """如实序列化过滤条件；未过滤项标注"无"，不写含糊值。"""
    parts = [
        f"from={_format_timestamp(from_at) if from_at else '无'}",
        f"to={_format_timestamp(to_at) if to_at else '无'}",
        f"service_id={service_id or '无'}",
        f"action_type={action_type or '无'}",
        f"result={outcome or '无'}",
    ]
    return "; ".join(parts)


def _activity_row(item: AuditActivityData) -> dict[str, object]:
    """把审计活动收敛为导出行；文本字段兜底脱敏。"""
    return {
        "id": str(item.id),
        "kind": item.kind.value,
        "type": item.type.value,
        "occurred_at": _format_timestamp(item.occurred_at),
        "service_id": item.service_id or "",
        "session_id": str(item.session_id),
        "session_title": desensitize(item.session_title),
        "outcome": item.outcome.value,
        "summary": desensitize(item.summary) if item.summary else "",
        "run_id": str(item.run_id) if item.run_id else "",
        "severity": item.severity or "",
        "confidence": "" if item.confidence is None else f"{item.confidence:.2f}",
        "proposal_status": item.proposal_status or "",
        "verification_status": item.verification_status or "",
        "proposal_id": str(item.proposal_id) if item.proposal_id else "",
        "action_id": item.action_id or "",
        "mode": item.mode or "",
        "approval_actor": item.approval_actor or "",
    }


def _meta_lines(result: AuditExportResult, filters: str, count: int) -> list[str]:
    """构造元信息四要素（导出时间 / 过滤条件 / 条数 / 快照标注）。"""
    return [
        f"{_META_LABELS['exported_at']}: {_format_timestamp(result.exported_at)}",
        f"{_META_LABELS['filters']}: {filters}",
        f"{_META_LABELS['count']}: {count}",
        f"{_META_LABELS['note']}: {_NOTE_TEXT}",
    ]


def _render_csv(result: AuditExportResult, filters: str) -> Iterator[str]:
    """流式渲染 CSV：元信息 # 注释行 + 空行 + 表头 + 数据行。"""
    for line in _meta_lines(result, filters, len(result.items)):
        yield f"# {line}\n"
    yield "\n"
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(_EXPORT_FIELDS)
    yield buffer.getvalue()
    for item in result.items:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([_activity_row(item)[field] for field in _EXPORT_FIELDS])
        yield buffer.getvalue()


def _md_escape(value: str) -> str:
    """转义 Markdown 表格分隔符与换行，避免破坏表格结构。"""
    return value.replace("|", "\\|").replace("\n", " ").replace("\r", " ")


def _render_markdown(result: AuditExportResult, filters: str) -> Iterator[str]:
    """流式渲染 Markdown：导出元信息块 + 活动记录表格。"""
    yield "## 导出元信息\n\n"
    for line in _meta_lines(result, filters, len(result.items)):
        yield f"- {line}\n"
    yield "\n## 活动记录\n\n"
    if not result.items:
        yield "无匹配记录\n"
        return
    yield "| " + " | ".join(_EXPORT_FIELDS) + " |\n"
    yield "| " + " | ".join("---" for _ in _EXPORT_FIELDS) + " |\n"
    for item in result.items:
        row = _activity_row(item)
        cells = [_md_escape(str(row[field])) for field in _EXPORT_FIELDS]
        yield "| " + " | ".join(cells) + " |\n"


def render_audit_export(
    result: AuditExportResult,
    fmt: AuditExportFormat,
    *,
    from_at: datetime | None,
    to_at: datetime | None,
    service_id: str | None,
    action_type: str | None,
    outcome: str | None,
) -> Iterator[str]:
    """把导出结果流式渲染为指定格式文本块（确定性：稳定排序 + 固定字段序）。"""
    filters = _filter_description(
        from_at=from_at,
        to_at=to_at,
        service_id=service_id,
        action_type=action_type,
        outcome=outcome,
    )
    if fmt is AuditExportFormat.CSV:
        yield from _render_csv(result, filters)
    else:
        yield from _render_markdown(result, filters)
