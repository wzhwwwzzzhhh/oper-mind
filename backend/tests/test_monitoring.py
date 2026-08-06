"""P5 历史监控采样器与样本持久化测试。"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from src.domain.services import (
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceDatabaseStateData,
    ServiceDefinitionData,
    ServiceMode,
    ServiceServerMetricsData,
    ServiceSnapshotData,
    ServiceSourceStatus,
)
from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.models import ServiceMonitorSampleRecord
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository
from src.infrastructure.monitoring.sampler import MonitorSampler


def _snapshot(
    *,
    availability: ServiceAvailability = ServiceAvailability.HEALTHY,
    source_status: ServiceSourceStatus = ServiceSourceStatus.AVAILABLE,
) -> ServiceSnapshotData:
    observed_at = datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc)
    return ServiceSnapshotData(
        observed_at=observed_at,
        mode=ServiceMode.TARGET,
        availability=availability,
        performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
        server_metrics=ServiceServerMetricsData(
            source_status=source_status,
            window_size=60,
            p50_ms=12.5 if source_status is ServiceSourceStatus.AVAILABLE else None,
            p95_ms=28.0 if source_status is ServiceSourceStatus.AVAILABLE else None,
            slow_query_count=0 if source_status is ServiceSourceStatus.AVAILABLE else None,
            timeout_count=0 if source_status is ServiceSourceStatus.AVAILABLE else None,
        ),
        database=ServiceDatabaseStateData(
            source_status=source_status,
            signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED
            if source_status is ServiceSourceStatus.AVAILABLE
            else DatabaseSignal.UNAVAILABLE,
        ),
    )


class _Connector:
    def __init__(self, service_id: str, snapshot: ServiceSnapshotData | None = None, error: Exception | None = None) -> None:
        self._definition = ServiceDefinitionData(
            id=service_id,
            title=service_id,
            kind="postgres",
            supported_investigations=(),
            action_boundary="只读",
            session_title=service_id,
        )
        self._snapshot = snapshot
        self._error = error

    def definition(self) -> ServiceDefinitionData:
        return self._definition

    def health_snapshot(self) -> ServiceSnapshotData:
        if self._error:
            raise self._error
        assert self._snapshot is not None
        return self._snapshot


def test_采样器写入脱敏样本并隔离单服务失败() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    sampler = MonitorSampler(
        session_factory=session_factory,
        connectors=(
            _Connector("healthy", _snapshot()),
            _Connector("failed", error=TimeoutError("secret dsn and raw sql must not escape")),
        ),
        retention_hours=24,
    )

    results = sampler.sample_once()

    assert [result.source_status.value for result in results] == ["available", "unavailable"]
    with session_factory() as session:
        records = list(session.scalars(select(ServiceMonitorSampleRecord).order_by(ServiceMonitorSampleRecord.service_id)))
    assert len(records) == 2
    healthy = next(record for record in records if record.service_id == "healthy")
    failed = next(record for record in records if record.service_id == "failed")
    assert healthy.p95_ms == 28.0
    assert failed.availability == "unavailable"
    assert failed.p95_ms is None
    assert "secret" not in repr(failed.__dict__)


def test_采样器保存未配置状态而不伪造指标() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    sampler = MonitorSampler(
        session_factory=session_factory,
        connectors=(_Connector("missing", _snapshot(availability=ServiceAvailability.NOT_CONFIGURED, source_status=ServiceSourceStatus.NOT_CONFIGURED)),),
        retention_hours=24,
    )

    sampler.sample_once()

    with session_factory() as session:
        record = session.scalar(select(ServiceMonitorSampleRecord))
    assert record is not None
    assert record.source_status == "not_configured"
    assert record.p50_ms is None
    assert record.slow_query_count is None
