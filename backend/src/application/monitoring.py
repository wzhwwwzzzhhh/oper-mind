"""P5 历史监控查询与 P7 监控概览应用服务。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from src.domain.monitoring import (
    MonitorHistoryData,
    MonitorHistoryStatus,
    MonitorOverviewData,
    MonitorServiceOverviewData,
    MonitorTrendSummaryData,
    ServiceMonitorSampleData,
)
from src.domain.services import (
    ServiceAvailability,
    ServiceConnector,
    ServiceDefinitionData,
    ServiceRegistry,
    ServiceSourceStatus,
)
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.monitor_repositories import SqlAlchemyMonitorSampleRepository

LOGGER = logging.getLogger(__name__)

OVERVIEW_READ_TIMEOUT_SECONDS = 3.0


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
    now = datetime.now(UTC)
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
    return value.astimezone(UTC)


class MonitorOverviewApplicationService:
    """P7 监控概览：按静态注册表聚合最新采样快照与趋势摘要，只读应用库、不触发目标连接。"""

    def __init__(
        self,
        session_factory: SessionFactory,
        registry: ServiceRegistry,
        sample_interval_seconds: int,
        retention_hours: int,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._sample_interval_seconds = sample_interval_seconds
        self._retention_hours = retention_hours

    def get_overview(self) -> MonitorOverviewData:
        """读取全部已注册服务的监控概览，按注册表顺序返回。

        单个服务样本读取失败只将该服务降级为不可用，不阻塞其他服务展示。
        """
        now = datetime.now(UTC)
        start = now - timedelta(hours=self._retention_hours)
        items = []
        for connector in self._registry.list_connectors():
            try:
                items.append(self._service_overview(connector, start, now))
            except Exception:
                LOGGER.warning("服务概览读取不可用：service_id=%s", connector.definition().id)
                items.append(self._degraded(connector.definition()))
        return MonitorOverviewData(
            items=tuple(items),
            source="scheduled_sampling",
            sample_interval_seconds=self._sample_interval_seconds,
            retention_hours=self._retention_hours,
        )

    @staticmethod
    def _degraded(definition: ServiceDefinitionData) -> MonitorServiceOverviewData:
        """样本读取失败时返回不可用降级概览，不保存异常详情、不伪造数值。"""
        return MonitorServiceOverviewData(
            service_id=definition.id,
            title=definition.title,
            kind=definition.kind,
            connection_status=MonitorHistoryStatus.UNAVAILABLE,
            availability=ServiceAvailability.UNAVAILABLE,
            latest_sample=None,
            trend_summary=MonitorTrendSummaryData(sample_count=0, anomaly_sample_count=0),
        )

    def _service_overview(
        self,
        connector: ServiceConnector,
        start: datetime,
        now: datetime,
    ) -> MonitorServiceOverviewData:
        """读取单个服务的窗口样本并判定概览状态、最新样本与趋势摘要。

        连接状态取自窗口内**原始**最新一条样本的 source_status（含 not_configured/unavailable
        状态样本），趋势摘要只统计有效样本（排除 not_configured 空标量样本）。
        """
        definition = connector.definition()
        session = self._session_factory()
        try:
            raw_samples = tuple(
                SqlAlchemyMonitorSampleRepository(session).list_between(definition.id, start, now)
            )
        finally:
            session.close()

        meaningful = tuple(
            sample for sample in raw_samples if sample.source_status is not ServiceSourceStatus.NOT_CONFIGURED
        )
        latest = raw_samples[-1] if raw_samples else None

        if latest is None:
            status = MonitorHistoryStatus.NOT_SAMPLED
            availability = ServiceAvailability.UNAVAILABLE
        elif latest.source_status is ServiceSourceStatus.NOT_CONFIGURED:
            status = MonitorHistoryStatus.NOT_CONFIGURED
            availability = latest.availability
        elif latest.source_status is ServiceSourceStatus.UNAVAILABLE:
            status = MonitorHistoryStatus.UNAVAILABLE
            availability = latest.availability
        else:
            status = MonitorHistoryStatus.AVAILABLE
            availability = latest.availability

        return MonitorServiceOverviewData(
            service_id=definition.id,
            title=definition.title,
            kind=definition.kind,
            connection_status=status,
            availability=availability,
            latest_sample=latest,
            trend_summary=self._trend_summary(meaningful, definition.kind),
        )

    @staticmethod
    def _trend_summary(
        samples: tuple[ServiceMonitorSampleData, ...],
        kind: str,
    ) -> MonitorTrendSummaryData:
        """统计窗口内样本数与异常采样点计数，判定规则与 P5 前端一致。"""
        is_redis = "redis" in kind.lower()
        anomaly_count = 0
        previous_availability: ServiceAvailability | None = None
        for sample in samples:
            has_slow_or_timeout = (
                (sample.slowlog_count or 0) > 0
                if is_redis
                else (sample.slow_query_count or 0) > 0 or (sample.timeout_count or 0) > 0
            )
            availability_changed = (
                previous_availability is not None and sample.availability is not previous_availability
            )
            if has_slow_or_timeout or availability_changed:
                anomaly_count += 1
            previous_availability = sample.availability
        return MonitorTrendSummaryData(
            sample_count=len(samples),
            anomaly_sample_count=anomaly_count,
        )
