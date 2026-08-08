"""P5 历史趋势查询 API 测试。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.v1.dependencies import V1Services
from src.application.monitoring import MonitorHistoryApplicationService
from src.domain.monitoring import ServiceMonitorSampleData
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
    host_cpu_percent: float | None = None,
    host_memory_percent: float | None = None,
    host_memory_bytes: int | None = None,
    host_disk_used_percent: float | None = None,
) -> ServiceMonitorSampleData:
    return ServiceMonitorSampleData(
        service_id=service_id,
        observed_at=observed_at,
        availability=ServiceAvailability.HEALTHY,
        p50_ms=10.0,
        p95_ms=20.0,
        slow_query_count=slow,
        timeout_count=0,
        host_cpu_percent=host_cpu_percent,
        host_memory_percent=host_memory_percent,
        host_memory_bytes=host_memory_bytes,
        host_disk_used_percent=host_disk_used_percent,
        performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
        source_status=ServiceSourceStatus.AVAILABLE,
    )


class _Registry:
    def __init__(self, service_ids: tuple[str, ...]) -> None:
        self._service_ids = frozenset(service_ids)

    def get_connector(self, service_id: str) -> object | None:
        return object() if service_id in self._service_ids else None


def test_历史查询按时间升序并限制窗口() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_sample("postgres-production", now - timedelta(hours=2)))
        repository.add(_sample("postgres-production", now - timedelta(hours=1), slow=2))
        session.commit()

    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("postgres-production",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("postgres-production", from_at=now - timedelta(hours=3), to_at=now)

    assert result.status.value == "available"
    assert [item.observed_at for item in result.samples] == [now - timedelta(hours=2), now - timedelta(hours=1)]
    assert result.samples[-1].slow_query_count == 2


def test_历史样本携带主机标量() -> None:
    """AC3：样本主机标量经历史查询透出，null 保持 null。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(
            _sample(
                "postgres-production",
                now,
                host_cpu_percent=42.5,
                host_memory_percent=61.0,
                host_memory_bytes=10 * 1024**3,
                host_disk_used_percent=70.0,
            )
        )
        repository.add(_sample("postgres-production", now - timedelta(minutes=5)))
        session.commit()

    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("postgres-production",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("postgres-production", from_at=now - timedelta(hours=1), to_at=now)

    host_sample = max(result.samples, key=lambda item: item.observed_at)
    assert host_sample.host_cpu_percent == 42.5
    assert host_sample.host_memory_percent == 61.0
    assert host_sample.host_memory_bytes == 10 * 1024**3
    assert host_sample.host_disk_used_percent == 70.0
    plain_sample = min(result.samples, key=lambda item: item.observed_at)
    assert plain_sample.host_cpu_percent is None
    assert plain_sample.host_memory_bytes is None


def test_未注册服务不会探测外部资源() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(()),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    try:
        service.get_history("unknown", from_at=None, to_at=None)
    except ValueError as error:
        assert str(error) == "SERVICE_NOT_FOUND"
    else:
        raise AssertionError("未注册服务必须被拒绝")


def test_redis样本经历史查询返回专用标量且pg字段为null() -> None:
    """Redis 历史样本携带专用标量返回，PG 语义字段保持 null。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    sample = ServiceMonitorSampleData(
        service_id="redis-production",
        observed_at=now,
        availability=ServiceAvailability.HEALTHY,
        memory_bytes=2048,
        client_connections=4,
        slowlog_count=1,
        performance_signal=PerformanceSignal.SLOW_QUERY_DETECTED,
        source_status=ServiceSourceStatus.AVAILABLE,
    )
    with session_factory() as session:
        SqlAlchemyMonitorSampleRepository(session).add(sample)
        session.commit()

    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("redis-production",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("redis-production", from_at=now - timedelta(hours=1), to_at=now + timedelta(minutes=1))

    assert result.status.value == "available"
    assert len(result.samples) == 1
    item = result.samples[0]
    assert item.memory_bytes == 2048
    assert item.client_connections == 4
    assert item.slowlog_count == 1
    assert item.p50_ms is None
    assert item.p95_ms is None
    assert item.slow_query_count is None
    assert item.timeout_count is None


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


def test_未配置服务历史查询返回空序列和未配置状态() -> None:
    """AC2：未配置服务不产生有效样本，查询返回空序列 + not_configured 诚实状态，不伪造数值。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_not_configured_sample("unconfigured-service", now - timedelta(minutes=10)))
        repository.add(_not_configured_sample("unconfigured-service", now - timedelta(minutes=5)))
        session.commit()

    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("unconfigured-service",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("unconfigured-service", from_at=now - timedelta(hours=1), to_at=now)

    assert result.status.value == "not_configured"
    assert result.samples == ()
    assert result.sample_interval_seconds == 300
    assert result.retention_hours == 24


def test_无历史样本返回未采样状态() -> None:
    """已注册但没有历史样本 → not_sampled 空序列。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("fresh-service",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("fresh-service", from_at=None, to_at=None)

    assert result.status.value == "not_sampled"
    assert result.samples == ()


def test_仅有不可用样本返回不可用状态但保留状态样本() -> None:
    """AC3：采样失败/超时样本记录为不可用状态，查询返回 unavailable，不暴露异常详情。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_unavailable_sample("flaky-service", now - timedelta(minutes=10)))
        repository.add(_unavailable_sample("flaky-service", now - timedelta(minutes=5)))
        session.commit()

    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("flaky-service",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("flaky-service", from_at=now - timedelta(hours=1), to_at=now)

    assert result.status.value == "unavailable"
    assert len(result.samples) == 2
    for item in result.samples:
        assert item.source_status.value == "unavailable"
        assert item.p95_ms is None
        assert item.slow_query_count is None


def test_混合状态无可用样本时如实标注不可用() -> None:
    """窗口内混合不可用与未配置且无可用样本时，不得谎报 available。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_unavailable_sample("mixed-service", now - timedelta(minutes=10)))
        repository.add(_not_configured_sample("mixed-service", now - timedelta(minutes=5)))
        session.commit()

    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("mixed-service",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("mixed-service", from_at=now - timedelta(hours=1), to_at=now)

    assert result.status.value == "unavailable"
    assert all(item.source_status.value != "not_configured" for item in result.samples)


def test_混合状态含可用样本时返回可用并过滤未配置样本() -> None:
    """窗口内存在可用样本 → available，未配置空标量样本不进入趋势序列。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime(2026, 8, 5, 12, tzinfo=timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_not_configured_sample("transitioning-service", now - timedelta(minutes=20)))
        repository.add(_sample("transitioning-service", now - timedelta(minutes=10), slow=1))
        session.commit()

    service = MonitorHistoryApplicationService(
        session_factory=session_factory,
        registry=_Registry(("transitioning-service",)),
        sample_interval_seconds=300,
        retention_hours=24,
        query_max_hours=24,
    )

    result = service.get_history("transitioning-service", from_at=now - timedelta(hours=1), to_at=now)

    assert result.status.value == "available"
    assert [item.observed_at for item in result.samples] == [now - timedelta(minutes=10)]
    assert result.samples[0].slow_query_count == 1


class _StubConnector:
    """静态注册表最小只读 Connector 桩，不触发任何外部连接。"""

    def __init__(self, service_id: str) -> None:
        self._definition = ServiceDefinitionData(
            id=service_id,
            title=service_id,
            kind="postgres",
            supported_investigations=(),
            action_boundary="只读",
            session_title=service_id,
        )

    def definition(self) -> ServiceDefinitionData:
        return self._definition

    def health_snapshot(self) -> ServiceSnapshotData:
        return ServiceSnapshotData(
            observed_at=datetime.now(timezone.utc),
            mode=ServiceMode.TARGET,
            availability=ServiceAvailability.NOT_CONFIGURED,
            performance_signal=PerformanceSignal.NOT_CONFIGURED,
            server_metrics=ServiceServerMetricsData(
                source_status=ServiceSourceStatus.NOT_CONFIGURED,
                window_size=None,
                p50_ms=None,
                p95_ms=None,
                slow_query_count=None,
                timeout_count=None,
            ),
            database=ServiceDatabaseStateData(
                source_status=ServiceSourceStatus.NOT_CONFIGURED,
                signal=DatabaseSignal.NOT_CONFIGURED,
            ),
        )


@pytest.fixture
def history_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Iterator[TestClient]:
    """以临时 SQLite 与静态注册表装配 v1 API，供历史路由端到端测试。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'history.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry((_StubConnector("postgres-production"),))

    from src.application.contracts import DiagnosisExecutionEvent, DiagnosisExecutionResult
    from src.application.services import RunApplicationService, SessionApplicationService
    from src.domain.diagnosis import RunEventType
    from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler

    class _DeterministicExecutor:
        """不访问真实 Agent、只输出一条安全事件的确定性执行器。"""

        def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
            yield DiagnosisExecutionEvent(
                type=RunEventType.ROUTE_DECIDED,
                node="route",
                occurred_at=datetime.now(timezone.utc),
            )
            yield DiagnosisExecutionResult(strategy="direct")

    services = V1Services(
        session_factory=session_factory,
        session_service=SessionApplicationService(session_factory, registry=registry),
        run_service=RunApplicationService(
            session_factory,
            _DeterministicExecutor(),
            ConservativeResultAssembler(),
        ),
        service_registry=registry,
    )

    now = datetime.now(timezone.utc)
    with session_factory() as session:
        repository = SqlAlchemyMonitorSampleRepository(session)
        repository.add(_not_configured_sample("postgres-production", now - timedelta(minutes=5)))
        session.commit()

    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    engine.dispose()


def test_历史接口对未配置服务返回空序列和未配置状态(history_client: TestClient) -> None:
    """AC2：HTTP 层对未配置服务返回 status=not_configured、samples=[]，不伪造数值。"""
    response = history_client.get("/api/v1/services/postgres-production/monitor/history")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_configured"
    assert body["samples"] == []
    assert body["source"] == "scheduled_sampling"
    assert body["sample_interval_seconds"] == 300
    assert body["retention_hours"] == 24


def test_历史接口对未注册服务返回404(history_client: TestClient) -> None:
    """AC4：未注册服务键直接 404，不探测外部资源。"""
    response = history_client.get("/api/v1/services/not-registered/monitor/history")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SERVICE_NOT_FOUND"


def test_历史接口拒绝超大窗口(history_client: TestClient) -> None:
    """非功能：窗口超出最大范围返回 422，避免一次性拉取过量历史。"""
    response = history_client.get(
        "/api/v1/services/postgres-production/monitor/history",
        params={"hours": 168},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
