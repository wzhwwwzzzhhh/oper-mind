"""数据库诊断工具：mock 场景与真实 PostgreSQL 只读分支。"""

from __future__ import annotations

import json
import re
from typing import Any, Literal

from data.scenarios import get_active_scenario
from pydantic import BaseModel, Field
from sqlalchemy import text

from src.config import load_service_dsn
from src.core.tool_registry import Tool
from src.infrastructure.services.postgres_engine import create_read_only_postgres_engine

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class LockWaitChain(BaseModel):
    """一条锁等待链的结构化脱敏事实（不含用户名/客户端 IP/原始 SQL）。"""

    blocked_seconds: int = Field(description="被阻塞会话自 query_start 起的阻塞时长（秒）")
    blocker_xact_seconds: int | None = Field(default=None, description="阻塞源头事务运行时长（秒）；未知为 None")
    lock_type: str = Field(description="锁类型，如 relation / tuple / transactionid")
    lock_mode: str = Field(description="锁模式，如 RowExclusiveLock / AccessShareLock")
    object_name: str = Field(description="相关对象名（表名或锁类型）；非 relation 锁取 locktype")


class LockWaitStatus(BaseModel):
    """锁诊断的结构化结果或诚实降级。"""

    status: Literal["ok", "not_configured", "unavailable"]
    message: str = Field(description="面向用户的摘要/降级文案")
    chain_count: int = Field(default=0, description="锁等待链数量；无等待为 0")
    chains: list[LockWaitChain] = Field(default_factory=list, description="锁等待链明细（脱敏）")
    lock_mode_distribution: dict[str, int] = Field(default_factory=dict, description="锁模式分布")


class ConnectionPoolStatus(BaseModel):
    """连接池诊断的结构化结果或诚实降级。"""

    status: Literal["ok", "not_configured", "unavailable"]
    message: str = Field(description="面向用户的摘要/降级文案")
    total_connections: int = Field(default=0, description="当前连接总数")
    active: int = Field(default=0, description="state=active 的连接数")
    idle: int = Field(default=0, description="state=idle 的连接数")
    waiting: int = Field(default=0, description="wait_event_type 非空且非 idle 的连接数")
    max_connections: int = Field(default=0, description="最大连接数")
    utilization: float = Field(default=0.0, description="利用率（0–1）")
    health: Literal["正常", "接近上限", "已耗尽"] = Field(default="正常", description="健康程度")


def _real_connection(service_id: str | None):
    """按当前配置创建一次短生命周期只读连接；未配置时返回 None。"""
    if not service_id:
        return None
    dsn = load_service_dsn(service_id)
    if not dsn:
        return None
    engine = create_read_only_postgres_engine(dsn)
    try:
        connection = engine.connect()
    except Exception:
        engine.dispose()
        raise
    try:
        connection.execute(text("SET TRANSACTION READ ONLY"))
    except Exception:
        connection.close()
        engine.dispose()
        raise
    return connection, engine


def _is_identifier(value: str) -> bool:
    """判断表名是否为不含 SQL 语法的 PostgreSQL 标识符。"""
    return bool(_IDENTIFIER_RE.fullmatch(value))


def _format_explain(rows: list[dict[str, Any]]) -> str:
    """格式化 PostgreSQL EXPLAIN 的有限结果，不回显原始 SQL。"""
    if not rows:
        return "EXPLAIN 执行计划：\n无计划结果"
    lines = ["EXPLAIN 执行计划："]
    for row in rows:
        plan_payload = row.get("QUERY PLAN") or row.get("query plan")
        if isinstance(plan_payload, str):
            try:
                plan_payload = json.loads(plan_payload)
            except json.JSONDecodeError:
                plan_payload = {"Node Type": plan_payload}
        if isinstance(plan_payload, list) and plan_payload:
            plan_payload = plan_payload[0]
        if isinstance(plan_payload, dict):
            sub_plan = plan_payload.get("Plan")
            plan = sub_plan if isinstance(sub_plan, dict) else plan_payload
            for key in ("Node Type", "Relation Name", "Scan Direction", "Plan Rows", "Total Cost"):
                if key in plan:
                    lines.append(f"  {key}: {plan[key]}")
        else:
            for key in ("Node Type", "Relation Name", "Scan Direction", "Plan Rows", "Total Cost"):
                if key in row:
                    lines.append(f"  {key}: {row[key]}")
    if len(lines) == 1:
        lines.append("  计划字段已按安全边界收敛")
    return "\n".join(lines)


