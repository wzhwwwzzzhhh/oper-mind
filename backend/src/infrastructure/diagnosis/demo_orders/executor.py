"""P4.1 会话驱动的订单慢查询只读调查执行器。"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Protocol, TypeVar

from src.application.contracts import DiagnosisExecutionError, DiagnosisExecutionEvent, DiagnosisExecutionResult, DiagnosisExecutor
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.demo_orders.collectors import (
    CollectorOutcome,
    SnapshotCollector,
    build_evidence_investigation_result,
)
from src.infrastructure.diagnosis.demo_orders.log_reader import OrderServiceLogReader
from src.infrastructure.diagnosis.demo_orders.models import (
    DatabaseEvidenceSnapshot,
    EvidenceSnapshot,
    LogEvidenceSnapshot,
    ServerEvidenceSnapshot,
)
from src.infrastructure.diagnosis.demo_orders.postgres_reader import (
    DemoOrdersSourceError,
    PostgresDemoOrdersDatabaseClient,
    PostgresEvidenceReader,
)
from src.infrastructure.diagnosis.demo_orders.service_reader import HttpDemoOrdersServiceClient, OrderServiceEvidenceReader
from src.infrastructure.diagnosis.demo_orders.settings import DemoOrdersEvidenceSettings, EvidenceMode


SnapshotT = TypeVar("SnapshotT", bound=EvidenceSnapshot)


class StreamExecutor(Protocol):
    """可由 P4.1 路由器复用的诊断执行端口。"""

    def stream(self, query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """输出既有 P2 事件和一次最终结果。"""


class DemoOrdersInvestigationExecutor(DiagnosisExecutor):
    """并行协调 DB、日志、服务三类固定只读调查角色。"""

    def __init__(
        self,
        mode: EvidenceMode,
        database_collector: SnapshotCollector[DatabaseEvidenceSnapshot],
        log_collector: SnapshotCollector[LogEvidenceSnapshot],
        server_collector: SnapshotCollector[ServerEvidenceSnapshot],
    ) -> None:
        self._mode = mode
        self._database_collector = database_collector
        self._log_collector = log_collector
        self._server_collector = server_collector

    @classmethod
    def from_settings(cls, settings: DemoOrdersEvidenceSettings) -> "DemoOrdersInvestigationExecutor":
        """按 mock 或 target 配置装配相同契约的三个 Collector。"""
        if settings.mode is EvidenceMode.MOCK:
            return cls(
                settings.mode,
                SnapshotCollector("db", _mock_database_snapshot),
                SnapshotCollector("log", _mock_log_snapshot),
                SnapshotCollector("server", _mock_server_snapshot),
            )
        if settings.mode is EvidenceMode.TARGET:
            return cls(
                settings.mode,
                SnapshotCollector("db", PostgresEvidenceReader(PostgresDemoOrdersDatabaseClient(settings)).collect),
                SnapshotCollector("log", OrderServiceLogReader(settings).collect),
                SnapshotCollector("server", OrderServiceEvidenceReader(HttpDemoOrdersServiceClient(settings)).collect),
            )
        raise ValueError("disabled 模式不可装配订单慢查询调查执行器。")

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """发送最小角色进度事件，再并行采集和组装确定性结论。"""
        yield _event(
            RunEventType.ROUTE_DECIDED,
            "orders_slow_query_route",
            "已识别订单慢查询场景，开始并行收集只读证据。",
            mode=self._mode.value,
        )
        collectors = (self._database_collector, self._log_collector, self._server_collector)
        for collector in collectors:
            yield _event(
                RunEventType.AGENT_START,
                f"{collector.role}_collector",
                f"{_display_name(collector.role)}正在收集只读证据。",
                role=collector.role,
                status="running",
            )

        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="orders-evidence") as pool:
            futures = {collector.role: pool.submit(collector.collect) for collector in collectors}
            database = _result_or_failed(futures["db"], "db")
            logs = _result_or_failed(futures["log"], "log")
            server = _result_or_failed(futures["server"], "server")

        for outcome in (database, logs, server):
            yield _event(
                RunEventType.AGENT_DONE,
                f"{outcome.role}_collector",
                _outcome_summary(outcome),
                role=outcome.role,
                status="completed" if outcome.completed else "failed",
                duration_ms=outcome.duration_ms,
            )

        try:
            investigation = build_evidence_investigation_result(database, logs, server)
        except DemoOrdersSourceError as error:
            raise DiagnosisExecutionError() from error
        yield DiagnosisExecutionResult(
            strategy="demo_orders_readonly_evidence",
            evidence_investigation=investigation,
        )


class RoutedDemoOrdersExecutor(DiagnosisExecutor):
    """只拦截明确订单慢查询意图，其余输入返回 MVP 范围说明。"""

    def __init__(self, demo_executor: StreamExecutor) -> None:
        self._demo_executor = demo_executor
        self._unsupported_executor = UnsupportedP4Executor()

    def stream(self, query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """根据确定性关键词路由，避免把任意问题伪装为订单调查。"""
        executor = self._demo_executor if is_demo_orders_slow_query(query) else self._unsupported_executor
        yield from executor.stream(query)


class UnsupportedP4Executor(DiagnosisExecutor):
    """在 P4.1 已开启时明确表达首版 MVP 的支持范围。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """不访问任何诊断源，只写入可审计的范围说明。"""
        yield _event(
            RunEventType.ROUTE_DECIDED,
            "p4_scope_route",
            "当前 MVP 仅支持订单慢查询的只读调查，本次未发起外部读取。",
        )
        yield DiagnosisExecutionResult(strategy="p4_unsupported_request")


