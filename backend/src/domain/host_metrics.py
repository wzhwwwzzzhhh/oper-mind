"""P6 主机指标监控的跨层领域模型与采集端口。

独立模块：`services.py`（ServiceViewData）与 `monitoring.py`（样本标量）都只单向依赖本模块，
本模块不反向依赖二者，避免 `services.py ↔ monitoring.py` 循环依赖。

设计见 `docs/design/monitor/P6服务主机指标监控Design.md`。
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field, field_validator


class HostMetricsMode(str, Enum):
    """主机指标采集模式：mock 读场景，target 读 psutil。"""

    MOCK = "mock"
    TARGET = "target"


class HostMetricsSourceStatus(str, Enum):
    """主机采集的诚实状态。

    后端主机恒存在，不使用 `not_configured`；采集成功为 available，失败为 unavailable。
    """

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"


class HostDomainModel(BaseModel):
    """主机指标跨层模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class HostDiskPartitionData(HostDomainModel):
    """单个挂载点的脱敏使用信息，不含敏感路径细节。"""

    mount: str = Field(min_length=1, max_length=200)
    percent: float | None = Field(default=None, ge=0.0)
    used_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)


class HostProcessData(HostDomainModel):
    """异常进程的脱敏展示信息。

    仅展示名称/PID/占用率标量，不含命令行或凭据。单条进程可能只有 CPU 或只有内存超阈，
    故 `cpu_percent` / `memory_percent` 均可空。
    """

    name: str = Field(min_length=1, max_length=200)
    pid: int = Field(ge=1)
    cpu_percent: float | None = Field(default=None, ge=0.0)
    memory_percent: float | None = Field(default=None, ge=0.0)


class HostMetricsData(HostDomainModel):
    """一次主机指标采集的结构化结果。

    不可用/未采集时标量为 null，不得用 0 代替缺失（产品定义 §5.5 诚实性）。
    """

    mode: HostMetricsMode
    source_status: HostMetricsSourceStatus
    observed_at: datetime
    cpu_percent: float | None = Field(default=None, ge=0.0)
    cpu_count: int | None = Field(default=None, ge=1)
    load_avg_1m: float | None = Field(default=None, ge=0.0)
    memory_total_bytes: int | None = Field(default=None, ge=0)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    memory_percent: float | None = Field(default=None, ge=0.0)
    disk_used_percent: float | None = Field(default=None, ge=0.0)
    disk_top_partitions: tuple[HostDiskPartitionData, ...] = ()
    network_connections: int | None = Field(default=None, ge=0)
    network_established: int | None = Field(default=None, ge=0)
    network_time_wait: int | None = Field(default=None, ge=0)
    abnormal_processes: tuple[HostProcessData, ...] = ()

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        """采集时间必须为 UTC aware datetime。"""
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("observed_at 必须是 UTC aware datetime。")
        return value

    @classmethod
    def unavailable(cls, observed_at: datetime, *, mode: HostMetricsMode) -> "HostMetricsData":
        """采集失败/psutil 不可用时收敛为不可用状态，标量全部为 null。"""
        return cls(
            mode=mode,
            source_status=HostMetricsSourceStatus.UNAVAILABLE,
            observed_at=observed_at,
        )


class HostMetricsCollector(Protocol):
    """主机指标采集端口，供服务快照与历史采样器复用。"""

    def collect(self) -> HostMetricsData:
        """采集当前主机指标；不抛异常，失败返回不可用状态。"""
