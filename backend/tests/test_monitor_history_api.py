"""P5 历史趋势查询 API 测试。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application.monitoring import MonitorHistoryApplicationService
from src.domain.monitoring import ServiceMonitorSampleData
from src.domain.services import PerformanceSignal, ServiceAvailability, ServiceSourceStatus
from src.infrastructure.persistence.database import Base
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository


def _sample(service_id: str, observed_at: datetime, *, slow: int | None = 0) -> ServiceMonitorSampleData:
    return ServiceMonitorSampleData(
        service_id=service_id,
        observed_at=observed_at,
        availability=ServiceAvailability.HEALTHY,
        p50_ms=10.0,
        p95_ms=20.0,
        slow_query_count=slow,
        timeout_count=0,
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
