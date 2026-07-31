"""P4.3 订单服务靶场的静态注册与有限健康快照 Connector。"""

from __future__ import annotations

from datetime import datetime, timezone

from src.domain.services import (
    ORDER_SERVICE_ID,
    ORDER_SERVICE_SESSION_TITLE,
    ORDERS_SLOW_QUERY_DEFAULT_QUERY,
    ORDERS_SLOW_QUERY_INTENT_ID,
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceDatabaseStateData,
    ServiceDefinitionData,
    ServiceInvestigationData,
    ServiceMode,
    ServiceServerMetricsData,
    ServiceSnapshotData,
    ServiceSourceStatus,
)
from src.infrastructure.diagnosis.demo_orders.models import DatabaseEvidenceSnapshot, ServerEvidenceSnapshot
from src.infrastructure.diagnosis.demo_orders.postgres_reader import (
    DemoOrdersSourceError,
    PostgresDemoOrdersDatabaseClient,
    PostgresEvidenceReader,
)
from src.infrastructure.diagnosis.demo_orders.service_reader import HttpDemoOrdersServiceClient, OrderServiceEvidenceReader
from src.infrastructure.diagnosis.demo_orders.settings import DemoOrdersEvidenceSettings, EvidenceMode


class PostgresOrdersSlowQueryConnector:
    """唯一订单服务 Connector，仅复用 P4.1 已批准的固定只读读取器。"""

    def __init__(self, mode: ServiceMode, settings: DemoOrdersEvidenceSettings | None = None) -> None:
        if mode is ServiceMode.TARGET and settings is not None and settings.mode is not EvidenceMode.TARGET:
            raise ValueError("target 服务 Connector 必须使用 target 靶场配置。")
        if mode is ServiceMode.MOCK and settings is not None and settings.mode is not EvidenceMode.MOCK:
            raise ValueError("mock 服务 Connector 不接受非 mock 靶场配置。")
        self._mode = mode
        self._settings = settings

    def definition(self) -> ServiceDefinitionData:
        """返回不可编辑的订单服务身份与固定调查入口。"""
        return ServiceDefinitionData(
            id=ORDER_SERVICE_ID,
            title="订单服务靶场",
            kind="postgres_orders_demo",
            supported_investigations=(
                ServiceInvestigationData(
                    id=ORDERS_SLOW_QUERY_INTENT_ID,
                    title="调查订单慢查询",
                    description="针对订单服务的固定慢查询场景收集受控 DB、日志和服务证据。",
                    default_query=ORDERS_SLOW_QUERY_DEFAULT_QUERY,
                ),
            ),
            action_boundary="仅当调查确认固定根因后，才可提出需人工审批和二次确认的固定修复。",
            session_title=ORDER_SERVICE_SESSION_TITLE,
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前有限快照；任何 target 读取失败均以受控状态表达。"""
        if self._mode is ServiceMode.DISABLED:
            return _not_configured_snapshot()
        if self._mode is ServiceMode.MOCK:
            return _mock_snapshot()
        if self._settings is None:
            return _unavailable_snapshot()

        server_snapshot = _read_server_snapshot(self._settings)
        database_snapshot = _read_database_snapshot(self._settings)
        return _target_snapshot(server_snapshot, database_snapshot)


def _read_server_snapshot(settings: DemoOrdersEvidenceSettings) -> ServerEvidenceSnapshot | None:
    """读取固定 health/metrics，拒绝把下游错误文本带出 Connector。"""
    try:
        return OrderServiceEvidenceReader(HttpDemoOrdersServiceClient(settings)).collect()
    except DemoOrdersSourceError:
        return None


def _read_database_snapshot(settings: DemoOrdersEvidenceSettings) -> DatabaseEvidenceSnapshot | None:
    """读取固定当前库、索引和计划，不调用日志、probe 或执行器。"""
    try:
        return PostgresEvidenceReader(PostgresDemoOrdersDatabaseClient(settings)).collect()
    except DemoOrdersSourceError:
        return None


def _not_configured_snapshot() -> ServiceSnapshotData:
    """disabled 模式不读取外部来源，明确返回未配置状态。"""
    return ServiceSnapshotData(
        observed_at=datetime.now(timezone.utc),
        mode=ServiceMode.DISABLED,
        availability=ServiceAvailability.NOT_CONFIGURED,
        performance_signal=PerformanceSignal.NOT_CONFIGURED,
        server_metrics=ServiceServerMetricsData(source_status=ServiceSourceStatus.NOT_CONFIGURED),
        database=ServiceDatabaseStateData(
            source_status=ServiceSourceStatus.NOT_CONFIGURED,
            signal=DatabaseSignal.NOT_CONFIGURED,
        ),
    )


def _mock_snapshot() -> ServiceSnapshotData:
    """提供确定性降级 mock，明确不代表真实 target 当前状态。"""
    return ServiceSnapshotData(
        observed_at=datetime.now(timezone.utc),
        mode=ServiceMode.MOCK,
        availability=ServiceAvailability.HEALTHY,
        performance_signal=PerformanceSignal.SLOW_QUERY_DETECTED,
        server_metrics=ServiceServerMetricsData(
            source_status=ServiceSourceStatus.AVAILABLE,
            window_size=12,
            p50_ms=82.0,
            p95_ms=210.0,
            slow_query_count=10,
            timeout_count=0,
        ),
        database=ServiceDatabaseStateData(
            source_status=ServiceSourceStatus.AVAILABLE,
            signal=DatabaseSignal.MISSING_INDEX_SEQ_SCAN_DETECTED,
        ),
    )


def _unavailable_snapshot() -> ServiceSnapshotData:
    """target 配置或两个来源不可用时不回退 mock。"""
    return ServiceSnapshotData(
        observed_at=datetime.now(timezone.utc),
        mode=ServiceMode.TARGET,
        availability=ServiceAvailability.UNAVAILABLE,
        performance_signal=PerformanceSignal.UNAVAILABLE,
        server_metrics=ServiceServerMetricsData(source_status=ServiceSourceStatus.UNAVAILABLE),
        database=ServiceDatabaseStateData(
            source_status=ServiceSourceStatus.UNAVAILABLE,
            signal=DatabaseSignal.UNAVAILABLE,
        ),
    )


def _target_snapshot(
    server_snapshot: ServerEvidenceSnapshot | None,
    database_snapshot: DatabaseEvidenceSnapshot | None,
) -> ServiceSnapshotData:
    """根据 P4.3 固定规则组合两个独立受控来源。"""
    server_metrics = _server_metrics(server_snapshot)
    database = _database_state(database_snapshot)
    return ServiceSnapshotData(
        observed_at=datetime.now(timezone.utc),
        mode=ServiceMode.TARGET,
        availability=_availability(server_snapshot),
        performance_signal=_performance_signal(server_snapshot, database.signal),
        server_metrics=server_metrics,
        database=database,
    )


def _server_metrics(snapshot: ServerEvidenceSnapshot | None) -> ServiceServerMetricsData:
    """把 P4.1 服务事实映射为 P4.3 有限指标。"""
    if snapshot is None:
        return ServiceServerMetricsData(source_status=ServiceSourceStatus.UNAVAILABLE)
    return ServiceServerMetricsData(
        source_status=ServiceSourceStatus.AVAILABLE,
        window_size=snapshot.window_size,
        p50_ms=snapshot.p50_ms,
        p95_ms=snapshot.p95_ms,
        slow_query_count=snapshot.slow_query_count,
        timeout_count=snapshot.timeout_count,
    )


def _database_state(snapshot: DatabaseEvidenceSnapshot | None) -> ServiceDatabaseStateData:
    """从固定索引/计划事实生成确定的高层数据库状态。"""
    if snapshot is None:
        return ServiceDatabaseStateData(
            source_status=ServiceSourceStatus.UNAVAILABLE,
            signal=DatabaseSignal.UNAVAILABLE,
        )
    if (
        snapshot.target_database_confirmed
        and not snapshot.target_index_exists
        and snapshot.plan_uses_seq_scan
    ):
        signal = DatabaseSignal.MISSING_INDEX_SEQ_SCAN_DETECTED
    elif (
        snapshot.target_database_confirmed
        and snapshot.target_index_exists
        and snapshot.plan_uses_target_index
    ):
        signal = DatabaseSignal.INDEX_AND_PLAN_CONFIRMED
    else:
        signal = DatabaseSignal.INSUFFICIENT_DATA
    return ServiceDatabaseStateData(source_status=ServiceSourceStatus.AVAILABLE, signal=signal)


def _availability(snapshot: ServerEvidenceSnapshot | None) -> ServiceAvailability:
    """仅依据可读 health 响应表达服务可用性。"""
    if snapshot is None:
        return ServiceAvailability.UNAVAILABLE
    return ServiceAvailability.HEALTHY if snapshot.service_healthy else ServiceAvailability.UNHEALTHY


def _performance_signal(
    server_snapshot: ServerEvidenceSnapshot | None,
    database_signal: DatabaseSignal,
) -> PerformanceSignal:
    """严格按设计中数据库与服务指标的共同规则表达性能信号。"""
    if server_snapshot is None and database_signal is DatabaseSignal.UNAVAILABLE:
        return PerformanceSignal.UNAVAILABLE
    if server_snapshot is None or database_signal is DatabaseSignal.UNAVAILABLE:
        return PerformanceSignal.INSUFFICIENT_DATA
    has_anomaly = server_snapshot.slow_query_count > 0 or server_snapshot.timeout_count > 0
    if database_signal is DatabaseSignal.MISSING_INDEX_SEQ_SCAN_DETECTED and has_anomaly:
        return PerformanceSignal.SLOW_QUERY_DETECTED
    if (
        database_signal is DatabaseSignal.INDEX_AND_PLAN_CONFIRMED
        and server_snapshot.window_size > 0
        and server_snapshot.slow_query_count == 0
        and server_snapshot.timeout_count == 0
    ):
        return PerformanceSignal.NO_SLOW_QUERY_DETECTED
    return PerformanceSignal.INSUFFICIENT_DATA
