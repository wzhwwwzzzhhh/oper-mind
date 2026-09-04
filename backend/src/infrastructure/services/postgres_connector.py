"""静态注册的 PostgreSQL 只读 Connector。"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

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
from src.infrastructure.services.postgres_engine import create_read_only_postgres_engine

LOGGER = logging.getLogger(__name__)


class _PostgresReadonlyCapability:
    """Agent-facing 封闭 adapter；不暴露 Connector、connection 或通用 SQL。"""

    def __init__(self, connector: PostgresServiceConnector) -> None:
        self.__connector = connector

    def capability_kind(self) -> str:
        return "postgres"

    def agent_health_snapshot(self) -> ServiceSnapshotData:
        return self.__connector.agent_health_snapshot()

    def explain_select(self, sql: str) -> str:
        from src.tools.db_tools import ExplainTool

        return ExplainTool(_resource_provider=self.__connector._open_readonly_connection).execute(sql)

    def show_indexes(self, table: str) -> str:
        from src.tools.db_tools import ShowIndexTool

        return ShowIndexTool(_resource_provider=self.__connector._open_readonly_connection).execute(table)

    def show_create_table(self, table: str) -> str:
        from src.tools.db_tools import ShowCreateTableTool

        return ShowCreateTableTool(_resource_provider=self.__connector._open_readonly_connection).execute(table)

    def check_locks(self) -> str:
        from src.tools.db_tools import CheckLockStatusTool

        return CheckLockStatusTool(
            self.__connector._instance_id,
            _resource_provider=self.__connector._open_readonly_connection,
        ).execute()


class PostgresServiceConnector:
    """只读 PostgreSQL 服务快照 Connector，实现 ServiceConnector 协议。"""

    def __init__(
        self,
        dsn: str | None,
        engine: Engine | None = None,
        instance_id: str = "postgres-production",
        title: str = "生产 PostgreSQL 主库",
        dsn_masked_tail: str | None = None,
        binding_origin: BindingOrigin | None = None,
    ) -> None:
        self._dsn = dsn
        self._instance_id = instance_id
        self._title = title
        self._dsn_masked_tail = dsn_masked_tail
        self._binding_origin = binding_origin or BindingOrigin.from_reference(f"registry:{instance_id}")
        self._agent_view = _PostgresReadonlyCapability(self)
        # engine 注入点：测试传假 engine；生产传 create_engine(dsn)。
        self._engine = engine

    def definition(self) -> ServiceDefinitionData:
        """返回 PostgreSQL 服务的静态身份与只读调查边界。"""
        return ServiceDefinitionData(
            id=self._instance_id,
            title=self._title,
            kind="postgres",
            supported_investigations=(
                ServiceInvestigationData(
                    id=SERVICE_HEALTH_PRESSURE_INTENT_ID,
                    title="PostgreSQL 健康与连接压力概览",
                    description="读取固定连接池压力标量。",
                    default_query=SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
                ),
                ServiceInvestigationData(
                    id="postgres_slow_query.v1",
                    title="PostgreSQL 慢查询调查",
                    description="通过只读查询定位慢 SQL 与索引问题。",
                    default_query="生产 PostgreSQL 变慢，请只读排查慢查询。",
                ),
            ),
            action_boundary="只读调查，不执行任何写入或结构变更。",
            session_title="PostgreSQL 慢查询调查",
            has_dsn=self._dsn is not None,
            dsn_masked_tail=self._dsn_masked_tail,
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前有限只读快照；失败/超时返回 unavailable，不抛异常。"""
        observed = datetime.now(UTC)
        if self._dsn is None:
            return self._not_configured(observed)

        engine = self._engine
        owns_engine = engine is None
        try:
            engine = engine or self._create_engine()
            result = self._read_healthy(engine, observed)
        except Exception as error:
            result = self._unavailable(observed, self._failure_code(error))
        if owns_engine and engine is not None:
            try:
                engine.dispose()
            except Exception:
                LOGGER.warning("PostgreSQL 连接清理失败：instance_id=%s", self._instance_id)
        return result

    def agent_capability(self) -> _PostgresReadonlyCapability:
        """复用同一 Connector entry 作为受控 PostgreSQL capability。"""
        return self._agent_view

    def capability_kind(self) -> str:
        """返回封闭 capability 类型。"""
        return "postgres"

    def _open_readonly_connection(self) -> tuple[Any, Engine]:
        """只供代码注册的 PostgreSQL Tool 获取短生命周期只读连接。"""
        engine = self._engine or self._create_engine()
        owns_engine = self._engine is None
        try:
            connection = engine.connect()
            connection.execute(text("SET TRANSACTION READ ONLY"))
            return connection, engine
        except Exception:
            if owns_engine:
                engine.dispose()
            raise

    def binding_origin(self) -> BindingOrigin:
        """返回内部来源指纹，不暴露引用正文。"""
        return self._binding_origin

    def agent_health_snapshot(self) -> ServiceSnapshotData:
        """DBAgent 固定连接压力读取：只执行只读 SET 与两个固定 SELECT。"""
        observed = datetime.now(UTC)
        if self._dsn is None:
            return self._not_configured(observed)
        engine = self._engine
        owns_engine = engine is None
        try:
            engine = engine or self._create_engine()
            with engine.connect() as connection:
                connection.execute(text("SET TRANSACTION READ ONLY"))
                row = connection.execute(
                    text(
                        "SELECT count(*) AS total, "
                        "count(*) FILTER (WHERE state = 'active') AS active, "
                        "count(*) FILTER (WHERE state = 'idle') AS idle, "
                        "count(*) FILTER (WHERE wait_event_type IS NOT NULL AND state <> 'idle') AS waiting "
                        "FROM pg_stat_activity"
                    )
                ).mappings().first()
                maximum_row = connection.execute(
                    text("SELECT setting::int AS max_connections FROM pg_settings WHERE name = 'max_connections'")
                ).mappings().first()
            result = ServiceSnapshotData(
                observed_at=observed,
                mode=ServiceMode.TARGET,
                availability=ServiceAvailability.HEALTHY,
                performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
                server_metrics=ServiceServerMetricsData(
                    source_status=ServiceSourceStatus.AVAILABLE,
                    client_connections=self._metric_int(row, "total"),
                    active_connections=self._metric_int(row, "active"),
                    idle_connections=self._metric_int(row, "idle"),
                    waiting_connections=self._metric_int(row, "waiting"),
                    max_connections=self._metric_int(maximum_row, "max_connections"),
                ),
                database=ServiceDatabaseStateData(
                    source_status=ServiceSourceStatus.AVAILABLE,
                    signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
                ),
            )
            primary_failed = False
        except Exception as error:
            result = self._unavailable(observed, self._failure_code(error))
            primary_failed = True
        if owns_engine and engine is not None:
            try:
                engine.dispose()
            except Exception:
                LOGGER.warning("PostgreSQL Agent 连接清理失败：instance_id=%s", self._instance_id)
                if primary_failed:
                    return self._unavailable(observed, "cleanup_failed")
                return result.model_copy(update={"cleanup_status": "unknown"})
        return result

    def _create_engine(self) -> Engine:
        """创建强制使用 psycopg 驱动且带三秒超时的 PostgreSQL Engine。"""
        # 调用方 health_snapshot 已先判 None；这里显式抛而不用 assert，
        # 因为 python -O 会剥掉 assert，收窄就失效了。异常文本不含 DSN。
        if self._dsn is None:
            raise ValueError("PostgreSQL DSN 未配置")
        return create_read_only_postgres_engine(self._dsn)

    def _read_healthy(self, engine: Engine, observed: datetime) -> ServiceSnapshotData:
        """在只读事务中读取连通性与有限数据库指标。"""
        with engine.connect() as conn:
            conn.execute(text("SET TRANSACTION READ ONLY"))
            conn.execute(text("SELECT 1"))
            try:
                row = conn.execute(
                    text(
                        "SELECT numbackends, xact_commit, xact_rollback, blks_read "
                        "FROM pg_stat_database WHERE datname = current_database()"
                    )
                ).mappings().first()
            except Exception:
                row = None

            statistics = self._read_optional_statement_statistics(conn)

        # statistics 同时装 slow_query_count(int) 与 p50/p95(float)，值类型被推成
        # int | float | None。这里收窄成 int | None，与 ServiceServerMetricsData 对齐。
        raw_slow_query_count = statistics.get("slow_query_count")
        slow_query_count = raw_slow_query_count if isinstance(raw_slow_query_count, int) else None
        return ServiceSnapshotData(
            observed_at=observed,
            mode=ServiceMode.TARGET,
            availability=ServiceAvailability.HEALTHY,
            performance_signal=(
                PerformanceSignal.SLOW_QUERY_DETECTED
                if slow_query_count is not None and slow_query_count > 0
                else PerformanceSignal.NO_SLOW_QUERY_DETECTED
            ),
            server_metrics=ServiceServerMetricsData(
                source_status=ServiceSourceStatus.AVAILABLE,
                window_size=self._metric_int(row, "numbackends"),
                p50_ms=self._metric_float(statistics, "p50_ms"),
                p95_ms=self._metric_float(statistics, "p95_ms"),
                slow_query_count=slow_query_count,
                timeout_count=None,
            ),
            database=ServiceDatabaseStateData(
                source_status=ServiceSourceStatus.AVAILABLE,
                signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
            ),
        )

    @staticmethod
    def _read_optional_statement_statistics(conn: Any) -> dict[str, int | float | None]:
        """尽力读取可选统计扩展；扩展不可用时不影响健康结论。"""
        try:
            row = conn.execute(
                text(
                    "SELECT COALESCE(SUM(calls), 0) AS calls, "
                    "percentile_cont(0.50) WITHIN GROUP "
                    "(ORDER BY mean_exec_time) AS p50_ms, "
                    "percentile_cont(0.95) WITHIN GROUP "
                    "(ORDER BY mean_exec_time) AS p95_ms "
                    "FROM pg_stat_statements"
                )
            ).mappings().first()
        except Exception:
            return {}

        if not row:
            return {}
        calls = row.get("calls")
        return {
            "slow_query_count": int(calls) if calls is not None else None,
            "p50_ms": row.get("p50_ms"),
            "p95_ms": row.get("p95_ms"),
        }

    @staticmethod
    def _metric_int(row: Any, name: str) -> int | None:
        """把数据库指标安全收敛为非负整数。"""
        if not row:
            return None
        value = row.get(name)
        if value is None:
            return None
        return int(value)

    @staticmethod
    def _metric_float(row: Any, name: str) -> float | None:
        """把数据库指标安全收敛为非负浮点数。"""
        if not row:
            return None
        value = row.get(name)
        if value is None:
            return None
        return float(value)

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