class UnavailableDemoOrdersExecutor(DiagnosisExecutor):
    """target 配置非法时仅使受控场景安全失败，不阻断 legacy 路径。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """持久化一条脱敏路由摘要后关闭 Run。"""
        yield _event(
            RunEventType.ROUTE_DECIDED,
            "orders_slow_query_route",
            "订单慢查询只读证据源未就绪，无法安全开始调查。",
        )
        raise DiagnosisExecutionError()


def is_demo_orders_slow_query(query: str) -> bool:
    """首版仅识别明确包含订单和性能/查询语义的输入。"""
    normalized = query.strip().lower()
    mentions_orders = "订单" in normalized or "order" in normalized
    mentions_slow = any(token in normalized for token in ("慢查询", "变慢", "慢", "slow", "latency", "延迟"))
    mentions_query = any(token in normalized for token in ("查询", "sql", "索引", "数据库", "query"))
    return mentions_orders and mentions_slow and mentions_query


def _result_or_failed(
    future: Future[CollectorOutcome[SnapshotT]],
    role: str,
) -> CollectorOutcome[SnapshotT]:
    """收敛预期的源失败，意外程序错误则交给 Application Service 安全关闭 Run。"""
    try:
        return future.result()
    except (DemoOrdersSourceError, OSError, ValueError):
        return CollectorOutcome(role=role, snapshot=None, duration_ms=0)


def _event(
    event_type: RunEventType,
    node: str,
    summary: str,
    **data: object,
) -> DiagnosisExecutionEvent:
    """构造只含过程级安全字段的既有 RunEvent。"""
    return DiagnosisExecutionEvent(
        type=event_type,
        node=node,
        occurred_at=datetime.now(timezone.utc),
        data={"summary": summary, **data},
    )


def _display_name(role: str) -> str:
    """返回前端可展示的固定角色名称。"""
    return {"db": "数据库", "log": "日志", "server": "服务"}.get(role, "证据源")


def _outcome_summary(outcome: CollectorOutcome[object]) -> str:
    """生成不包含异常详情的角色完成摘要。"""
    if outcome.completed:
        return f"{_display_name(outcome.role)}只读证据已收集。"
    return f"{_display_name(outcome.role)}只读证据暂不可用。"


def _mock_database_snapshot() -> DatabaseEvidenceSnapshot:
    """提供与 target 相同语义的确定性数据库 mock。"""
    return DatabaseEvidenceSnapshot(
        observed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        target_database_confirmed=True,
        target_index_exists=False,
        plan_uses_seq_scan=True,
        plan_uses_target_index=False,
    )


def _mock_log_snapshot() -> LogEvidenceSnapshot:
    """提供确定性慢查询聚合日志 mock。"""
    return LogEvidenceSnapshot(
        observed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        matched_query_count=12,
        slow_query_count=10,
        timeout_count=0,
    )


def _mock_server_snapshot() -> ServerEvidenceSnapshot:
    """提供确定性服务延迟指标 mock。"""
    return ServerEvidenceSnapshot(
        observed_at=datetime(2026, 7, 30, tzinfo=timezone.utc),
        service_healthy=True,
        window_size=12,
        p50_ms=82.0,
        p95_ms=210.0,
        slow_query_count=10,
        timeout_count=0,
        slow_query_threshold_ms=100.0,
    )