def _table_exists(connection: Any, table: str) -> bool:
    """查询 public schema 中的表是否存在。"""
    result = connection.execute(
        text(
            "SELECT 1 AS exists FROM pg_class c "
            "JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relname = :table "
            "AND c.relkind IN ('r', 'p', 'v', 'm')"
        ),
        {"table": table},
    )
    return bool(result.mappings().all())


def _explain_mock() -> str:
    """只格式化当前场景显式提供的执行计划事实。"""
    scenario = get_active_scenario()
    fact = scenario.db.explain if scenario is not None and scenario.db is not None else None
    if fact is None:
        return "当前场景未提供数据库执行计划事实"
    possible = "、".join(fact.possible_indexes) if fact.possible_indexes else "无"
    used = fact.used_index or "无"
    lines = [
        f"EXPLAIN {fact.table}:",
        f" 访问类型：{fact.access_type}",
        f" 可能索引：{possible}",
        f" 实际索引：{used}",
        f" 扫描行数：{fact.scanned_rows}",
        f" 额外信息：{fact.extra}",
    ]
    if fact.access_type == "ALL":
        lines.append("⚠️ 全表扫描，性能风险高")
    if "filesort" in fact.extra.lower():
        lines.append("⚠️ 文件排序，数据量大时性能差")
    return "\n".join(lines)


class ExplainTool(Tool):
    """执行 EXPLAIN 分析 SQL。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        super().__init__(
            name="explain_sql",
            description="执行 EXPLAIN 分析 SQL 的执行计划，返回访问类型、扫描行数、索引使用情况",
            parameters={
                "type": "object",
                "properties": {"sql": {"type": "string", "description": "要分析的 SELECT 语句"}},
                "required": ["sql"],
            },
        )

    def execute(self, sql: str) -> str:
        """按当前模式返回 mock 或真实 PostgreSQL 执行计划。"""
        if get_active_scenario() is not None:
            return _explain_mock()
        normalized_sql = sql.strip()
        statement_sql = normalized_sql.rstrip(";").rstrip()
        if (
            not normalized_sql.upper().startswith("SELECT")
            or ";" in statement_sql
        ):
            return "只支持分析 SELECT 查询，已拒绝"
        try:
            resource = _real_connection(self._service_id)
            if resource is None:
                return "数据库未选择目标服务" if self._service_id is None else "数据库未配置，无法查询"
            connection, engine = resource
            try:
                result = connection.execute(text(f"EXPLAIN (FORMAT JSON) {sql}"))
                return _format_explain(result.mappings().all())
            finally:
                connection.close()
                engine.dispose()
        except Exception:
            return "数据库不可用"


class ShowIndexTool(Tool):
    """查询 PostgreSQL 表的索引信息。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        super().__init__(
            name="show_index",
            description="查询指定表的 PostgreSQL 索引名称与定义",
            parameters={
                "type": "object",
                "properties": {"table": {"type": "string", "description": "表名，如 orders"}},
                "required": ["table"],
            },
        )

    def execute(self, table: str) -> str:
        """返回 mock 或真实 PostgreSQL 索引信息。"""
        if get_active_scenario() is not None:
            scenario = get_active_scenario()
            fact = scenario.db.table if scenario is not None and scenario.db is not None else None
            if fact is None or fact.table != table:
                return "当前场景未提供该表的数据库索引事实"
            return f"表 {fact.table} 的索引:\n" + "\n".join(f"  {item}" for item in fact.indexes)

        if not _is_identifier(table):
            return "表名格式非法，已拒绝"
        try:
            resource = _real_connection(self._service_id)
            if resource is None:
                return "数据库未选择目标服务" if self._service_id is None else "数据库未配置，无法查询"
            connection, engine = resource
            try:
                if not _table_exists(connection, table):
                    return f"表 '{table}' 不存在"
                rows = connection.execute(
                    text(
                        "SELECT indexname, indexdef FROM pg_indexes "
                        "WHERE schemaname = 'public' AND tablename = :table ORDER BY indexname"
                    ),
                    {"table": table},
                ).mappings().all()
                if not rows:
                    return f"表 '{table}' 没有索引"
                return "表 " + table + " 的索引:\n" + "\n".join(
                    f"{row['indexname']}: {row['indexdef']}" for row in rows
                )
            finally:
                connection.close()
                engine.dispose()
        except Exception:
            return "数据库不可用"


