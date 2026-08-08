"""P7 监控概览应用服务单元测试（S1）。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application.monitoring import MonitorOverviewApplicationService
from src.domain.monitoring import MonitorHistoryStatus, ServiceMonitorSampleData
from src.domain.services import (
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceDatabaseStateData,
    ServiceDefinitionData,
    ServiceMode,
    ServiceRegistry,
    ServiceServerMetricsData,
    ServiceSnapshotData,
    ServiceSourceStatus,
)
from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository


def _sample(
    service_id: str,
    observed_at: datetime,
    *,
    slow: int | None = 0,
    timeout: int | None = 0,
    availability: ServiceAvailability = ServiceAvailability.HEALTHY,
    source_status: ServiceSourceStatus = ServiceSourceStatus.AVAILABLE,
    slowlog: int | None = None,
) -> ServiceMonitorSampleData:
    return ServiceMonitorSampleData(
        service_id=service_id,
        observed_at=observed_at,
        availability=availability,
        p50_ms=10.0 if source_status is ServiceSourceStatus.AVAILABLE else None,
        p95_ms=20.0 if source_status is ServiceSourceStatus.AVAILABLE else None,
        slow_query_count=slow if source_status is ServiceSourceStatus.AVAILABLE else None,
        timeout_count=timeout if source_status is ServiceSourceStatus.AVAILABLE else None,
        slowlog_count=slowlog,
        performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
        source_status=source_status,
    )


def _not_configured_sample(service_id: str, observed_at: datetime) -> ServiceMonitorSampleData:
    """构造未配置状态样本：所有指标标量必须为 null，不得用 0 代替缺失。"""
    return ServiceMonitorSampleData(
        service_id=service_id,
        observed_at=observed_at,
        availability=ServiceAvailability.NOT_CONFIGURED,
        performance_signal=PerformanceSignal.NOT_CONFIGURED,
        source_status=ServiceSourceStatus.NOT_CONFIGURED,
    )


def _unavailable_sample(service_id: str, observed_at: datetime) -> ServiceMonitorSampleData:
    """构造不可用状态样本：不保存异常详情，指标标量保持 null。"""
    return ServiceMonitorSampleData(
        service_id=service_id,
        observed_at=observed_at,
        availability=ServiceAvailability.UNAVAILABLE,
        performance_signal=PerformanceSignal.UNAVAILABLE,
        source_status=ServiceSourceStatus.UNAVAILABLE,
    )


class _StubConnector:
    """静态注册表最小只读 Connector 桩，不触发任何外部连接。"""

    def __init__(self, service_id: str, kind: str = "postgres") -> None:
        self._definition = ServiceDefinitionData(
            id=service_id,
            title=f"{service_id} 标题",
            kind=kind,
            supported_investigations=(),
            action_boundary="只读",
            session_title=service_id,
        )

    def definition(self) -> ServiceDefinitionData:
        return self._definition

    def health_snapshot(self) -> ServiceSnapshotData:
        raise AssertionError("概览路径不得调用 health_snapshot（不触发目标连接）。")


def _build_service(
    session_factory,
    registry: ServiceRegistry,
    sample_interval_seconds: int = 300,
    retention_hours: int = 24,
) -> MonitorOverviewApplicationService:
    return MonitorOverviewApplicationService(
        session_factory=session_factory,
        registry=registry,
        sample_interval_seconds=sample_interval_seconds,
        retention_hours=retention_hours,
    )


def test_概览返回全部注册服务且按注册顺序() -> None:
    """AC1：概览覆盖全部已注册服务，无未注册服务混入。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry(
        (_StubConnector("postgres-production"), _StubConnector("redis-production", kind="redis"))
    )
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=5)))
        repository.add(_sample("redis-production", now - timedelta(minutes=5)))
        session.commit()

    service = _build_service(session_factory, registry)
    overview = service.get_overview()

    assert [item.service_id for item in overview.items] == ["postgres-production", "redis-production"]
    assert overview.source == "scheduled_sampling"
    assert overview.sample_interval_seconds == 300
    assert overview.retention_hours == 24


