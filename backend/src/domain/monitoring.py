"""P5 历史监控样本的跨层领域模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.services import (
    PerformanceSignal,
    ServiceAvailability,
    ServiceSnapshotData,
    ServiceSourceStatus,
)


class MonitorHistoryStatus(str, Enum):
    """历史查询结果的诚实状态。"""

    AVAILABLE = "available"
    NOT_SAMPLED = "not_sampled"
    NOT_CONFIGURED = "not_configured"
    UNAVAILABLE = "unavailable"


class MonitorDomainModel(BaseModel):
    """监控跨层模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ServiceMonitorSampleData(MonitorDomainModel):
    """一次定时采样留下的脱敏标量。"""

    id: UUID | None = None
    service_id: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    availability: ServiceAvailability
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    slow_query_count: int | None = Field(default=None, ge=0)
    timeout_count: int | None = Field(default=None, ge=0)
    memory_bytes: int | None = Field(default=None, ge=0)
    client_connections: int | None = Field(default=None, ge=0)
    slowlog_count: int | None = Field(default=None, ge=0)
    # P6 主机指标历史标量：每轮采样一次写入各服务样本；失败/未采样为 null，不用 0 代替缺失。
    host_cpu_percent: float | None = Field(default=None, ge=0.0)
    host_memory_percent: float | None = Field(default=None, ge=0.0)
    host_memory_bytes: int | None = Field(default=None, ge=0)
    host_disk_used_percent: float | None = Field(default=None, ge=0.0)
    performance_signal: PerformanceSignal
    source_status: ServiceSourceStatus

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        """样本时间必须为 UTC aware datetime。"""
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("observed_at 必须是 UTC aware datetime。")
        return value

    @classmethod
    def from_snapshot(cls, service_id: str, snapshot: ServiceSnapshotData) -> "ServiceMonitorSampleData":
        """从服务快照提取只允许落库的脱敏字段。"""
        metrics = snapshot.server_metrics
        return cls(
            service_id=service_id,
            observed_at=snapshot.observed_at,
            availability=snapshot.availability,
            p50_ms=metrics.p50_ms,
            p95_ms=metrics.p95_ms,
            slow_query_count=metrics.slow_query_count,
            timeout_count=metrics.timeout_count,
            memory_bytes=metrics.memory_bytes,
            client_connections=metrics.client_connections,
            slowlog_count=metrics.slowlog_count,
            performance_signal=snapshot.performance_signal,
            source_status=metrics.source_status,
        )

    @classmethod
    def unavailable(cls, service_id: str, observed_at: datetime) -> "ServiceMonitorSampleData":
        """把采样异常收敛为不可用状态，不保存异常详情。"""
        return cls(
            service_id=service_id,
            observed_at=observed_at,
            availability=ServiceAvailability.UNAVAILABLE,
            performance_signal=PerformanceSignal.UNAVAILABLE,
            source_status=ServiceSourceStatus.UNAVAILABLE,
        )


class MonitorHistoryData(MonitorDomainModel):
    """历史查询的安全响应模型。"""

    service_id: str = Field(min_length=1, max_length=64)
    status: MonitorHistoryStatus
    source: str = "scheduled_sampling"
    sample_interval_seconds: int = Field(ge=30)
    retention_hours: int = Field(ge=1)
    from_at: datetime
    to_at: datetime
    samples: tuple[ServiceMonitorSampleData, ...]


class MonitorTrendSummaryData(MonitorDomainModel):
    """概览窗口内的趋势摘要：样本数与异常采样点计数。"""

    sample_count: int = Field(ge=0)
    anomaly_sample_count: int = Field(ge=0)


class MonitorServiceOverviewData(MonitorDomainModel):
    """单个已注册服务的监控概览视图。

    数据来自定时采样历史（`service_monitor_samples`），不触发目标连接；
    连接状态与最新样本语义见 `docs/design/monitor/P7服务监控概览页Design.md`。
    """

    service_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=80)
    connection_status: MonitorHistoryStatus
    availability: ServiceAvailability
    latest_sample: ServiceMonitorSampleData | None = None
    trend_summary: MonitorTrendSummaryData


class MonitorOverviewData(MonitorDomainModel):
    """全部已注册服务的监控概览响应。"""

    items: tuple[MonitorServiceOverviewData, ...]
    source: str = "scheduled_sampling"
    sample_interval_seconds: int = Field(ge=30)
    retention_hours: int = Field(ge=1)
