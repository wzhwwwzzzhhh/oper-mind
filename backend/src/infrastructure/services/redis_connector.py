"""静态注册的 Redis 只读服务 Connector。

凭据只走 `OPERMIND_SERVICE_<INSTANCE_ID>_DSN` 环境变量命名空间化，零落库；
连接默认三秒超时，仅执行 PING / INFO memory / CLIENT LIST / SLOWLOG LEN 只读命令。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import redis
from redis import Redis

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


class RedisServiceConnector:
    """只读 Redis 服务快照 Connector，实现 ServiceConnector 协议。"""

    def __init__(
        self,
        dsn: str | None,
        client: Redis | Any | None = None,
        instance_id: str = "redis-production",
        title: str = "生产 Redis 缓存",
    ) -> None:
        self._dsn = dsn
        self._instance_id = instance_id
        self._title = title
        # client 注入点：测试传假客户端；生产用 from_url(dsn) 现建。
        self._client = client

    def definition(self) -> ServiceDefinitionData:
        """返回 Redis 服务的静态身份与只读调查边界。"""
        return ServiceDefinitionData(
            id=self._instance_id,
            title=self._title,
            kind="redis",
            supported_investigations=(),
            action_boundary="只读监控，不执行任何写入、配置变更或键空间访问。",
            session_title="Redis 缓存健康调查",
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前有限只读快照；失败/超时返回 unavailable，不抛异常。"""
        observed = datetime.now(timezone.utc)
        if self._dsn is None:
            return self._not_configured(observed)

        client = self._client
        owns_client = client is None
        try:
            client = client or self._create_readonly_client()
            return self._read_healthy(client, observed)
        except Exception:
            return self._unavailable(observed)
        finally:
            if owns_client and client is not None:
                try:
                    client.close()
                except Exception:
                    pass

    def _create_readonly_client(self) -> Redis:
        """创建只读 Redis 客户端，固定三秒连接与命令超时。"""
        assert self._dsn is not None
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
    def _unavailable(observed: datetime) -> ServiceSnapshotData:
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
        )
