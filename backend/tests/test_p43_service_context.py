"""P4.3 服务上下文的领域、Tool 与执行器边界测试。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import pytest

from src.application.contracts import CreateSessionCommand, DiagnosisExecutionEvent
from src.application.errors import ServiceNotFoundError
from src.application.message_routing import requires_database_context
from src.application.services import SessionApplicationService, _safe_event_data
from src.domain.diagnosis import RunEventType
from src.domain.records import SessionData
from src.domain.services import ServiceRegistry
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from src.tools.db_tools import ShowIndexTool


def test_已注册服务可创建领域会话且服务注册表拒绝旧服务() -> None:
    """服务合法性由静态注册表应用边界统一校验。"""
    assert SessionData(title="生产调查", service_id="postgres-production").service_id == "postgres-production"
    with pytest.raises(ServiceNotFoundError):
        SessionApplicationService(lambda: None, registry=ServiceRegistry(())).create_session(  # type: ignore[arg-type]
            CreateSessionCommand(title="旧演示", service_id="order-service")
        )


def test_未绑定服务的数据库工具诚实拒绝() -> None:
    """未绑定会话不能退回固定生产连接，也不伪造未配置状态。"""
    assert ShowIndexTool(service_id=None).execute("orders") == "数据库未选择目标服务"


def test_明确数据库调查需要服务上下文() -> None:
    """受理层能识别未绑定会话不能直接发起的数据库调查。"""
    assert requires_database_context("请检查 orders 表的索引") is True
    assert requires_database_context("请检查接口 5xx 日志") is False
    assert requires_database_context("请查看日志表中的错误记录") is False
    assert requires_database_context("请检查数据库日志中的慢查询") is True


def test_工具事件携带绑定服务且仍只保留安全摘要() -> None:
    """Run Trace 可追溯服务，但不承载原始工具输出。"""
    data = _safe_event_data(
        DiagnosisExecutionEvent(
            type=RunEventType.TOOL_INVOKED,
            node="tool",
            occurred_at=datetime.now(UTC),
            data={"summary": "只读工具完成", "service_id": "postgres-staging", "status": "ok"},
        )
    )
    assert data == {"node": "tool", "summary": "只读工具完成", "status": "ok", "service_id": "postgres-staging"}


def test_执行器把服务上下文传给每次新建内核() -> None:
    """每次 Run 都以绑定服务创建隔离 Coordinator。"""
    seen: list[str | None] = []

    class Coordinator:
        def route_stream(self, _query: str) -> Iterator[dict[str, Any]]:
            yield {
                "kind": "trace",
                "event": {
                    "type": "tool_invoked",
                    "node": "tool",
                    "role": "db",
                    "detail": "只读工具完成",
                    "status": "ok",
                },
            }
            yield {"kind": "complete", "result": "完成", "strategy": "direct", "trace": []}

    def factory(service_id: str | None) -> Coordinator:
        seen.append(service_id)
        return Coordinator()

    events = list(CoordinatorDiagnosisExecutor(factory).stream("检查", "postgres-staging"))
    assert seen == ["postgres-staging"]
    assert events[0].data == {
        "summary": "只读工具完成",
        "status": "ok",
        "role": "db",
        "service_id": "postgres-staging",
    }
    assert all("order-service" not in str(getattr(event, "data", event)) for event in events)
