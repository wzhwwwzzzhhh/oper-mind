"""P4.3 已注册服务、有限快照与活动摘要的领域模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


POSTGRES_PRODUCTION_SERVICE_ID = "postgres-production"
POSTGRES_STAGING_SERVICE_ID = "postgres-staging"
REGISTERED_SERVICE_IDS = frozenset({POSTGRES_PRODUCTION_SERVICE_ID, POSTGRES_STAGING_SERVICE_ID})
ORDERS_SLOW_QUERY_INTENT_ID = "orders_slow_query.v1"
ORDERS_SLOW_QUERY_DEFAULT_QUERY = "订单服务变慢，帮我排查慢查询。"
ORDER_SERVICE_SESSION_TITLE = "订单服务慢查询调查"


class ServiceMode(str, Enum):
    """服务快照的受控数据源模式。"""

    DISABLED = "disabled"
    MOCK = "mock"
    TARGET = "target"


class ServiceSourceStatus(str, Enum):
    """单个外部来源的可读状态。"""

    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class ServiceAvailability(str, Enum):
    """固定健康端点的当前可用性结论。"""

    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class DatabaseSignal(str, Enum):
    """固定数据库读取的高层状态，不携带 SQL 或对象名。"""

    MISSING_INDEX_SEQ_SCAN_DETECTED = "missing_index_seq_scan_detected"
    INDEX_AND_PLAN_CONFIRMED = "index_and_plan_confirmed"
    INSUFFICIENT_DATA = "insufficient_data"
    NO_SLOW_QUERY_DETECTED = "no_slow_query_detected"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class PerformanceSignal(str, Enum):
    """由当前固定数据库与服务指标共同得出的性能信号。"""

    SLOW_QUERY_DETECTED = "slow_query_detected"
    NO_SLOW_QUERY_DETECTED = "no_slow_query_detected"
    INSUFFICIENT_DATA = "insufficient_data"
    UNAVAILABLE = "unavailable"
    NOT_CONFIGURED = "not_configured"


class ServiceDomainModel(BaseModel):
    """P4.3 跨层服务数据的严格基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ServiceInvestigationData(ServiceDomainModel):
    """服务卡中可发起的固定调查能力。"""

    id: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    description: str = Field(min_length=1, max_length=280)
    default_query: str = Field(min_length=1, max_length=4000)


class ServiceDefinitionData(ServiceDomainModel):
    """静态注册服务的用户可见身份与能力边界。"""

    id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    kind: str = Field(min_length=1, max_length=80)
    supported_investigations: tuple[ServiceInvestigationData, ...]
    action_boundary: str = Field(min_length=1, max_length=280)
    session_title: str = Field(min_length=1, max_length=200)


class ServiceServerMetricsData(ServiceDomainModel):
    """从固定服务指标端点读取的有限脱敏标量。"""

    source_status: ServiceSourceStatus
    window_size: int | None = Field(default=None, ge=0)
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    slow_query_count: int | None = Field(default=None, ge=0)
    timeout_count: int | None = Field(default=None, ge=0)


class ServiceDatabaseStateData(ServiceDomainModel):
    """从固定数据库读取收敛出的高层状态。"""

    source_status: ServiceSourceStatus
    signal: DatabaseSignal


class ServiceSnapshotData(ServiceDomainModel):
    """一次请求时读取的有限快照，不构成时序监控历史。"""

    observed_at: datetime
    mode: ServiceMode
    availability: ServiceAvailability
    performance_signal: PerformanceSignal
    server_metrics: ServiceServerMetricsData
    database: ServiceDatabaseStateData

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        """快照时间必须为 UTC aware 时间。"""
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("observed_at 必须是 UTC aware datetime。")
        return value


class ServiceViewData(ServiceDomainModel):
    """服务中心列表和详情共用的动态服务视图。"""

    definition: ServiceDefinitionData
    snapshot: ServiceSnapshotData


class ServiceActivityData(ServiceDomainModel):
    """服务关联 Run 与修复闭环的最小历史摘要。"""

    session_id: UUID
    session_title: str = Field(min_length=1, max_length=200)
    run_id: UUID
    run_status: str = Field(min_length=1, max_length=20)
    created_at: datetime
    finished_at: datetime | None = None
    summary: str | None = Field(default=None, max_length=800)
    severity: str | None = Field(default=None, max_length=20)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    proposal_status: str | None = Field(default=None, max_length=32)
    verification_status: str | None = Field(default=None, max_length=32)

    @field_validator("created_at", "finished_at")
    @classmethod
    def validate_utc_datetime(cls, value: datetime | None) -> datetime | None:
        """活动时间必须为 UTC aware 时间。"""
        if value is None:
            return value
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError("活动时间必须是 UTC aware datetime。")
        return value


class ServiceConnector(Protocol):
    """已注册服务必须实现的只读固定能力端口。"""

    def definition(self) -> ServiceDefinitionData:
        """返回代码内静态服务身份与能力。"""

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前受控有限快照。"""


class ServiceRegistry:
    """只保存经过设计审查的静态 Connector，不提供运行时写入能力。"""

    def __init__(self, connectors: tuple[ServiceConnector, ...]) -> None:
        definitions = tuple(connector.definition() for connector in connectors)
        ids = [definition.id for definition in definitions]
        if len(set(ids)) != len(ids):
            raise ValueError("服务注册表中的静态服务标识必须唯一。")
        self._connectors = {connector.definition().id: connector for connector in connectors}

    def list_connectors(self) -> tuple[ServiceConnector, ...]:
        """按固定注册顺序返回 Connector。"""
        return tuple(self._connectors.values())

    def get_connector(self, service_id: str) -> ServiceConnector | None:
        """按静态服务键读取 Connector，不解析 URL 或连接配置。"""
        return self._connectors.get(service_id)

    def service_ids(self) -> frozenset[str]:
        """返回当前静态注册表中的合法服务键。"""
        return frozenset(self._connectors)
