"""P4.3 已注册服务、有限快照与活动摘要的领域模型。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from hashlib import sha256
from threading import Lock, RLock
from typing import Protocol, runtime_checkable
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.domain.host_metrics import HostMetricsData

POSTGRES_PRODUCTION_SERVICE_ID = "postgres-production"
POSTGRES_STAGING_SERVICE_ID = "postgres-staging"
POSTGRES_TARGET_SERVICE_ID = "postgres-target"
REDIS_PRODUCTION_SERVICE_ID = "redis-production"
SERVICE_HEALTH_PRESSURE_INTENT_ID = "service_health_pressure.v1"
SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY = "请对当前服务执行只读健康与连接压力调查。"
SERVICE_KINDS = frozenset({"postgres", "redis", "mysql"})
REGISTERED_SERVICE_IDS = frozenset({
    POSTGRES_PRODUCTION_SERVICE_ID,
    POSTGRES_STAGING_SERVICE_ID,
    POSTGRES_TARGET_SERVICE_ID,
    REDIS_PRODUCTION_SERVICE_ID,
})
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
    # P8 动态注册服务的凭据安全视图：只表意不泄露。
    has_dsn: bool = False
    dsn_masked_tail: str | None = Field(default=None, max_length=8)


class ServiceServerMetricsData(ServiceDomainModel):
    """从固定服务指标端点读取的有限脱敏标量。

    PG 语义字段（p50_ms / p95_ms / slow_query_count / timeout_count）对 Redis 实例置 null，
    Redis 专用标量（memory_bytes / client_connections / slowlog_count）对 PG 实例置 null。
    """

    source_status: ServiceSourceStatus
    window_size: int | None = Field(default=None, ge=0)
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    slow_query_count: int | None = Field(default=None, ge=0)
    timeout_count: int | None = Field(default=None, ge=0)
    memory_bytes: int | None = Field(default=None, ge=0)
    client_connections: int | None = Field(default=None, ge=0)
    slowlog_count: int | None = Field(default=None, ge=0)
    uptime_seconds: int | None = Field(default=None, ge=0)
    running_connections: int | None = Field(default=None, ge=0)
    max_connections: int | None = Field(default=None, ge=0)
    active_connections: int | None = Field(default=None, ge=0)
    idle_connections: int | None = Field(default=None, ge=0)
    waiting_connections: int | None = Field(default=None, ge=0)


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
    failure_code: str | None = Field(default=None, max_length=80)
    cleanup_status: str | None = Field(default=None, pattern="^unknown$")

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        """快照时间必须为 UTC aware 时间。"""
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("observed_at 必须是 UTC aware datetime。")
        return value


class ServiceViewData(ServiceDomainModel):
    """服务中心列表和详情共用的动态服务视图。

    携带服务所在后端主机的主机指标（必选，恒存在）；采集失败时 `source_status` 为 unavailable，
    不伪造数值。
    """

    definition: ServiceDefinitionData
    snapshot: ServiceSnapshotData
    host_metrics: HostMetricsData


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
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("活动时间必须是 UTC aware datetime。")
        return value


class ServiceConnector(Protocol):
    """已注册服务必须实现的只读固定能力端口。"""

    def definition(self) -> ServiceDefinitionData:
        """返回代码内静态服务身份与能力。"""

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前受控有限快照。"""

    def agent_capability(self) -> object:
        """返回不暴露凭据、仅含类型限定读取方法的 Agent capability。"""

    def binding_origin(self) -> BindingOrigin:
        """返回仅用于人工验收同源核对的不可逆来源指纹。"""


@runtime_checkable
class TypedServiceCapability(Protocol):
    """三类服务 capability 的共同封闭表面。"""

    def capability_kind(self) -> str: ...

    def agent_health_snapshot(self) -> ServiceSnapshotData: ...


@runtime_checkable
class PostgresServiceCapability(TypedServiceCapability, Protocol):
    """PostgreSQL 既有只读 Tool 额外需要的封闭连接能力。"""

    def explain_select(self, sql: str) -> str: ...

    def show_indexes(self, table: str) -> str: ...

    def show_create_table(self, table: str) -> str: ...

    def check_locks(self) -> str: ...


