"""P5 历史监控采样器与样本持久化测试。"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, inspect, select
from sqlalchemy.orm import sessionmaker

from src.domain.host_metrics import (
    HostMetricsCollector,
    HostMetricsData,
    HostMetricsMode,
    HostMetricsSourceStatus,
)
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
from src.infrastructure.persistence.database import Base, create_app_engine
from src.infrastructure.persistence.models import ServiceMonitorSampleRecord
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository
from src.infrastructure.monitoring.sampler import MonitorSampler
from src.project_paths import BACKEND_ROOT


def _snapshot(
    *,
    availability: ServiceAvailability = ServiceAvailability.HEALTHY,
    source_status: ServiceSourceStatus = ServiceSourceStatus.AVAILABLE,
) -> ServiceSnapshotData:
    observed_at = datetime.now(timezone.utc)
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


def test_采样器持久化redis专用标量而pg语义字段为null() -> None:
    """Redis 快照的专用标量落库，PG 语义字段保持 null，不冒充数据库延迟。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    snapshot = ServiceSnapshotData(
        observed_at=datetime.now(timezone.utc),
        mode=ServiceMode.TARGET,
        availability=ServiceAvailability.HEALTHY,
        performance_signal=PerformanceSignal.SLOW_QUERY_DETECTED,
        server_metrics=ServiceServerMetricsData(
            source_status=ServiceSourceStatus.AVAILABLE,
            memory_bytes=1048576,
            client_connections=5,
            slowlog_count=2,
        ),
        database=ServiceDatabaseStateData(
            source_status=ServiceSourceStatus.AVAILABLE,
            signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
        ),
    )
    sampler = MonitorSampler(
        session_factory=session_factory,
        connectors=(_Connector("redis-production", snapshot),),
        retention_hours=24,
    )

    results = sampler.sample_once()

    assert results[0].service_id == "redis-production"
    assert results[0].memory_bytes == 1048576
    assert results[0].client_connections == 5
    assert results[0].slowlog_count == 2
    assert results[0].p50_ms is None
    assert results[0].slow_query_count is None
    with session_factory() as session:
        record = session.scalar(select(ServiceMonitorSampleRecord))
    assert record is not None
    assert record.service_id == "redis-production"
    assert record.memory_bytes == 1048576
    assert record.client_connections == 5
    assert record.slowlog_count == 2
    assert record.p50_ms is None
    assert record.p95_ms is None
    assert record.slow_query_count is None
    assert record.timeout_count is None


def _run_alembic(database_path: Path, command: list[str]) -> subprocess.CompletedProcess[str]:
    """在临时目录运行 alembic，模拟独立部署迁移环境。"""
    env = os.environ.copy()
    env.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(BACKEND_ROOT / "alembic.ini"), *command],
        cwd=database_path.parent,
        env=env,
        check=False,
        capture_output=True,
        text=True,
    )


def test_p6_redis标量迁移升降级(tmp_path: Path) -> None:
    """Redis 专用标量迁移 upgrade 增加三列，downgrade 移除，既有 PG 样本不受影响。"""
    database_path = tmp_path / "p6-redis.sqlite3"
    result = _run_alembic(database_path, ["upgrade", "head"])
    assert result.returncode == 0, result.stderr

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        columns = {item["name"] for item in inspector.get_columns("service_monitor_samples")}
        assert {"memory_bytes", "client_connections", "slowlog_count"} <= columns
        constraint_text = "\n".join(
            str(item["sqltext"]) for item in inspector.get_check_constraints("service_monitor_samples")
        )
        assert "memory_bytes" in constraint_text
        assert "client_connections" in constraint_text
        assert "slowlog_count" in constraint_text
    finally:
        engine.dispose()

    result = _run_alembic(database_path, ["downgrade", "20260807_05_p5_monitor_samples"])
    assert result.returncode == 0, result.stderr
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        columns = {item["name"] for item in inspect(engine).get_columns("service_monitor_samples")}
        assert "memory_bytes" not in columns
        assert "client_connections" not in columns
        assert "slowlog_count" not in columns
    finally:
        engine.dispose()

    result = _run_alembic(database_path, ["upgrade", "head"])
    assert result.returncode == 0, result.stderr


class _FakeHostCollector:
    """确定性主机采集器，用于采样器附加主机字段测试。"""

    def __init__(self, data: HostMetricsData | None = None, error: Exception | None = None) -> None:
        self._data = data
        self._error = error

    def collect(self) -> HostMetricsData:
        if self._error:
            raise self._error
        assert self._data is not None
        return self._data


def _host_metrics() -> HostMetricsData:
    """构造一个 available 的主机指标样例。"""
    return HostMetricsData(
        mode=HostMetricsMode.TARGET,
        source_status=HostMetricsSourceStatus.AVAILABLE,
        observed_at=datetime(2026, 8, 5, 12, 0, tzinfo=timezone.utc),
        cpu_percent=42.5,
        memory_percent=61.0,
        memory_used_bytes=10 * 1024**3,
        disk_used_percent=70.0,
    )


