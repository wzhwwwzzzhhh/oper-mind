"""数据库诊断工具：mock 场景与真实 PostgreSQL 只读分支。"""

from __future__ import annotations

import re
import json
from typing import Any

from sqlalchemy import text

from data.scenarios import get_active_scenario
from src.config import load_service_dsn
from src.core.tool_registry import Tool
from src.infrastructure.services.postgres_engine import create_read_only_postgres_engine


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
            plan = plan_payload.get("Plan") if isinstance(plan_payload.get("Plan"), dict) else plan_payload
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


def _explain_mock(sql: str) -> str:
    """保留既有 mock EXPLAIN 的格式与告警行为。"""
    from data.mock_db import explain_sql, extract_table_name

    plan = explain_sql(sql)
    table_name = extract_table_name(sql)
    result = f"EXPLAIN {table_name or '(unknown)'}:\n"
    result += f" 查询类型：{plan['select_type']}\n"
    result += f" 访问类型：{plan['type']}\n"
    result += f" 可能索引：{plan['possible_keys']}\n"
    result += f" 实际索引：{plan['key']}\n"
    result += f" 扫描行数：{plan['rows']}\n"
    result += f" 额外信息：{plan['Extra']}\n"

    warnings = []
    if plan["type"] == "ALL":
        warnings.append("⚠️ 全表扫描，性能风险高")
    if plan["Extra"] and "filesort" in plan["Extra"].lower():
        warnings.append("⚠️ 文件排序，数据量大时性能差")
    if plan["key"] is None and plan["possible_keys"]:
        warnings.append("⚠️ 有可用索引但没使用，可能是函数包裹或类型转换导致")
    if warnings:
        result += "\n" + "\n".join(warnings)
    return result


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
            return _explain_mock(sql)
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
            from data.mock_db import get_indexes

            indexes = get_indexes(table)
            if indexes is None:
                return f"表 '{table}' 不存在或没有索引信息"
            result = f"表 {table} 的索引:\n"
            result += f"{'索引名':<20} {'列名':<15} {'顺序':>5} {'非唯一':>8} {'基数':>10}\n"
            result += "-" * 60 + "\n"
            for index in indexes:
                result += f"{index['Key_name']:<20} {index['Column_name']:<15} {index['Seq_in_index']:>5} {index['Non_unique']:>8} {index['Cardinality']:>10}\n"
            return result

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
            from data.mock_db import get_create_table

            result = get_create_table(table)
            return result if result is not None else f"表 '{table}' 不存在"

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
