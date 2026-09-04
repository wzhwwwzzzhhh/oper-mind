"""MySQL 固定指标只读 Connector。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.pool import NullPool

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

_STATUS_SQL = (
    "SHOW GLOBAL STATUS WHERE Variable_name IN "
    "('Uptime','Threads_connected','Threads_running','Slow_queries')"
)
_VARIABLE_SQL = "SHOW GLOBAL VARIABLES WHERE Variable_name = 'max_connections'"


class MySqlServiceConnector:
    """只接受 mysql+pymysql DSN，仅读取代码固定的全局标量。"""

    def __init__(
        self,
        dsn: str | None,
        engine: Engine | Any | None = None,
        instance_id: str = "mysql-local",
        title: str = "MySQL 服务",
        dsn_masked_tail: str | None = None,
        binding_origin: BindingOrigin | None = None,
    ) -> None:
        self._dsn = self._validate_dsn(dsn) if dsn is not None else None
        self._engine = engine
        self._instance_id = instance_id
        self._title = title
        self._dsn_masked_tail = dsn_masked_tail
        self._binding_origin = binding_origin or BindingOrigin.from_reference(f"registry:{instance_id}")

    @staticmethod
    def _validate_dsn(dsn: str) -> str:
        """拒绝数据库路径、URL query 和非 PyMySQL driver，避免目标扩大。"""
        try:
            url = make_url(dsn)
        except Exception as error:
            raise ValueError("MySQL DSN 格式无效") from error
        if url.drivername != "mysql+pymysql" or not url.username or not url.host:
            raise ValueError("MySQL DSN 必须使用 mysql+pymysql 且包含用户名和主机")
        if url.database not in {None, ""} or url.query:
            raise ValueError("MySQL P12 DSN 不允许数据库路径或 URL query")
        return dsn

    def definition(self) -> ServiceDefinitionData:
        """返回 MySQL 的安全服务定义。"""
        return ServiceDefinitionData(
            id=self._instance_id,
            title=self._title,
            kind="mysql",
            supported_investigations=(
                ServiceInvestigationData(
                    id=SERVICE_HEALTH_PRESSURE_INTENT_ID,
                    title="MySQL 健康与连接压力概览",
                    description="读取固定运行时长、连接数与慢查询计数标量。",
                    default_query=SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
                ),
            ),
            action_boundary="只读固定指标，不读取业务表、会话 SQL 或配置全文。",
            session_title="MySQL 健康与连接压力调查",
            has_dsn=self._dsn is not None,
            dsn_masked_tail=self._dsn_masked_tail,
        )

    def agent_capability(self) -> MySqlServiceConnector:
        """复用同一 Connector entry 作为 MySQL capability。"""
        return self

    def capability_kind(self) -> str:
        """返回封闭 capability 类型。"""
        return "mysql"

    def agent_health_snapshot(self) -> ServiceSnapshotData:
        """Agent 与连接测试复用同一固定指标读取。"""
        return self.health_snapshot()

    def binding_origin(self) -> BindingOrigin:
        """返回内部不可逆来源指纹。"""
        return self._binding_origin

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取固定指标；任何失败均收敛为无原始异常的 unavailable。"""
        observed = datetime.now(UTC)
        if self._dsn is None and self._engine is None:
            return self._empty_snapshot(observed, ServiceAvailability.NOT_CONFIGURED)
        engine = self._engine
        owns_engine = engine is None
        try:
            engine = engine or self._create_engine()
            with engine.connect() as connection:
                status_rows = connection.execute(text(_STATUS_SQL)).mappings().all()
                variable_rows = connection.execute(text(_VARIABLE_SQL)).mappings().all()
            values = self._rows_to_ints((*status_rows, *variable_rows))
            slow_queries = values.get("Slow_queries")
            result = ServiceSnapshotData(
                observed_at=observed,
                mode=ServiceMode.TARGET,
                availability=ServiceAvailability.HEALTHY,
                performance_signal=(
                    PerformanceSignal.SLOW_QUERY_DETECTED
                    if slow_queries is not None and slow_queries > 0
                    else PerformanceSignal.NO_SLOW_QUERY_DETECTED
                ),
                server_metrics=ServiceServerMetricsData(
                    source_status=ServiceSourceStatus.AVAILABLE,
                    client_connections=values.get("Threads_connected"),
                    running_connections=values.get("Threads_running"),
                    max_connections=values.get("max_connections"),
                    slow_query_count=slow_queries,
                    uptime_seconds=values.get("Uptime"),
                ),
                database=ServiceDatabaseStateData(
                    source_status=ServiceSourceStatus.AVAILABLE,
                    signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
                ),
            )
            primary_failed = False
        except Exception as error:
            result = self._empty_snapshot(
                observed,
                ServiceAvailability.UNAVAILABLE,
                failure_code=self._failure_code(error),
            )
            primary_failed = True
        if owns_engine and engine is not None:
            try:
                engine.dispose()
            except Exception:
                LOGGER.warning("MySQL 连接清理失败：instance_id=%s", self._instance_id)
                if primary_failed:
                    return self._empty_snapshot(
                        observed,
                        ServiceAvailability.UNAVAILABLE,
                        failure_code="cleanup_failed",
                    )
                return result.model_copy(update={"cleanup_status": "unknown"})
        return result

    def _create_engine(self) -> Engine:
        """创建 NullPool、短超时、无隐式重试的 Engine。"""
        if self._dsn is None:
            raise ValueError("MySQL DSN 未配置")
        return create_engine(
            self._dsn,
            poolclass=NullPool,
            pool_pre_ping=False,
            connect_args={
                "connect_timeout": 3,
                "read_timeout": 3,
                "write_timeout": 3,
                "charset": "utf8mb4",
            },
        )

    @staticmethod
    def _rows_to_ints(rows: tuple[Any, ...]) -> dict[str, int]:
        result: dict[str, int] = {}
        for row in rows:
            name = row.get("Variable_name") or row.get("variable_name")
            value = row.get("Value") if "Value" in row else row.get("value")
            if isinstance(name, str) and value is not None:
                if name in result:
                    raise ValueError("MySQL 指标重复")
                parsed = int(value)
                if parsed < 0:
                    raise ValueError("MySQL 指标不能为负数")
                result[name] = parsed
        return result

    @staticmethod
    def _empty_snapshot(
        observed: datetime,
        availability: ServiceAvailability,
        failure_code: str | None = None,
    ) -> ServiceSnapshotData:
        not_configured = availability is ServiceAvailability.NOT_CONFIGURED
        source = ServiceSourceStatus.NOT_CONFIGURED if not_configured else ServiceSourceStatus.UNAVAILABLE
        signal = PerformanceSignal.NOT_CONFIGURED if not_configured else PerformanceSignal.UNAVAILABLE
        database_signal = DatabaseSignal.NOT_CONFIGURED if not_configured else DatabaseSignal.UNAVAILABLE
        return ServiceSnapshotData(
            observed_at=observed,
            mode=ServiceMode.DISABLED if not_configured else ServiceMode.TARGET,
            availability=availability,
            performance_signal=signal,
            server_metrics=ServiceServerMetricsData(source_status=source),
            database=ServiceDatabaseStateData(source_status=source, signal=database_signal),
            failure_code=failure_code,
        )

    @staticmethod
    def _failure_code(error: Exception) -> str:
        return classify_service_operation_failure(error)