class ServiceBindingFailureCode(str, Enum):
    """Registry binding 解析的封闭失败分类。"""

    NOT_FOUND = "binding_not_found"
    TYPE_MISMATCH = "binding_type_mismatch"
    INVESTIGATION_NOT_SUPPORTED = "investigation_not_supported"
    CREDENTIAL_UNAVAILABLE = "credential_unavailable"
    POISONED = "binding_poisoned"


class ServiceBindingError(ValueError):
    """不携带目标或凭据正文的 typed binding failure。"""

    def __init__(self, code: ServiceBindingFailureCode) -> None:
        self.code = code
        super().__init__(code.value)


@dataclass(frozen=True)
class BindingOrigin:
    """Registry entry 的内部来源证明；不得进入 Agent、Trace 或公开 API。"""

    source_fingerprint: str

    @classmethod
    def from_reference(cls, reference: str) -> BindingOrigin:
        """只保存引用的 SHA-256，不保存环境变量名或 credential reference。"""
        return cls(source_fingerprint=sha256(reference.encode("utf-8")).hexdigest())


@dataclass(frozen=True)
class BoundServiceCapabilities:
    """传给 Agent 的最窄服务视图；不含 Connector、DSN 或来源元数据。"""

    service_id: str
    kind: str
    supported_investigations: frozenset[str]
    capability: TypedServiceCapability


@dataclass(frozen=True)
class RegistryBinding:
    """由唯一 Registry entry 原子派生的内部 typed binding。"""

    service_id: str
    kind: str
    supported_investigations: frozenset[str]
    capability: TypedServiceCapability
    origin: BindingOrigin

    def for_agent(self) -> BoundServiceCapabilities:
        """投影为 Agent 可见的无凭据 capability。"""
        return BoundServiceCapabilities(
            service_id=self.service_id,
            kind=self.kind,
            supported_investigations=self.supported_investigations,
            capability=self.capability,
        )


@runtime_checkable
class BindingCapableConnector(Protocol):
    """能从同一 Connector entry 派生 Agent capability 的内部协议。"""

    def definition(self) -> ServiceDefinitionData: ...

    def health_snapshot(self) -> ServiceSnapshotData: ...

    def agent_capability(self) -> TypedServiceCapability: ...

    def binding_origin(self) -> BindingOrigin: ...


def validate_service_instance_id(value: str) -> str:
    """唯一 service_id 规则：trim 后 1–64 字符及受控字符集。"""
    import re

    normalized = value.strip()
    if not 1 <= len(normalized) <= 64 or re.fullmatch(r"[a-z0-9][a-z0-9._-]*", normalized) is None:
        raise ValueError("实例 ID 只允许小写字母、数字、点、下划线或连字符。")
    return normalized


def classify_service_operation_failure(error: Exception) -> str:
    """只按异常类型、包装链与稳定数字码分类；不读取或输出异常正文。"""
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    permission_codes = {1044, 1045, 1142, 1227}
    timeout_codes = {1205, 2002, 2003, 2006, 2013}
    permission_sqlstates = {"42501", "28P01"}
    timeout_sqlstates = {"57014"}
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        name = type(current).__name__.lower()
        if isinstance(current, TimeoutError) or "timeout" in name:
            return "operation_timeout"
        if (
            isinstance(current, PermissionError)
            or "permission" in name
            or "authentication" in name
            or "authorization" in name
            or "accessdenied" in name
        ):
            return "permission_denied"
        code = current.args[0] if current.args and isinstance(current.args[0], int) else None
        if code in permission_codes:
            return "permission_denied"
        if code in timeout_codes:
            return "operation_timeout"
        sqlstate = getattr(current, "sqlstate", None) or getattr(current, "pgcode", None)
        if sqlstate in permission_sqlstates:
            return "permission_denied"
        if sqlstate in timeout_sqlstates:
            return "operation_timeout"
        for nested in (getattr(current, "orig", None), current.__cause__, current.__context__):
            if isinstance(nested, BaseException):
                pending.append(nested)
    if isinstance(error, (TypeError, ValueError)):
        return "malformed_fact"
    return "connection_unavailable"