def test_采样器附加主机标量到每个样本() -> None:
    """AC3：采样器每轮一次采集主机指标并写入各服务样本。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    sampler = MonitorSampler(
        session_factory=session_factory,
        connectors=(
            _Connector("a", _snapshot()),
            _Connector("b", _snapshot()),
        ),
        retention_hours=24,
        host_collector=_FakeHostCollector(_host_metrics()),
    )

    results = sampler.sample_once()

    assert [result.host_cpu_percent for result in results] == [42.5, 42.5]
    assert [result.host_memory_percent for result in results] == [61.0, 61.0]
    assert [result.host_memory_bytes for result in results] == [10 * 1024**3, 10 * 1024**3]
    assert [result.host_disk_used_percent for result in results] == [70.0, 70.0]
    with session_factory() as session:
        records = list(session.scalars(select(ServiceMonitorSampleRecord).order_by(ServiceMonitorSampleRecord.service_id)))
    assert len(records) == 2
    assert all(record.host_cpu_percent == 42.5 for record in records)
    assert all(record.host_disk_used_percent == 70.0 for record in records)


def test_主机采集失败只置null不改服务状态() -> None:
    """硬约束：主机失败仅主机字段为 null，服务 availability/source_status 不受影响。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    sampler = MonitorSampler(
        session_factory=session_factory,
        connectors=(_Connector("healthy", _snapshot()),),
        retention_hours=24,
        host_collector=_FakeHostCollector(error=TimeoutError("主机采集超时")),
    )

    results = sampler.sample_once()

    assert results[0].availability is ServiceAvailability.HEALTHY
    assert results[0].source_status is ServiceSourceStatus.AVAILABLE
    assert results[0].host_cpu_percent is None
    assert results[0].host_memory_percent is None
    assert results[0].host_disk_used_percent is None
    with session_factory() as session:
        record = session.scalar(select(ServiceMonitorSampleRecord))
    assert record is not None
    assert record.availability == "healthy"
    assert record.source_status == "available"
    assert record.host_cpu_percent is None


def test_主机采集器未装配时主机字段为null() -> None:
    """未注入 host_collector 时样本主机字段保持 null（既有行为不变）。"""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    sampler = MonitorSampler(
        session_factory=session_factory,
        connectors=(_Connector("a", _snapshot()),),
        retention_hours=24,
    )

    results = sampler.sample_once()

    assert results[0].host_cpu_percent is None
    assert results[0].host_memory_bytes is None


def test_异步采样路径附加主机指标(tmp_path: Path) -> None:
    """异步采样路径同样附加主机标量（覆盖 3s 超时包装）。"""
    engine = create_engine(f"sqlite:///{tmp_path / 'async-sampler.sqlite3'}")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, expire_on_commit=False)
    sampler = MonitorSampler(
        session_factory=session_factory,
        connectors=(
            _Connector("a", _snapshot()),
            _Connector("b", _snapshot()),
        ),
        retention_hours=24,
        host_collector=_FakeHostCollector(_host_metrics()),
    )

    results = asyncio.run(sampler.sample_once_async())

    assert [result.host_cpu_percent for result in results] == [42.5, 42.5]
    assert [result.host_disk_used_percent for result in results] == [70.0, 70.0]
    with session_factory() as session:
        records = list(session.scalars(select(ServiceMonitorSampleRecord).order_by(ServiceMonitorSampleRecord.service_id)))
    assert len(records) == 2
    assert all(record.host_cpu_percent == 42.5 for record in records)


def test_p6_主机指标迁移升降级(tmp_path: Path) -> None:
    """P6 主机指标迁移 upgrade 增加四列，downgrade 移除，既有 PG/Redis 样本不受影响。"""
    database_path = tmp_path / "p6-host-metrics.sqlite3"
    result = _run_alembic(database_path, ["upgrade", "head"])
    assert result.returncode == 0, result.stderr

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        inspector = inspect(engine)
        columns = {item["name"] for item in inspector.get_columns("service_monitor_samples")}
        assert {"host_cpu_percent", "host_memory_percent", "host_memory_bytes", "host_disk_used_percent"} <= columns
        constraint_text = "\n".join(
            str(item["sqltext"]) for item in inspector.get_check_constraints("service_monitor_samples")
        )
        assert "host_cpu_percent" in constraint_text
        assert "host_disk_used_percent" in constraint_text
    finally:
        engine.dispose()

    result = _run_alembic(database_path, ["downgrade", "20260807_06_p6_redis_monitor_metrics"])
    assert result.returncode == 0, result.stderr
    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        columns = {item["name"] for item in inspect(engine).get_columns("service_monitor_samples")}
        assert "host_cpu_percent" not in columns
        assert "host_memory_bytes" not in columns
        assert "host_disk_used_percent" not in columns
    finally:
        engine.dispose()

    result = _run_alembic(database_path, ["upgrade", "head"])
    assert result.returncode == 0, result.stderr
