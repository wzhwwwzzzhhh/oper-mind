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


def test_coordinator适配不转存trace_detail或报告正文() -> None:
    """Adapter 只能输出受控 type/node/time 与有限 strategy。"""
    executor = CoordinatorDiagnosisExecutor(
        FakeCoordinator(
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
                    "result": "# 原始 Markdown 报告，不应进入执行结果",
                    "strategy": "direct",
                    "trace": [],
                },
            ]
        )
    )

    items = list(executor.stream("检查安全适配"))

    assert isinstance(items[0], DiagnosisExecutionEvent)
    assert items[0].type == RunEventType.AGENT_DONE
    assert items[0].node == "db"
    assert items[0].data == {}
    assert isinstance(items[1], DiagnosisExecutionResult)
    assert items[1].strategy == "direct"


def test_coordinator适配将阶段一错误映射为安全执行错误() -> None:
    """阶段一 error item 只能作为安全执行错误向 Application Service 抛出。"""
    executor = CoordinatorDiagnosisExecutor(
        FakeCoordinator(
            [{"kind": "error", "code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}]
        )
    )

    with pytest.raises(DiagnosisExecutionError, match="诊断执行失败") as captured:
        list(executor.stream("检查安全适配"))
    assert captured.value.code == "DIAGNOSIS_FAILED"
