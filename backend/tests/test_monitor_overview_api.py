"""P7 监控概览接口 API 契约测试（S2）。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.api.v1.dependencies import V1Services
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


@pytest.fixture
def overview_client(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> Iterator[TestClient]:
    """以临时 SQLite 与静态注册表装配 v1 API，供概览路由端到端测试。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'overview.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    registry = ServiceRegistry(
        (
            _StubConnector("postgres-production"),
            _StubConnector("unconfigured-service"),
            _StubConnector("redis-production", kind="redis"),
        )
    )

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
        repository.add(_sample("postgres-production", now - timedelta(minutes=5), slow=2))
        repository.add(
            _sample(
                "postgres-production",
                now - timedelta(minutes=10),
                slow=0,
                timeout=0,
            )
        )
        repository.add(_not_configured_sample("unconfigured-service", now - timedelta(minutes=5)))
        repository.add(_sample("redis-production", now - timedelta(minutes=5), slowlog=1))
        session.commit()

    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    engine.dispose()


def test_概览接口返回全部服务与诚实状态(overview_client: TestClient) -> None:
    """AC1/AC2/AC4：概览返回全部已注册服务，逐服务诚实状态，脱敏标量。"""
    response = overview_client.get("/api/v1/monitor/overview")

    assert response.status_code == 200
    body = response.json()
    assert body["source"] == "scheduled_sampling"
    assert body["sample_interval_seconds"] == 300
    assert body["retention_hours"] == 24
    assert [item["service_id"] for item in body["items"]] == [
        "postgres-production",
        "unconfigured-service",
        "redis-production",
    ]

    available = next(item for item in body["items"] if item["service_id"] == "postgres-production")
    assert available["connection_status"] == "available"
    assert available["availability"] == "healthy"
    assert available["latest_sample"] is not None
    assert available["latest_sample"]["slow_query_count"] == 2
    assert available["trend_summary"]["sample_count"] == 2
    assert available["trend_summary"]["anomaly_sample_count"] == 1

    not_configured = next(item for item in body["items"] if item["service_id"] == "unconfigured-service")
    assert not_configured["connection_status"] == "not_configured"
    assert not_configured["latest_sample"] is not None
    assert not_configured["latest_sample"]["p50_ms"] is None

    redis = next(item for item in body["items"] if item["service_id"] == "redis-production")
    assert redis["connection_status"] == "available"
    assert redis["trend_summary"]["anomaly_sample_count"] == 1


def test_概览接口返回request关联头(overview_client: TestClient) -> None:
    """概览响应携带 v1 request 关联头，便于前端诊断。"""
    response = overview_client.get("/api/v1/monitor/overview")

    assert response.status_code == 200
    assert response.headers.get("X-Request-Id")
    body = response.json()
    assert body["meta"]["request_id"] == response.headers.get("X-Request-Id")


def test_概览接口脱敏不泄露敏感字段(overview_client: TestClient) -> None:
    """AC8：概览响应不含 SQL、对象名、用户名、IP 或凭据字段。"""
    response = overview_client.get("/api/v1/monitor/overview")

    assert response.status_code == 200
    raw = response.text
    for sensitive in ("password", "DSN", "dsn=", "sk-", "sql=", "SELECT", "username"):
        assert sensitive.lower() not in raw.lower()


def test_概览接口读库超时返回内部错误(overview_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """概览读库限时（复用网关超时模式）：超时返回 INTERNAL_ERROR，不挂起请求。"""
    import time

    from src.application import monitoring as monitoring_module
    from src.api.v1 import routes as routes_module

    original = monitoring_module.MonitorOverviewApplicationService.get_overview

    def _slow_overview(self):
        time.sleep(0.5)
        return original(self)

    monkeypatch.setattr(routes_module, "OVERVIEW_READ_TIMEOUT_SECONDS", 0.05)
    monkeypatch.setattr(
        monitoring_module.MonitorOverviewApplicationService,
        "get_overview",
        _slow_overview,
    )

    response = overview_client.get("/api/v1/monitor/overview")

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
