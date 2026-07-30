"""P4.1 固定 PostgreSQL 靶场的只读证据读取器。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any, Protocol

import psycopg
from psycopg.rows import dict_row

from src.infrastructure.diagnosis.demo_orders.models import DatabaseEvidenceSnapshot
from src.infrastructure.diagnosis.demo_orders.settings import (
    DemoOrdersEvidenceSettings,
    TARGET_DATABASE,
    TARGET_INDEX,
    TARGET_SCHEMA,
    TARGET_TABLE,
)


class DemoOrdersSourceError(RuntimeError):
    """外部证据源不可用时传递给编排器的安全内部错误。"""


class DemoOrdersDatabaseClient(Protocol):
    """限定于三项固定只读操作的数据库客户端端口。"""

    def current_database(self) -> str:
        """返回服务端确认的当前数据库名。"""

    def target_index_exists(self) -> bool:
        """返回唯一允许检查的订单索引是否存在。"""

    def explain_orders_query(self) -> object:
        """返回唯一固定订单查询的 JSON 计划对象。"""


class PostgresDemoOrdersDatabaseClient:
    """使用 psycopg 访问固定靶场、固定 SQL 的只读客户端。"""

    def __init__(
        self,
        settings: DemoOrdersEvidenceSettings,
        connection_factory: Callable[..., Any] = psycopg.connect,
    ) -> None:
        self._settings = settings
        self._connection_factory = connection_factory

    def current_database(self) -> str:
        """从服务器读取数据库名，以防本地隧道意外指向其他库。"""
        row = self._fetch_one("SELECT current_database() AS database_name")
        name = row.get("database_name")
        if not isinstance(name, str):
            raise DemoOrdersSourceError("数据库只读证据不可用")
        return name

    def target_index_exists(self) -> bool:
        """读取唯一目标索引的存在状态。"""
        row = self._fetch_one(
            """
            SELECT EXISTS (
                SELECT 1
                FROM pg_indexes
                WHERE schemaname = %s
                  AND tablename = %s
                  AND indexname = %s
            ) AS target_index_exists
            """,
            (TARGET_SCHEMA, TARGET_TABLE, TARGET_INDEX),
        )
        return bool(row.get("target_index_exists"))

    def explain_orders_query(self) -> object:
        """执行唯一固定参数化 EXPLAIN，不允许任何模型或用户 SQL。"""
        row = self._fetch_one(
            """
            EXPLAIN (FORMAT JSON)
            SELECT id, order_no, status, total_amount, created_at
            FROM opermind_demo.orders
            WHERE user_id = %s
              AND created_at >= %s
              AND created_at < %s
            ORDER BY created_at DESC
            LIMIT 100
            """,
            (42, "2025-01-01 00:00:00", "2026-01-01 00:00:00"),
        )
        plan = row.get("QUERY PLAN")
        if plan is None:
            raise DemoOrdersSourceError("数据库只读证据不可用")
        return plan

    def _fetch_one(self, statement: str, parameters: tuple[object, ...] = ()) -> dict[str, object]:
        """以限时只读连接执行固定语句，不向上泄露驱动异常。"""
        password = self._settings.database_password
        if self._settings.database_user is None or password is None:
            raise DemoOrdersSourceError("数据库只读证据不可用")
        try:
            with self._connection_factory(
                host=self._settings.database_host,
                port=self._settings.database_port,
                dbname=self._settings.database_name,
                user=self._settings.database_user,
                password=password.get_secret_value(),
                connect_timeout=self._settings.connection_timeout_seconds,
                options=(
                    "-c default_transaction_read_only=on "
                    f"-c statement_timeout={self._settings.query_timeout_milliseconds}"
                ),
                row_factory=dict_row,
            ) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT current_database() AS database_name")
                    target_row = cursor.fetchone()
                    if not isinstance(target_row, dict) or target_row.get("database_name") != TARGET_DATABASE:
                        raise DemoOrdersSourceError("数据库只读证据不可用")
                    cursor.execute(statement, parameters)
                    row = cursor.fetchone()
        except (psycopg.Error, OSError, ValueError) as error:
            raise DemoOrdersSourceError("数据库只读证据不可用") from error
        if not isinstance(row, dict):
            raise DemoOrdersSourceError("数据库只读证据不可用")
        return row


class PostgresEvidenceReader:
    """将固定数据库读取转换为安全快照。"""

    def __init__(self, client: DemoOrdersDatabaseClient) -> None:
        self._client = client

    def collect(self) -> DatabaseEvidenceSnapshot:
        """确认数据库边界、索引状态和计划扫描方式。"""
        if self._client.current_database() != TARGET_DATABASE:
            raise DemoOrdersSourceError("数据库只读证据不可用")
        plan = self._client.explain_orders_query()
        node_types, index_names = _plan_access_paths(plan)
        return DatabaseEvidenceSnapshot(
            observed_at=datetime.now(timezone.utc),
            target_database_confirmed=True,
            target_index_exists=self._client.target_index_exists(),
            plan_uses_seq_scan="Seq Scan" in node_types,
            plan_uses_target_index=TARGET_INDEX in index_names,
        )


def _plan_access_paths(plan: object) -> tuple[set[str], set[str]]:
    """递归提取 JSON 计划的节点类型和索引名，不保留原计划。"""
    node_types: set[str] = set()
    index_names: set[str] = set()
    _collect_plan_access_paths(plan, node_types, index_names)
    return node_types, index_names


def _collect_plan_access_paths(value: object, node_types: set[str], index_names: set[str]) -> None:
    """从嵌套 JSON 值中抽取允许的两个标量字段。"""
    if isinstance(value, list):
        for item in value:
            _collect_plan_access_paths(item, node_types, index_names)
        return
    if not isinstance(value, dict):
        return
    node_type = value.get("Node Type")
    index_name = value.get("Index Name")
    if isinstance(node_type, str):
        node_types.add(node_type)
    if isinstance(index_name, str):
        index_names.add(index_name)
    for nested_value in value.values():
        _collect_plan_access_paths(nested_value, node_types, index_names)
