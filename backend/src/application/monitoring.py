"""P5 历史监控查询、P7 监控概览与 P8 监控阈值配置应用服务。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.domain.monitoring import (
    DEFAULT_MONITOR_THRESHOLDS,
    MonitorHistoryData,
    MonitorHistoryStatus,
    MonitorOverviewData,
    MonitorServiceOverviewData,
    MonitorThresholdConfig,
    MonitorThresholdSource,
    MonitorThresholdView,
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
from src.infrastructure.persistence.monitor_repositories import (
    SqlAlchemyMonitorSampleRepository,
    SqlAlchemyMonitorThresholdRepository,
)

LOGGER = logging.getLogger(__name__)

OVERVIEW_READ_TIMEOUT_SECONDS = 3.0


def _load_threshold_config(session: Session, service_id: str) -> MonitorThresholdConfig:
    """防御性读取阈值配置：未配置或配置行校验损坏时回退内置默认并记录安全摘要。

    降级仅覆盖"校验类损坏"（领域模型校验失败）；数据库层故障属基础设施错误，
    按既有错误语义上抛（概览单服务降级 / 接口 500），不在此静默降级。
    """
    try:
        stored = SqlAlchemyMonitorThresholdRepository(session).get(service_id)
    except ValidationError:
        LOGGER.warning("监控阈值配置行损坏，回退内置默认：service_id=%s", service_id)
        stored = None
    return stored if stored is not None else DEFAULT_MONITOR_THRESHOLDS


class MonitorThresholdApplicationService:
    """P8 按服务读取与保存监控阈值配置；未配置返回内置默认并如实标注来源。"""

    def __init__(self, session_factory: SessionFactory, registry: ServiceRegistry) -> None:
        self._session_factory = session_factory
        self._registry = registry

    def get(self, service_id: str) -> MonitorThresholdView:
        """读取服务的阈值配置视图；未配置/损坏 → 内置默认 + source=default。"""
        if self._registry.get_connector(service_id) is None:
            raise ValueError("SERVICE_NOT_FOUND")
        session = self._session_factory()
        try:
            try:
                stored = SqlAlchemyMonitorThresholdRepository(session).get(service_id)
            except ValidationError:
                LOGGER.warning("监控阈值配置行损坏，回退内置默认：service_id=%s", service_id)
                stored = None
        finally:
            session.close()
        if stored is None:
            return MonitorThresholdView(
                service_id=service_id,
                source=MonitorThresholdSource.DEFAULT,
                config=DEFAULT_MONITOR_THRESHOLDS,
            )
        return MonitorThresholdView(
            service_id=service_id,
            source=MonitorThresholdSource.CONFIGURED,
            config=stored,
        )

    def save(self, service_id: str, config: MonitorThresholdConfig) -> MonitorThresholdView:
        """全量保存服务的阈值配置（单行 upsert，保存即生效）。"""
        if self._registry.get_connector(service_id) is None:
            raise ValueError("SERVICE_NOT_FOUND")
        session = self._session_factory()
        try:
            SqlAlchemyMonitorThresholdRepository(session).upsert(service_id, config)
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
        return MonitorThresholdView(
            service_id=service_id,
            source=MonitorThresholdSource.CONFIGURED,
            config=config,
        )


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
            threshold_config = _load_threshold_config(session, definition.id)
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
            trend_summary=self._trend_summary(meaningful, threshold_config),
        )

    @staticmethod
    def _trend_summary(
        samples: tuple[ServiceMonitorSampleData, ...],
        config: MonitorThresholdConfig,
    ) -> MonitorTrendSummaryData:
        """统计窗口内样本数与异常采样点计数，判定规则按服务配置计算。

        规则见 `docs/design/service-center/P8监控阈值与关注项配置Design.md` §2.3：
        当前采样点往前 window_minutes 分钟内（含两端）目标指标计数之和 ≥ 阈值 → 该点异常；
        可用性状态变化是否计异常按 count_availability_change 配置；首样本不判可用性异常，
        与前一个样本比较指序列中相邻的既有样本（缺口采样时亦然）。
        """
        anomaly_count = 0
        previous_availability: ServiceAvailability | None = None
        window_seconds = config.window_minutes * 60
        for sample in samples:
            slow_sum, timeout_sum, slowlog_sum = _windowed_metric_sums(samples, sample, window_seconds)
            has_metric_anomaly = (
                (
                    config.slow_query_count_threshold is not None
                    and slow_sum >= config.slow_query_count_threshold
                )
                or (
                    config.timeout_count_threshold is not None
                    and timeout_sum >= config.timeout_count_threshold
                )
                or (
                    config.slowlog_count_threshold is not None
                    and slowlog_sum >= config.slowlog_count_threshold
                )
            )
            availability_changed = (
                config.count_availability_change
                and previous_availability is not None
                and sample.availability is not previous_availability
            )
            if has_metric_anomaly or availability_changed:
                anomaly_count += 1
            previous_availability = sample.availability
        return MonitorTrendSummaryData(
            sample_count=len(samples),
            anomaly_sample_count=anomaly_count,
        )


def _windowed_metric_sums(
    samples: tuple[ServiceMonitorSampleData, ...],
    sample: ServiceMonitorSampleData,
    window_seconds: int,
) -> tuple[int, int, int]:
    """当前采样点往前 window_seconds 秒内（含两端）目标指标计数之和。

    样本按 observed_at 升序；window_seconds=0 时窗口只含当前采样点自身。
    null 计为 0（缺失指标不贡献计数），与现状"出现即异常"语义一致。
    """
    observed_at = sample.observed_at
    start = observed_at - timedelta(seconds=window_seconds)
    slow_sum = 0
    timeout_sum = 0
    slowlog_sum = 0
    for candidate in samples:
        if candidate.observed_at < start:
            continue
        if candidate.observed_at > observed_at:
            break
        slow_sum += candidate.slow_query_count or 0
        timeout_sum += candidate.timeout_count or 0
        slowlog_sum += candidate.slowlog_count or 0
    return slow_sum, timeout_sum, slowlog_sum
