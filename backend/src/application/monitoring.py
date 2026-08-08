"""P5 历史监控查询应用服务。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.domain.monitoring import MonitorHistoryData, MonitorHistoryStatus
from src.domain.services import ServiceRegistry, ServiceSourceStatus
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository


class MonitorHistoryApplicationService:
    """校验静态服务边界并查询历史样本。"""

    def __init__(
        self,
        session_factory: SessionFactory,
        registry: ServiceRegistry,
        sample_interval_seconds: int,
        retention_hours: int,
        query_max_hours: int,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._sample_interval_seconds = sample_interval_seconds
        self._retention_hours = retention_hours
        self._query_max_hours = query_max_hours

    def get_history(
        self,
        service_id: str,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        hours: int | None = None,
    ) -> MonitorHistoryData:
        """读取固定窗口的历史样本，不触发目标服务连接。"""
        if self._registry.get_connector(service_id) is None:
            raise ValueError("SERVICE_NOT_FOUND")
        start, end = _window(from_at, to_at, hours, self._query_max_hours)
        session = self._session_factory()
        try:
            samples = tuple(SqlAlchemyMonitorSampleRepository(session).list_between(service_id, start, end))
        finally:
            session.close()
        if not samples:
            status = MonitorHistoryStatus.NOT_SAMPLED
        elif all(sample.source_status is ServiceSourceStatus.NOT_CONFIGURED for sample in samples):
            # 未配置服务不产生有效历史数据：如实返回空序列 + 未配置状态，避免把空标量画成"看似有数据"的趋势。
            status = MonitorHistoryStatus.NOT_CONFIGURED
            samples = ()
        elif any(sample.source_status is ServiceSourceStatus.AVAILABLE for sample in samples):
            status = MonitorHistoryStatus.AVAILABLE
            # 过滤未配置的空标量样本，只返回真实采样点。
            samples = tuple(sample for sample in samples if sample.source_status is not ServiceSourceStatus.NOT_CONFIGURED)
        else:
            status = MonitorHistoryStatus.UNAVAILABLE
            samples = tuple(sample for sample in samples if sample.source_status is not ServiceSourceStatus.NOT_CONFIGURED)
        return MonitorHistoryData(
            service_id=service_id,
            status=status,
            sample_interval_seconds=self._sample_interval_seconds,
            retention_hours=self._retention_hours,
            from_at=start,
            to_at=end,
            samples=samples,
        )


def _window(
    from_at: datetime | None,
    to_at: datetime | None,
    hours: int | None,
    max_hours: int,
) -> tuple[datetime, datetime]:
    """规范化 UTC 窗口并限制最大范围。"""
    now = datetime.now(timezone.utc)
    if hours is not None and (from_at is not None or to_at is not None):
        raise ValueError("WINDOW_CONFLICT")
    if hours is not None:
        if hours < 1 or hours > max_hours:
            raise ValueError("WINDOW_TOO_LARGE")
        return now - timedelta(hours=hours), now
    end = _as_utc(to_at) if to_at is not None else now
    start = _as_utc(from_at) if from_at is not None else end - timedelta(hours=max_hours)
    if start > end:
        raise ValueError("WINDOW_INVALID")
    if end - start > timedelta(hours=max_hours):
        raise ValueError("WINDOW_TOO_LARGE")
    return start, end


def _as_utc(value: datetime) -> datetime:
    """要求带时区的时间并统一为 UTC。"""
    if value.tzinfo is None:
        raise ValueError("WINDOW_INVALID")
    return value.astimezone(timezone.utc)
