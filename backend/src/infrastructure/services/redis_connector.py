"""静态注册的 Redis 只读服务 Connector。

凭据只走 `OPERMIND_SERVICE_<INSTANCE_ID>_DSN` 环境变量命名空间化，零落库；
连接默认三秒超时，仅执行 PING / INFO memory / CLIENT LIST / SLOWLOG LEN 只读命令。
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import redis
from redis import Redis

from src.domain.services import (
    SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
    SERVICE_HEALTH_PRESSURE_INTENT_ID,
    BindingOrigin,
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceDatabaseStateData,
    ServiceDefinitionData,
    ServiceInvestigationData,
    ServiceMode,
    ServiceServerMetricsData,
    ServiceSnapshotData,
    ServiceSourceStatus,
    classify_service_operation_failure,
)

LOGGER = logging.getLogger(__name__)


class RedisServiceConnector:
    """只读 Redis 服务快照 Connector，实现 ServiceConnector 协议。"""

    def __init__(
        self,
        dsn: str | None,
        client: Redis | Any | None = None,
        instance_id: str = "redis-production",
        title: str = "生产 Redis 缓存",
        dsn_masked_tail: str | None = None,
        binding_origin: BindingOrigin | None = None,
    ) -> None:
        self._dsn = dsn
        self._instance_id = instance_id
        self._title = title
        self._dsn_masked_tail = dsn_masked_tail
        self._binding_origin = binding_origin or BindingOrigin.from_reference(f"registry:{instance_id}")
        # client 注入点：测试传假客户端；生产用 from_url(dsn) 现建。
        self._client = client

    def definition(self) -> ServiceDefinitionData:
        """返回 Redis 服务的静态身份与只读调查边界。"""
        return ServiceDefinitionData(
            id=self._instance_id,
            title=self._title,
            kind="redis",
            supported_investigations=(
                ServiceInvestigationData(
                    id=SERVICE_HEALTH_PRESSURE_INTENT_ID,
                    title="Redis 健康与压力概览",
                    description="读取固定健康、内存、连接数和慢日志计数标量。",
                    default_query=SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
                ),
            ),
            action_boundary="只读监控，不执行任何写入、配置变更或键空间访问。",
            session_title="Redis 缓存健康调查",
            has_dsn=self._dsn is not None,
            dsn_masked_tail=self._dsn_masked_tail,
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前有限只读快照；失败/超时返回 unavailable，不抛异常。"""
        return self._collect_snapshot(strict_cleanup=False)

    def _collect_snapshot(self, *, strict_cleanup: bool) -> ServiceSnapshotData:
        """P12 Agent 对 cleanup 未知失败关闭；既有服务快照保持 P11 兼容语义。"""
        observed = datetime.now(UTC)
        if self._dsn is None:
            return self._not_configured(observed)

        client = self._client
        owns_client = client is None
        try:
            client = client or self._create_readonly_client()
            result = self._read_healthy(client, observed)
            primary_failed = False
        except Exception as error:
            result = self._unavailable(observed, self._failure_code(error))
            primary_failed = True
        if owns_client and client is not None:
            try:
                client.close()
            except Exception:
                LOGGER.warning("Redis 连接关闭失败：instance_id=%s", self._instance_id)
                if strict_cleanup:
                    if primary_failed:
                        return self._unavailable(observed, "cleanup_failed")
                    return result.model_copy(update={"cleanup_status": "unknown"})
        return result

    def agent_capability(self) -> RedisServiceConnector:
        """复用同一 Connector entry 作为固定 Redis 健康 capability。"""
        return self

    def capability_kind(self) -> str:
        """返回封闭 capability 类型。"""
        return "redis"

    def agent_health_snapshot(self) -> ServiceSnapshotData:
        """Agent 与连接测试复用同一固定命令读取。"""
        return self._collect_snapshot(strict_cleanup=True)

    def binding_origin(self) -> BindingOrigin:
        """返回内部来源指纹，不暴露引用正文。"""
        return self._binding_origin

    def _create_readonly_client(self) -> Redis:
        """创建只读 Redis 客户端，固定三秒连接与命令超时。"""
        # 同 postgres_connector：不用 assert，python -O 下会被剥掉。异常文本不含 DSN。
        if self._dsn is None:
            raise ValueError("Redis DSN 未配置")
        return redis.Redis.from_url(
            self._dsn,
            socket_connect_timeout=3.0,
            socket_timeout=3.0,
            decode_responses=True,
        )

    def _read_healthy(self, client: Redis | Any, observed: datetime) -> ServiceSnapshotData:
        """依次执行只读命令并收敛 Redis 专用标量。"""
        if client.ping() is not True:
            raise RuntimeError("Redis PING 未返回 PONG")
        info = client.info("memory")
        memory_bytes = self._metric_int(info, "used_memory")
        client_connections = len(client.client_list())
        slowlog_count = int(client.slowlog_len())
        return ServiceSnapshotData(
            observed_at=observed,
            mode=ServiceMode.TARGET,
            availability=ServiceAvailability.HEALTHY,
            performance_signal=(
                PerformanceSignal.SLOW_QUERY_DETECTED
                if slowlog_count > 0
                else PerformanceSignal.NO_SLOW_QUERY_DETECTED
            ),
            server_metrics=ServiceServerMetricsData(
                source_status=ServiceSourceStatus.AVAILABLE,
                memory_bytes=memory_bytes,
                client_connections=client_connections,
                slowlog_count=slowlog_count,
            ),
            database=ServiceDatabaseStateData(
                source_status=ServiceSourceStatus.AVAILABLE,
                signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
            ),
        )

    @staticmethod
    def _metric_int(info: dict[str, Any], name: str) -> int | None:
        """把 INFO 字段安全收敛为非负整数。"""
        value = info.get(name)
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _not_configured(observed: datetime) -> ServiceSnapshotData:
        """构造未配置凭据时的固定快照。"""
        return ServiceSnapshotData(
            observed_at=observed,
            mode=ServiceMode.DISABLED,
            availability=ServiceAvailability.NOT_CONFIGURED,
            performance_signal=PerformanceSignal.NOT_CONFIGURED,
            server_metrics=ServiceServerMetricsData(
                source_status=ServiceSourceStatus.NOT_CONFIGURED,
            ),
            database=ServiceDatabaseStateData(
                source_status=ServiceSourceStatus.NOT_CONFIGURED,
                signal=DatabaseSignal.NOT_CONFIGURED,
            ),
        )

    @staticmethod
    def _unavailable(observed: datetime, failure_code: str = "unavailable") -> ServiceSnapshotData:
        """构造连接失败或读取超时时的固定快照。"""
        return ServiceSnapshotData(
            observed_at=observed,
            mode=ServiceMode.TARGET,
            availability=ServiceAvailability.UNAVAILABLE,
            performance_signal=PerformanceSignal.UNAVAILABLE,
            server_metrics=ServiceServerMetricsData(
                source_status=ServiceSourceStatus.UNAVAILABLE,
            ),
            database=ServiceDatabaseStateData(
                source_status=ServiceSourceStatus.UNAVAILABLE,
                signal=DatabaseSignal.UNAVAILABLE,
            ),
            failure_code=failure_code,
        )

    @staticmethod
    def _failure_code(error: Exception) -> str:
        return classify_service_operation_failure(error)
