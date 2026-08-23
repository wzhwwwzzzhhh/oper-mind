"""P2.3 Coordinator 诊断适配的安全边界验证。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.application.contracts import DiagnosisExecutionError, DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor


class FakeCoordinator:
    """模拟阶段一 Coordinator 的流式响应。"""

    def __init__(self, items: list[dict[str, object]]) -> None:
        self._items = items

    def route_stream(self, query: str) -> Iterator[dict[str, object]]:
        """返回预设流，保留 Adapter 对 detail 的安全过滤验证。"""
        assert query == "检查安全适配"
        yield from self._items


def test_coordinator适配清空trace_detail但透传报告正文() -> None:
    """Adapter 清空 trace 原始 detail/CoT，但把最终报告作为用户答复透传。"""
    executor = CoordinatorDiagnosisExecutor(
        lambda: FakeCoordinator(
            [
                {
                    "kind": "trace",
                    "event": {
                        "type": "agent_done",
                        "node": "db",
                        "detail": "SELECT secret FROM credentials",
                        "timestamp": "2026-07-26T09:00:00Z",
                    },
                },
                {
                    "kind": "complete",
                    "result": "# 诊断报告\n初步判断为连接池耗尽。",
                    "strategy": "direct",
                    "trace": [],
                },
            ]
        )
    )

    items = list(executor.stream("检查安全适配"))

    # trace 事件仍只保留受控 type/node/time，原始 detail 不外流
    assert isinstance(items[0], DiagnosisExecutionEvent)
    assert items[0].type == RunEventType.AGENT_DONE
    assert items[0].node == "db"
    assert items[0].data == {}
    # 最终报告是面向用户的答复，可安全透传作为 summary 来源
    assert isinstance(items[1], DiagnosisExecutionResult)
    assert items[1].strategy == "direct"
    assert items[1].report == "# 诊断报告\n初步判断为连接池耗尽。"


def test_coordinator适配每次stream都现造独立内核() -> None:
    """并发隔离：每次 stream 都通过工厂新造内核，不复用同一实例。"""
    created: list[FakeCoordinator] = []

    def factory() -> FakeCoordinator:
        coordinator = FakeCoordinator(
            [{"kind": "complete", "result": "报告", "strategy": "direct", "trace": []}]
        )
        created.append(coordinator)
        return coordinator

    executor = CoordinatorDiagnosisExecutor(factory)
    list(executor.stream("检查安全适配"))
    list(executor.stream("检查安全适配"))

    assert len(created) == 2
    assert created[0] is not created[1]


def test_coordinator适配将阶段一错误映射为安全执行错误() -> None:
    """阶段一 error item 只能作为安全执行错误向 Application Service 抛出。"""
    executor = CoordinatorDiagnosisExecutor(
        lambda: FakeCoordinator(
            [{"kind": "error", "code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}]
        )
    )

    with pytest.raises(DiagnosisExecutionError, match="诊断执行失败") as captured:
        list(executor.stream("检查安全适配"))
    assert captured.value.code == "DIAGNOSIS_FAILED"


def test_coordinator最终报告执行末端再次安全投影() -> None:
    """即使上游误传原始请求、SQL、路径与 traceback，执行端也必须移除。"""
    executor = CoordinatorDiagnosisExecutor(
        lambda: FakeCoordinator(
            [
                {
                    "kind": "complete",
                    "result": (
                        "# 诊断报告\nSELECT secret FROM account\n"
                        "C:\\private\\trace.log\nTraceback (most recent call last)\n证据来源：数据库工具"
                    ),
                    "strategy": "direct",
                    "trace": [],
                }
            ]
        )
    )
    result = next(executor.stream("检查安全适配"))
    assert isinstance(result, DiagnosisExecutionResult)
    assert result.report is not None
    assert "SELECT secret" not in result.report
    assert "C:\\private" not in result.report
    assert "Traceback" not in result.report
    assert "证据来源" in result.report