def test_概览展示最新样本标量() -> None:
    """AC2：每个服务展示最新快照标量，null 保持 null，不伪造。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("postgres-production"),))
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=10), slow=0))
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=3, timeout=1))
        session.commit()

    overview = _build_service(session_factory, registry).get_overview()

    item = overview.items[0]
    assert item.connection_status is MonitorHistoryStatus.AVAILABLE
    assert item.latest_sample is not None
    assert item.latest_sample.observed_at == now - timedelta(minutes=5)
    assert item.latest_sample.slow_query_count == 3
    assert item.latest_sample.timeout_count == 1
    assert item.latest_sample.p50_ms == 10.0


def test_概览异常计数与p5一致() -> None:
    """AC6：异常采样点计数覆盖慢查询、超时与可用性状态变化。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("postgres-production"),))
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(minutes=20)))
        repository.add(_sample("postgres-production", now - timedelta(minutes=15), slow=1))
        repository.add(
            _sample(
                "postgres-production",
                now - timedelta(minutes=10),
                availability=ServiceAvailability.UNHEALTHY,
            )
        )
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=0))
        session.commit()

    overview = _build_service(session_factory, registry).get_overview()

    item = overview.items[0]
    assert item.trend_summary.sample_count == 4
    # 15 分钟慢查询 1 处 + 10 分钟可用性状态变化 1 处 + 5 分钟恢复状态变化 1 处 = 3 处异常
    # （P5 规则：任一样本 availability 与前一个不同即计为异常，含恢复）。
    assert item.trend_summary.anomaly_sample_count == 3


def test_redis异常计数按慢日志() -> None:
    """AC6：Redis 服务异常采样点按 slowlog_count>0 判定。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("redis-production", kind="redis"),))
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("redis-production", now - timedelta(minutes=10)))
        repository.add(_sample("redis-production", now - timedelta(minutes=5), slowlog=2))
        session.commit()

    overview = _build_service(session_factory, registry).get_overview()

    item = overview.items[0]
    assert item.trend_summary.sample_count == 2
    assert item.trend_summary.anomaly_sample_count == 1


def test_无样本返回未采样诚实空态() -> None:
    """AC3：无历史样本 → not_sampled，latest_sample 为 null。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("fresh-service"),))

    overview = _build_service(session_factory, registry).get_overview()

    item = overview.items[0]
    assert item.connection_status is MonitorHistoryStatus.NOT_SAMPLED
    assert item.latest_sample is None
    assert item.availability is ServiceAvailability.UNAVAILABLE
    assert item.trend_summary.sample_count == 0


def test_未配置服务显示未配置() -> None:
    """AC4：最新样本为 not_configured → 未配置，不显示伪造数值。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("unconfigured-service"),))
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_not_configured_sample("unconfigured-service", now - timedelta(minutes=5)))
        session.commit()

    overview = _build_service(session_factory, registry).get_overview()

    item = overview.items[0]
    assert item.connection_status is MonitorHistoryStatus.NOT_CONFIGURED
    assert item.latest_sample is not None
    assert item.latest_sample.p50_ms is None
    assert item.trend_summary.sample_count == 0


def test_不可用服务显示不可用() -> None:
    """AC4：最新样本为 unavailable → 不可用，标量 null。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("flaky-service"),))
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_unavailable_sample("flaky-service", now - timedelta(minutes=5)))
        session.commit()

    overview = _build_service(session_factory, registry).get_overview()

    item = overview.items[0]
    assert item.connection_status is MonitorHistoryStatus.UNAVAILABLE
    assert item.latest_sample is not None
    assert item.latest_sample.p95_ms is None
    assert item.latest_sample.slow_query_count is None


def test_单服务失败不影响其他服务(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC4：单个服务样本读取失败只将该服务降级，不阻塞整体概览。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("ok-service"), _StubConnector("broken-service")))
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("ok-service", now - timedelta(minutes=5)))
        session.commit()

    import src.application.monitoring as monitoring_module

    real_list_between = monitoring_module.SqlAlchemyMonitorSampleRepository.list_between

    def _raise_for_broken(self, service_id: str, from_at, to_at):
        if service_id == "broken-service":
            raise RuntimeError("样本读取失败")
        return real_list_between(self, service_id, from_at, to_at)

    monkeypatch.setattr(
        monitoring_module.SqlAlchemyMonitorSampleRepository,
        "list_between",
        _raise_for_broken,
    )
    try:
        overview = _build_service(session_factory, registry).get_overview()
    finally:
        monkeypatch.undo()

    assert [item.service_id for item in overview.items] == ["ok-service", "broken-service"]
    ok_item = next(item for item in overview.items if item.service_id == "ok-service")
    assert ok_item.connection_status is MonitorHistoryStatus.AVAILABLE
    broken_item = next(item for item in overview.items if item.service_id == "broken-service")
    assert broken_item.connection_status is MonitorHistoryStatus.UNAVAILABLE
    assert broken_item.latest_sample is None
