"""验证 P2-B 工具调用审计记录的 Trace 管道接缝。"""

from datetime import datetime, timezone

from src.application.contracts import DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.application.services import _safe_event_data
from src.core.coordinator import CoordinatorAgent
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor


class FakeCoordinator:
    """产出工具事件和完成事件的最小 Coordinator。"""

    def route_stream(self, query: str):
        """按任务约定产出受控流事件。"""
        assert query == "q"
        yield {
            "kind": "trace",
            "event": {
                "type": "tool_invoked",
                "node": "tool",
                "detail": "调用 explain_sql 成功",
                "status": "ok",
                "duration_ms": 7,
                "timestamp": "2026-08-02T00:00:00+00:00",
            },
        }
        yield {
            "kind": "trace",
            "event": {
                "type": "route_decided",
                "node": "route",
                "detail": "路由完成",
                "timestamp": "2026-08-02T00:00:00+00:00",
            },
        }
        yield {"kind": "complete", "strategy": "direct", "result": "报告正文"}


def test_executor_emits_safe_tool_event_data() -> None:
    """执行器应保留工具事件的摘要、状态和耗时，其他事件 data 为空。"""
    executor = CoordinatorDiagnosisExecutor(FakeCoordinator)
    events = list(executor.stream("q"))

    assert isinstance(events[0], DiagnosisExecutionEvent)
    assert events[0].type is RunEventType.TOOL_INVOKED
    assert events[0].data["summary"] == "调用 explain_sql 成功"
    assert events[0].data["status"] == "ok"
    assert events[0].data["duration_ms"] == 7
    assert isinstance(events[1], DiagnosisExecutionEvent)
    assert events[1].data == {}
    assert isinstance(events[2], DiagnosisExecutionResult)


def test_safe_event_data_preserves_gateway_statuses() -> None:
    """Application Service 应保留工具摘要、网关状态和耗时白名单字段。"""
    occurred_at = datetime.now(timezone.utc)
    event = DiagnosisExecutionEvent(
        type=RunEventType.TOOL_INVOKED,
        node="tool",
        occurred_at=occurred_at,
        data={"summary": "调用 x 成功", "status": "ok", "duration_ms": 7},
    )

    safe_data = _safe_event_data(event)
    assert safe_data["summary"] == "调用 x 成功"
    assert safe_data["status"] == "ok"
    assert safe_data["duration_ms"] == 7

    rejected = event.model_copy(update={"data": {"summary": "调用 x 被拒绝", "status": "rejected"}})
    assert _safe_event_data(rejected)["status"] == "rejected"


def test_coordinator_normalizes_tool_trace_fields() -> None:
    """Coordinator 应将工具 Trace 映射为 tool_invoked 并保留结构化字段。"""
    agent = CoordinatorAgent(llm=object())
    normalized = agent._normalize_trace(
        [
            {"node": "tool", "detail": "调用 x 成功", "status": "ok", "duration_ms": 7},
            {"node": "route", "detail": "x"},
        ]
    )

    assert normalized[0]["type"] == "tool_invoked"
    assert normalized[0]["status"] == "ok"
    assert normalized[0]["duration_ms"] == 7
    assert "status" not in normalized[1]
    assert "duration_ms" not in normalized[1]
