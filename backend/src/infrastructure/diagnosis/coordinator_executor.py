"""P2 对既有 Coordinator 的安全诊断适配。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from inspect import signature
from typing import Any

from src.application.contracts import (
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
    DiagnosisExecutor,
)
from src.core.coordinator import CoordinatorAgent
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.postgres_missing_index import PostgresMissingIndexCollector


class CoordinatorDiagnosisExecutor(DiagnosisExecutor):
    """将多 Agent 内核流转为不包含原始 detail 的应用执行端口。

    每次 stream 通过工厂现造一套内核，使并发 Run 之间的 Agent 状态互相隔离；
    不复用单例，避免 short_term/thinking 等实例级可变状态跨 Run 相互踩踏。
    """

    def __init__(
        self,
        coordinator_factory: Callable[[], CoordinatorAgent],
        missing_index_collector: PostgresMissingIndexCollector | None = None,
    ) -> None:
        self._coordinator_factory = coordinator_factory
        self._missing_index_collector = missing_index_collector

    def stream(self, query: str, service_id: str | None = None) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """转发受控事件，并将执行错误转换为安全应用错误。"""
        if len(signature(self._coordinator_factory).parameters) == 0:
            coordinator = self._coordinator_factory()
        else:
            coordinator = self._coordinator_factory(service_id)
        for item in coordinator.route_stream(query):
            kind = item["kind"]
            if kind == "trace":
                event = item["event"]
                event_type = _event_type(event)
                if event_type is not None:
                    yield DiagnosisExecutionEvent(
                        type=event_type,
                        node=_safe_node(event.get("node")),
                        occurred_at=_parse_timestamp(event.get("timestamp")),
                        data=_event_data(event, service_id),
                    )
            elif kind == "complete":
                yield DiagnosisExecutionResult(
                    strategy=_safe_strategy(item.get("strategy")),
                    report=_safe_report(item.get("result")),
                    evidence_investigation=(
                        self._missing_index_collector.collect(service_id, query)
                        if self._missing_index_collector is not None
                        else None
                    ),
                )
            else:
                raise DiagnosisExecutionError(code=item["code"], message=item["message"])


def _event_type(value: dict[str, Any]) -> RunEventType | None:
    """仅接受 P2 受控的 Coordinator 事件类型。"""
    try:
        return RunEventType(str(value.get("type", "")))
    except ValueError:
        return None


def _event_data(event: dict[str, Any], service_id: str | None = None) -> dict[str, Any]:
    """仅为工具事件构造安全 data；其余事件保持空 data，维持既有行为。"""
    if str(event.get("type")) != "tool_invoked":
        return {}
    data: dict[str, Any] = {}
    detail = event.get("detail")
    if isinstance(detail, str) and detail:
        data["summary"] = detail[:280]
    status = event.get("status")
    if isinstance(status, str):
        data["status"] = status
    duration = event.get("duration_ms")
    if isinstance(duration, int) and not isinstance(duration, bool):
        data["duration_ms"] = duration
    if service_id is not None:
        data["service_id"] = service_id
    return data


def _safe_node(value: object) -> str:
    """将节点名收敛为非空、有限长度的展示标识。"""
    node = str(value).strip()
    return node[:80] if node else "unknown"


def _safe_strategy(value: object) -> str | None:
    """限制策略字符串，避免把非结构化执行内容带入持久化。"""
    strategy = str(value).strip()
    return strategy[:80] if strategy else None


def _safe_report(value: object) -> str | None:
    """收敛大脑最终报告为有界的用户可读答复。

    报告是 Report Agent 面向用户的最终结论文本，可安全展示；这里只做类型
    与长度收敛，不改变内容，也不把它当作结构化事实来源。
    """
    if not isinstance(value, str):
        return None
    report = value.strip()
    if not report:
        return None
    return report[:8000]


def _parse_timestamp(value: object) -> datetime:
    """解析既有 UTC 时间戳，异常时使用当前 UTC 时间。"""
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
