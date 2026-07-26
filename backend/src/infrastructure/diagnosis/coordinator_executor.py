"""P2 对既有 Coordinator 的安全诊断适配。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timezone
from typing import Any

from src.application.contracts import (
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
    DiagnosisExecutor,
)
from src.core.coordinator import CoordinatorAgent
from src.domain.diagnosis import RunEventType


class CoordinatorDiagnosisExecutor(DiagnosisExecutor):
    """将阶段一 Coordinator 流转为不包含原始 detail 的应用执行端口。"""

    def __init__(self, coordinator: CoordinatorAgent) -> None:
        self._coordinator = coordinator

    def stream(self, query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """转发受控事件，并将阶段一错误转换为安全应用错误。"""
        for item in self._coordinator.route_stream(query):
            kind = item["kind"]
            if kind == "trace":
                event = item["event"]
                event_type = _event_type(event)
                if event_type is not None:
                    yield DiagnosisExecutionEvent(
                        type=event_type,
                        node=_safe_node(event.get("node")),
                        occurred_at=_parse_timestamp(event.get("timestamp")),
                    )
            elif kind == "complete":
                yield DiagnosisExecutionResult(strategy=_safe_strategy(item.get("strategy")))
            else:
                raise DiagnosisExecutionError(code=item["code"], message=item["message"])


def _event_type(value: dict[str, Any]) -> RunEventType | None:
    """仅接受 P2 受控的 Coordinator 事件类型。"""
    try:
        return RunEventType(str(value.get("type", "")))
    except ValueError:
        return None


def _safe_node(value: object) -> str:
    """将节点名收敛为非空、有限长度的展示标识。"""
    node = str(value).strip()
    return node[:80] if node else "unknown"


def _safe_strategy(value: object) -> str | None:
    """限制策略字符串，避免把非结构化执行内容带入持久化。"""
    strategy = str(value).strip()
    return strategy[:80] if strategy else None


def _parse_timestamp(value: object) -> datetime:
    """解析既有 UTC 时间戳，异常时使用当前 UTC 时间。"""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