class ShowCreateTableTool(Tool):
    """查询 PostgreSQL 表的建表语句。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        super().__init__(
            name="show_create_table",
            description="查看 PostgreSQL 表的建表语句，包含字段、约束与索引",
            parameters={
                "type": "object",
                "properties": {"table": {"type": "string", "description": "表名，如 orders"}},
                "required": ["table"],
            },
        )

    def execute(self, table: str) -> str:
        """返回 mock 或真实 PostgreSQL 建表语句。"""
        if get_active_scenario() is not None:
            scenario = get_active_scenario()
            fact = scenario.db.table if scenario is not None and scenario.db is not None else None
            if fact is None or fact.table != table:
                return "当前场景未提供该表的数据库结构事实"
            return "表结构摘要 " + fact.table + ":\n" + "\n".join(f"  {column}" for column in fact.columns)

        if not _is_identifier(table):
            return "表名格式非法，已拒绝"
        try:
            resource = _real_connection(self._service_id)
            if resource is None:
                return "数据库未选择目标服务" if self._service_id is None else "数据库未配置，无法查询"
            connection, engine = resource
            try:
                if not _table_exists(connection, table):
                    return f"表 '{table}' 不存在"
                rows = connection.execute(
                    text(
                        "SELECT a.attname AS column_name, "
                        "format_type(a.atttypid, a.atttypmod) AS formatted_type, "
                        "pg_get_expr(ad.adbin, ad.adrelid) AS default_expression, "
                        "a.attnotnull AS is_not_null "
                        "FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "JOIN pg_attribute a ON a.attrelid = c.oid "
                        "LEFT JOIN pg_attrdef ad ON ad.adrelid = c.oid AND ad.adnum = a.attnum "
                        "WHERE n.nspname = 'public' AND c.relname = :table "
                        "AND a.attnum > 0 AND NOT a.attisdropped ORDER BY a.attnum"
                    ),
                    {"table": table},
                ).mappings().all()
                if not rows:
                    return f"表 '{table}' 不存在"
                lines = [f"CREATE TABLE public.{table} ("]
                definitions = []
                seen_constraints: set[str] = set()
                seen_columns: set[str] = set()
                for row in rows:
                    definition = f"{row['column_name']} {row['formatted_type']}"
                    if row["column_name"] in seen_columns:
                        continue
                    seen_columns.add(row["column_name"])
                    if row.get("default_expression") is not None:
                        definition += f" DEFAULT {row['default_expression']}"
                    if row.get("is_not_null"):
                        definition += " NOT NULL"
                    definitions.append(definition)
                constraints = connection.execute(
                    text(
                        "SELECT con.conname AS constraint_name, "
                        "pg_get_constraintdef(con.oid) AS constraint_definition "
                        "FROM pg_constraint con JOIN pg_class c ON c.oid = con.conrelid "
                        "JOIN pg_namespace n ON n.oid = c.relnamespace "
                        "WHERE n.nspname = 'public' AND c.relname = :table "
                        "ORDER BY con.conname"
                    ),
                    {"table": table},
                ).mappings().all()
                for row in constraints:
                    constraint_definition = row.get("constraint_definition")
                    constraint_name = row.get("constraint_name")
                    if constraint_definition:
                        constraint_key = str(constraint_name or constraint_definition)
                        if constraint_key not in seen_constraints:
                            seen_constraints.add(constraint_key)
                            definitions.append(
                                f"CONSTRAINT {constraint_name} {constraint_definition}"
                                if constraint_name
                                else str(constraint_definition)
                            )
                lines.append(",\n".join(f"  {definition}" for definition in definitions))
                lines.append(");")
                indexes = connection.execute(
                    text(
                        "SELECT indexdef FROM pg_indexes "
                        "WHERE schemaname = 'public' AND tablename = :table ORDER BY indexname"
                    ),
                    {"table": table},
                ).mappings().all()
                if indexes:
                    lines.append("索引:")
                    lines.extend(f"  {row['indexdef']}" for row in indexes)
                return "\n".join(lines)
            finally:
                connection.close()
                engine.dispose()
        except Exception:
            return "数据库不可用"


# ---- P7 锁诊断与连接池诊断（只读） ----


def _format_lock_wait(status: LockWaitStatus) -> str:
    """把锁诊断结构化事实格式化为大脑可读文本。"""
    if status.status != "ok":
        return status.message
    if status.chain_count == 0:
        return "锁等待：无锁等待"
    lines = [f"锁等待：存在 {status.chain_count} 条锁等待链"]
    for index, chain in enumerate(status.chains, start=1):
        lines.append(
            f"  链 {index}: 阻塞 {chain.blocked_seconds}s，"
            f"锁类型 {chain.lock_type}，模式 {chain.lock_mode}，"
            f"对象 {chain.object_name}"
        )
        if chain.blocker_xact_seconds is not None:
            lines.append(f"    阻塞源头事务已运行 {chain.blocker_xact_seconds}s")
    if status.lock_mode_distribution:
        distribution = "、".join(f"{mode}×{count}" for mode, count in status.lock_mode_distribution.items())
        lines.append(f"  锁模式分布: {distribution}")
    return "\n".join(lines)


def _format_connection_pool(status: ConnectionPoolStatus) -> str:
    """把连接池诊断结构化事实格式化为大脑可读文本。"""
    if status.status != "ok":
        return status.message
    utilization_percent = status.utilization * 100
    return (
        "连接池状态:\n"
        f"  连接总数: {status.total_connections}\n"
        f"  活跃: {status.active}\n"
        f"  空闲: {status.idle}\n"
        f"  等待: {status.waiting}\n"
        f"  最大连接数: {status.max_connections}\n"
        f"  利用率: {utilization_percent:.1f}%\n"
        f"  健康程度: {status.health}"
    )


class CheckLockStatusTool(Tool):
    """查询当前锁与锁等待，识别阻塞链（只读）。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        self._last_summary = "锁诊断未执行"
        super().__init__(
            name="check_lock_status",
            description="查看当前锁与锁等待，识别阻塞链（阻塞时长、锁类型/模式、相关对象）；默认当前连接数据库",
            parameters={
                "type": "object",
                "properties": {
                    "database": {"type": "string", "description": "数据库名过滤（可选，默认当前连接数据库）"}
                },
            },
        )

    def audit_summary(self) -> str:
        """返回最近一次锁诊断的脱敏审计摘要（供 Trace 展示）。"""
        return self._last_summary

    def execute(self, database: str | None = None) -> str:
        """按当前模式返回 mock 或真实 PostgreSQL 锁诊断事实。"""
        if get_active_scenario() is not None:
            return self._mock_lock()
        if database is not None and not _is_identifier(database):
            self._last_summary = "锁诊断：数据库名非法，已拒绝"
            return "数据库名格式非法，已拒绝"
        try:
            resource = _real_connection(self._service_id)
            if resource is None:
                degraded = "数据库未选择目标服务" if self._service_id is None else "数据库未配置，无法查询"
                self._last_summary = degraded
                return degraded
            connection, engine = resource
            try:
                status = self._real_lock_status(connection, database)
                self._last_summary = self._audit_summary_from(status)
                return _format_lock_wait(status)
            finally:
                connection.close()
                engine.dispose()
        except Exception:
            self._last_summary = "锁诊断不可用"
            return "数据库不可用"

    def _mock_lock(self) -> str:
        """只消费当前场景显式提供的锁事实。"""
        scenario = get_active_scenario()
        summary = scenario.db.lock_summary if scenario is not None and scenario.db is not None else None
        if summary is None:
            self._last_summary = "当前场景未提供数据库锁事实"
            return self._last_summary
        status = LockWaitStatus(status="ok", message=summary)
        self._last_summary = f"{summary}（mock）"
        return _format_lock_wait(status)

    def _real_lock_status(self, connection: Any, database: str | None) -> LockWaitStatus:
        """真实分支：查 pg_locks + pg_stat_activity 识别阻塞链。"""
        params: dict[str, str] = {}
        scope_sql = ""
        if database is not None:
            scope_sql = " AND b.datname = :database"
            params["database"] = database
        elif self._service_id is not None:
            current = connection.execute(text("SELECT current_database() AS name")).mappings().all()
            if current and current[0].get("name"):
                scope_sql = " AND b.datname = :database"
                params["database"] = str(current[0]["name"])
        rows = connection.execute(
            text(
                "SELECT b.pid AS blocked_pid, "
                "EXTRACT(EPOCH FROM (now() - b.query_start))::int AS blocked_seconds, "
                "bl.locktype, bl.mode AS lock_mode, "
                "COALESCE(rel.relname, bl.locktype) AS object_name, "
                "(SELECT max(EXTRACT(EPOCH FROM (now() - a.xact_start))::int) "
                "FROM pg_stat_activity a WHERE a.pid = ANY(pg_blocking_pids(b.pid))) AS blocker_xact_seconds "
                "FROM pg_locks bl "
                "JOIN pg_stat_activity b ON b.pid = bl.pid "
                "LEFT JOIN pg_class rel ON rel.oid = bl.relation "
                "WHERE NOT bl.granted AND b.state = 'active'" + scope_sql
            ),
            params,
        ).mappings().all()
        mode_rows = connection.execute(
            text(
                "SELECT bl.mode AS lock_mode, count(*) AS cnt "
                "FROM pg_locks bl "
                "JOIN pg_stat_activity b ON b.pid = bl.pid "
                "WHERE NOT bl.granted AND b.state = 'active'" + scope_sql
                + " GROUP BY bl.mode ORDER BY cnt DESC"
            ),
            params,
        ).mappings().all()
        chains = [
            LockWaitChain(
                blocked_seconds=int(row.get("blocked_seconds") or 0),
                blocker_xact_seconds=int(row["blocker_xact_seconds"]) if row.get("blocker_xact_seconds") else None,
                lock_type=str(row.get("locktype") or "unknown"),
                lock_mode=str(row.get("lock_mode") or "unknown"),
                object_name=str(row.get("object_name") or "unknown"),
            )
            for row in rows
        ]
        distribution = {str(row["lock_mode"]): int(row["cnt"]) for row in mode_rows}
        message = "锁等待：存在 " + str(len(chains)) + " 条锁等待链" if chains else "锁等待：无锁等待"
        return LockWaitStatus(
            status="ok",
            message=message,
            chain_count=len(chains),
            chains=chains,
            lock_mode_distribution=distribution,
        )

    def _audit_summary_from(self, status: LockWaitStatus) -> str:
        """从结构化事实生成脱敏审计摘要。"""
        if status.status != "ok":
            return status.message
        if status.chain_count == 0:
            return "锁等待：无锁等待"
        max_blocked = max((chain.blocked_seconds for chain in status.chains), default=0)
        return f"锁等待：{status.chain_count} 条链，最长阻塞 {max_blocked}s"


