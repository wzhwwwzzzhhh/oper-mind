"""静态注册的 PostgreSQL 只读 Connector。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.domain.services import (
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
)
from src.infrastructure.services.postgres_engine import create_read_only_postgres_engine

class PostgresServiceConnector:
    """只读 PostgreSQL 服务快照 Connector，实现 ServiceConnector 协议。"""

    def __init__(
        self,
        dsn: str | None,
        engine: Engine | None = None,
        instance_id: str = "postgres-production",
        title: str = "生产 PostgreSQL 主库",
    ) -> None:
        self._dsn = dsn
        self._instance_id = instance_id
        self._title = title
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
                    id="postgres_slow_query.v1",
                    title="PostgreSQL 慢查询调查",
                    description="通过只读查询定位慢 SQL 与索引问题。",
                    default_query="生产 PostgreSQL 变慢，请只读排查慢查询。",
                ),
            ),
            action_boundary="只读调查，不执行任何写入或结构变更。",
            session_title="PostgreSQL 慢查询调查",
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        """读取当前有限只读快照；失败/超时返回 unavailable，不抛异常。"""
        observed = datetime.now(timezone.utc)
        if self._dsn is None:
            return self._not_configured(observed)

        engine = self._engine
        owns_engine = engine is None
        try:
            engine = engine or self._create_engine()
            return self._read_healthy(engine, observed)
        except Exception:
            return self._unavailable(observed)
        finally:
            if owns_engine and engine is not None:
                engine.dispose()

    def _create_engine(self) -> Engine:
        """创建强制使用 psycopg 驱动且带三秒超时的 PostgreSQL Engine。"""
        assert self._dsn is not None
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

        slow_query_count = statistics.get("slow_query_count")
        return ServiceSnapshotData(
            observed_at=observed,
            mode=ServiceMode.TARGET,
            availability=ServiceAvailability.HEALTHY,
            performance_signal=(
                PerformanceSignal.SLOW_QUERY_DETECTED
                if isinstance(slow_query_count, int) and slow_query_count > 0
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