_EXPECTED_INVESTIGATIONS = {
    "postgres": frozenset({"postgres_slow_query.v1", SERVICE_HEALTH_PRESSURE_INTENT_ID}),
    "redis": frozenset({SERVICE_HEALTH_PRESSURE_INTENT_ID}),
    "mysql": frozenset({SERVICE_HEALTH_PRESSURE_INTENT_ID}),
}


class ServiceRegistry:
    """已注册服务的运行时注册表。

    由「启动时硬编码实例（env DSN）」与「运行时经白名单类型注册的动态服务」
    共同组成；动态注册走 P8 应用服务（DSN 加密落库），只接受 postgres/redis
    类型。读方经 list_connectors()/get_connector() 取快照；写方复制当前表后
    整体替换（单次 dict 赋值），CPython GIL 下读不阻塞写、不因 resize 抛错。
    """

    def __init__(self, connectors: tuple[ServiceConnector, ...]) -> None:
        definitions = tuple(connector.definition() for connector in connectors)
        ids = [definition.id for definition in definitions]
        if len(set(ids)) != len(ids):
            raise ValueError("服务注册表中的静态服务标识必须唯一。")
        for connector in connectors:
            self._validate_connector(connector)
        self._connectors = {connector.definition().id: connector for connector in connectors}
        self._poisoned_service_ids: frozenset[str] = frozenset()
        self._mutation_locks: dict[str, RLock] = {}
        self._mutation_locks_guard = Lock()
        self._mutation_epoch = RLock()

    def list_connectors(self) -> tuple[ServiceConnector, ...]:
        """按固定注册顺序返回 Connector 的当前快照。"""
        with self._mutation_epoch:
            return tuple(
                connector
                for service_id, connector in self._connectors.items()
                if service_id not in self._poisoned_service_ids
            )

    def get_connector(self, service_id: str) -> ServiceConnector | None:
        """按服务键读取 Connector，不解析 URL 或连接配置。"""
        with self.entry_guard(service_id):
            if service_id in self._poisoned_service_ids:
                return None
            return self._connectors.get(service_id)

    def resolve_binding(
        self,
        service_id: str,
        *,
        expected_kind: str | None = None,
        investigation_id: str | None = None,
    ) -> RegistryBinding:
        """从唯一 Connector entry 精确解析 binding；任何不匹配均失败关闭。"""
        with self.entry_guard(service_id):
            if service_id in self._poisoned_service_ids:
                raise ServiceBindingError(ServiceBindingFailureCode.POISONED)
            connector = self._connectors.get(service_id)
            if connector is None or not isinstance(connector, BindingCapableConnector):
                raise ServiceBindingError(ServiceBindingFailureCode.NOT_FOUND)
            definition, capability, investigations = self._validate_connector(connector)
            if capability is None:
                raise ServiceBindingError(ServiceBindingFailureCode.NOT_FOUND)
            if definition.id != service_id:
                raise ServiceBindingError(ServiceBindingFailureCode.NOT_FOUND)
            if expected_kind is not None and definition.kind != expected_kind:
                raise ServiceBindingError(ServiceBindingFailureCode.TYPE_MISMATCH)
            if investigation_id is not None and investigation_id not in investigations:
                raise ServiceBindingError(ServiceBindingFailureCode.INVESTIGATION_NOT_SUPPORTED)
            if not definition.has_dsn:
                raise ServiceBindingError(ServiceBindingFailureCode.CREDENTIAL_UNAVAILABLE)
            return RegistryBinding(
                service_id=definition.id,
                kind=definition.kind,
                supported_investigations=investigations,
                capability=capability,
                origin=connector.binding_origin(),
            )

    def service_ids(self) -> frozenset[str]:
        """返回当前注册表中的合法服务键。"""
        with self._mutation_epoch:
            return frozenset(self._connectors) - self._poisoned_service_ids

    def register(self, connector: ServiceConnector) -> None:
        """运行时注册一个 Connector；实例 ID 冲突时抛 ValueError。"""
        definition, _, _ = self._validate_connector(connector)
        with self.mutation_guard(definition.id):
            current = self._connectors
            if definition.id in current:
                raise ValueError(f"服务实例 ID 已存在：{definition.id}")
            next_table = dict(current)
            next_table[definition.id] = connector
            self._connectors = next_table

    def replace(self, connector: ServiceConnector, expected: ServiceConnector | None = None) -> bool:
        """运行时替换一个已注册 Connector；不存在时注册并返回 False。"""
        definition, _, _ = self._validate_connector(connector)
        with self.mutation_guard(definition.id):
            next_table = dict(self._connectors)
            current = next_table.get(definition.id)
            if current is None or (expected is not None and current is not expected):
                return False
            next_table[definition.id] = connector
            self._connectors = next_table
            return True

    def remove(self, service_id: str, expected: ServiceConnector | None = None) -> bool:
        """从注册表移除一个服务；不存在返回 False（幂等）。"""
        with self.mutation_guard(service_id):
            current = self._connectors
            connector = current.get(service_id)
            if connector is None or (expected is not None and connector is not expected):
                return False
            next_table = dict(current)
            del next_table[service_id]
            self._connectors = next_table
            return True

    def poison(self, service_id: str) -> None:
        """隔离发生不可恢复可见性违例的单一 entry；不影响其他服务。"""
        with self.entry_guard(service_id):
            self._poisoned_service_ids = self._poisoned_service_ids | {service_id}

    def entry_guard(self, service_id: str) -> RLock:
        """单一 entry 的读写 guard；其他 service_id 不受阻塞。"""
        with self._mutation_locks_guard:
            return self._mutation_locks.setdefault(service_id, RLock())

    @contextmanager
    def mutation_guard(self, service_id: str) -> Iterator[None]:
        """写操作持有 mutation epoch，使全量投影不会看见 commit/map 中间窗。"""
        with self._mutation_epoch, self.entry_guard(service_id):
            yield

    @staticmethod
    def _validate_connector(
        connector: ServiceConnector,
    ) -> tuple[ServiceDefinitionData, TypedServiceCapability | None, frozenset[str]]:
        """entry 暴露前验证 kind、investigation 与 typed capability 完整一致。"""
        definition = connector.definition()
        investigations = frozenset(item.id for item in definition.supported_investigations)
        if not isinstance(connector, BindingCapableConnector):
            if investigations:
                raise ValueError("声明 investigation 的 Connector 必须支持 typed binding")
            return definition, None, investigations
        expected = _EXPECTED_INVESTIGATIONS.get(definition.kind)
        if expected is None or investigations != expected:
            raise ValueError("服务 investigation profile 不匹配")
        capability = connector.agent_capability()
        if not isinstance(capability, TypedServiceCapability):
            raise ValueError("服务 capability 类型无效")
        if capability.capability_kind() != definition.kind:
            raise ValueError("服务 capability kind 不匹配")
        if definition.kind == "postgres" and not isinstance(capability, PostgresServiceCapability):
            raise ValueError("PostgreSQL capability 不完整")
        return definition, capability, investigations


class ServiceRegistrationData(ServiceDomainModel):
    """P8 动态注册服务的持久化安全视图。

    DSN 以密文流转：``dsn_encrypted`` / ``dsn_nonce`` 仅为应用层与仓储之间的
    密文流转，对外资源映射只取 ``has_dsn`` 与 ``dsn_masked_tail``；明文 DSN
    绝不进入本模型之外的任何层。
    """

    instance_id: str = Field(min_length=1, max_length=64)
    kind: str = Field(min_length=1, max_length=80)
    title: str = Field(min_length=1, max_length=120)
    dsn_encrypted: str | None = None
    dsn_nonce: str | None = None
    has_dsn: bool = False
    dsn_masked_tail: str | None = Field(default=None, max_length=8)
    created_at: datetime | None = None
    updated_at: datetime | None = None