class CheckConnectionPoolTool(Tool):
    """统计当前连接池占用与利用率（只读）。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        self._last_summary = "连接池诊断未执行"
        super().__init__(
            name="check_connection_pool",
            description="统计当前连接总数/活跃/空闲/等待、最大连接数与利用率，标注健康程度",
            parameters={"type": "object", "properties": {}},
        )

    def audit_summary(self) -> str:
        """返回最近一次连接池诊断的脱敏审计摘要（供 Trace 展示）。"""
        return self._last_summary

    def execute(self) -> str:
        """按当前模式返回 mock 或真实 PostgreSQL 连接池事实。"""
        if get_active_scenario() is not None:
            return self._mock_pool()
        try:
            resource = _real_connection(self._service_id)
            if resource is None:
                degraded = "数据库未选择目标服务" if self._service_id is None else "数据库未配置，无法查询"
                self._last_summary = degraded
                return degraded
            connection, engine = resource
            try:
                status = self._real_pool_status(connection)
                self._last_summary = self._audit_summary_from(status)
                return _format_connection_pool(status)
            finally:
                connection.close()
                engine.dispose()
        except Exception:
            self._last_summary = "连接池诊断不可用"
            return "数据库不可用"

    def _mock_pool(self) -> str:
        """只消费当前场景显式提供的连接池事实。"""
        scenario = get_active_scenario()
        fact = scenario.db.pool if scenario is not None and scenario.db is not None else None
        if fact is None:
            self._last_summary = "当前场景未提供数据库连接池事实"
            return self._last_summary
        total, act, idle, wait, maximum = (
            fact.total,
            fact.active,
            fact.idle,
            fact.waiting,
            fact.maximum,
        )
        utilization = (total / maximum) if maximum else 0.0
        health: Literal["正常", "接近上限", "已耗尽"] = (
            "已耗尽" if utilization >= 1.0 else "接近上限" if utilization >= 0.8 else "正常"
        )
        status = ConnectionPoolStatus(
            status="ok",
            message=f"连接池状态: 总数 {total}，利用率 {utilization:.1%}",
            total_connections=total,
            active=act,
            idle=idle,
            waiting=wait,
            max_connections=maximum,
            utilization=round(utilization, 3),
            health=health,
        )
        self._last_summary = f"连接利用率 {utilization:.0%}，{health}（mock）"
        return _format_connection_pool(status)

    def _real_pool_status(self, connection: Any) -> ConnectionPoolStatus:
        """真实分支：统计 pg_stat_activity 占用与 pg_settings 上限。"""
        rows = connection.execute(
            text(
                "SELECT count(*) AS total, "
                "count(*) FILTER (WHERE state = 'active') AS active, "
                "count(*) FILTER (WHERE state = 'idle') AS idle, "
                "count(*) FILTER (WHERE wait_event_type IS NOT NULL AND state <> 'idle') AS waiting "
                "FROM pg_stat_activity"
            )
        ).mappings().all()
        settings = connection.execute(
            text("SELECT setting::int AS max_connections FROM pg_settings WHERE name = 'max_connections'")
        ).mappings().all()
        row = rows[0] if rows else {}
        total = int(row.get("total") or 0)
        maximum = int(settings[0]["max_connections"]) if settings and settings[0].get("max_connections") else 0
        utilization = (total / maximum) if maximum else 0.0
        health: Literal["正常", "接近上限", "已耗尽"] = (
            "已耗尽" if utilization >= 1.0 else "接近上限" if utilization >= 0.8 else "正常"
        )
        return ConnectionPoolStatus(
            status="ok",
            message=f"连接池状态: 总数 {total}，利用率 {utilization:.1%}",
            total_connections=total,
            active=int(row.get("active") or 0),
            idle=int(row.get("idle") or 0),
            waiting=int(row.get("waiting") or 0),
            max_connections=maximum,
            utilization=round(utilization, 3),
            health=health,
        )

    def _audit_summary_from(self, status: ConnectionPoolStatus) -> str:
        """从结构化事实生成脱敏审计摘要。"""
        if status.status != "ok":
            return status.message
        return f"连接利用率 {status.utilization:.0%}，{status.health}"
