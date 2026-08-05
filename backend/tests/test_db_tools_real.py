"""DBAgent PostgreSQL 真实分支的确定性单元测试。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import patch

from sqlalchemy.exc import OperationalError

from data.scenarios import set_active_scenario
from src.core.tool_gateway import ToolGateway, desensitize
from src.core.tool_registry import ToolRegistry
from src.tools.db_tools import ExplainTool, ShowCreateTableTool, ShowIndexTool


class FakeResult:
    """提供真实工具所需的最小 SQLAlchemy 结果接口。"""

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self._rows = rows or []

    def mappings(self) -> FakeResult:
        """模拟 SQLAlchemy mappings 结果。"""
        return self

    def all(self) -> list[dict[str, Any]]:
        """返回预设映射行。"""
        return self._rows


class FakeConnection(AbstractContextManager[Any]):
    """按执行顺序返回假数据库结果，并记录 SQL。"""

    def __init__(self, results: list[FakeResult]) -> None:
        self._results = iter(results)
        self.statements: list[str] = []
        self.closed = False

    def __enter__(self) -> FakeConnection:
        """进入连接上下文。"""
        return self

    def __exit__(self, *_args: object) -> None:
        """退出连接上下文。"""
        return None

    def close(self) -> None:
        """模拟关闭短生命周期连接。"""
        self.closed = True

    def execute(self, statement: object, parameters: dict[str, str] | None = None) -> FakeResult:
        """记录语句与参数并返回下一项结果。"""
        self.statements.append(f"{statement} {parameters or {}}")
        if str(statement).startswith("SET TRANSACTION READ ONLY"):
            return FakeResult()
        return next(self._results)


class FakeEngine:
    """提供 Engine.connect 的最小假对象。"""

    def __init__(self, connection: FakeConnection | None = None, error: Exception | None = None) -> None:
        self._connection = connection
        self._error = error
        self.disposed = False

    def connect(self) -> FakeConnection:
        """返回连接或抛出预设异常。"""
        if self._error is not None:
            raise self._error
        assert self._connection is not None
        return self._connection

    def dispose(self) -> None:
        """模拟释放 Engine 及其连接池。"""
        self.disposed = True


def test_mock模式保留原有Explain结果() -> None:
    """激活场景时仍使用确定性 mock 数据。"""
    set_active_scenario("S1")

    result = ExplainTool("postgres-production").execute("SELECT * FROM orders WHERE status = 'PENDING'")

    assert "全表扫描" in result


def test真实模式无DSN返回未配置() -> None:
    """真实模式没有 DSN 时不创建连接且返回诚实降级。"""
    with patch("src.tools.db_tools.load_service_dsn", return_value=None):
        result = ShowIndexTool("postgres-production").execute("orders")

    assert result == "数据库未配置，无法查询"


def test连接失败返回不可用且不泄露异常() -> None:
    """连接异常被收敛为中性文案。"""
    engine = FakeEngine(
        error=OperationalError("connect", {}, RuntimeError("postgresql://u:password@host/db")),
    )
    with patch("src.tools.db_tools.load_service_dsn", return_value="postgresql://u:p@host/db"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=engine
    ):
        result = ShowIndexTool("postgres-production").execute("orders")

    assert result == "数据库不可用"
    assert "password" not in result


def test只读初始化失败会释放连接池() -> None:
    """SET TRANSACTION 失败时连接与 Engine 都被释放。"""
    connection = FakeConnection([])
    original_execute = connection.execute

    def fail_read_only(statement: object, parameters: dict[str, str] | None = None) -> FakeResult:
        if str(statement).startswith("SET TRANSACTION READ ONLY"):
            raise RuntimeError("read only setup failed")
        return original_execute(statement, parameters)

    connection.execute = fail_read_only  # type: ignore[method-assign]
    engine = FakeEngine(connection=connection)
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=engine
    ):
        result = ShowIndexTool("postgres-production").execute("orders")

    assert result == "数据库不可用"
    assert engine.disposed


def test三个工具无DSN均返回未配置() -> None:
    """三个真实工具在未配置 DSN 时统一诚实降级。"""
    with patch("src.tools.db_tools.load_service_dsn", return_value=None):
        results = (
            ExplainTool("postgres-production").execute("SELECT 1"),
            ShowIndexTool("postgres-production").execute("orders"),
            ShowCreateTableTool("postgres-production").execute("orders"),
        )

    assert results == ("数据库未配置，无法查询",) * 3


def test三个工具连接失败均返回不可用() -> None:
    """三个真实工具在连接失败时均不抛异常或暴露底层错误。"""
    engine = FakeEngine(error=TimeoutError("postgresql://u:password@host/db"))
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=engine
    ):
        results = (
            ExplainTool("postgres-production").execute("SELECT 1"),
            ShowIndexTool("postgres-production").execute("orders"),
            ShowCreateTableTool("postgres-production").execute("orders"),
        )

    assert results == ("数据库不可用",) * 3


def test_explain拒绝非SELECT且不触库() -> None:
    """非 SELECT 输入在创建连接前被拒绝。"""
    with patch("src.tools.db_tools.create_read_only_postgres_engine") as create_engine:
        result = ExplainTool("postgres-production").execute("DELETE FROM orders")

    assert result == "只支持分析 SELECT 查询，已拒绝"
    create_engine.assert_not_called()


def test_explain拒绝多语句SELECT且不触库() -> None:
    """SELECT 后拼接其他语句时不进入数据库。"""
    with patch("src.tools.db_tools.create_read_only_postgres_engine") as create_engine:
        result = ExplainTool("postgres-production").execute("SELECT 1; DROP TABLE users")

    assert result == "只支持分析 SELECT 查询，已拒绝"
    create_engine.assert_not_called()


def test_explain格式化有限计划字段且不回显原SQL() -> None:
    """真实 EXPLAIN 仅输出计划白名单字段。"""
    connection = FakeConnection(
        [
            FakeResult(
                [{"QUERY PLAN": '[{"Plan": {"Node Type": "Seq Scan", "Relation Name": "orders", "Plan Rows": 10, "Total Cost": 3.2, "Output": ["password=secret"]}}]'}]
            )
        ]
    )
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=FakeEngine(connection=connection)
    ):
        result = ExplainTool("postgres-production").execute("SELECT password FROM orders")

    assert "Seq Scan" in result
    assert "orders" in result
    assert "Plan Rows" in result
    assert "password=secret" not in result


def test非法表名被拒绝且不触库() -> None:
    """空格和分号等表名输入不会进入数据库查询。"""
    with patch("src.tools.db_tools.create_read_only_postgres_engine") as create_engine:
        result = ShowIndexTool("postgres-production").execute("orders; DROP TABLE users")

    assert result == "表名格式非法，已拒绝"
    create_engine.assert_not_called()


def test_show_index格式化真实索引并使用参数化查询() -> None:
    """pg_indexes 行被格式化，表名通过绑定参数传递。"""
    connection = FakeConnection(
        [
            FakeResult([{"exists": 1}]),
            FakeResult([{"indexname": "orders_pkey", "indexdef": "CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (id)"}]),
        ]
    )
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=FakeEngine(connection=connection)
    ):
        result = ShowIndexTool("postgres-production").execute("orders")

    assert "orders_pkey" in result
    assert "CREATE UNIQUE INDEX" in result
    assert ":table" in connection.statements[1]
    assert "orders" in connection.statements[1]
    assert connection.closed


def test_show_index表不存在返回明确文案() -> None:
    """系统目录找不到表时返回不存在文案。"""
    connection = FakeConnection([FakeResult([])])
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=FakeEngine(connection=connection)
    ):
        result = ShowIndexTool("postgres-production").execute("missing_table")

    assert result == "表 'missing_table' 不存在"


def test_show_create_table格式化列与约束() -> None:
    """pg_catalog 行被格式化为 PostgreSQL 建表语句。"""
    connection = FakeConnection(
        [
            FakeResult([{"exists": 1}]),
            FakeResult(
                [
                    {
                        "column_name": "id",
                        "formatted_type": "integer",
                        "default_expression": "nextval('orders_id_seq'::regclass)",
                        "is_not_null": True,
                    }
                ]
            ),
            FakeResult(
                [
                    {"constraint_name": "orders_pkey", "constraint_definition": "PRIMARY KEY (id)"},
                    {"constraint_name": "orders_check", "constraint_definition": "CHECK ((id > 0))"},
                ]
            ),
            FakeResult([{"indexdef": "CREATE INDEX orders_status_idx ON public.orders USING btree (status)"}]),
        ]
    )
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=FakeEngine(connection=connection)
    ):
        result = ShowCreateTableTool("postgres-production").execute("orders")

    assert "CREATE TABLE public.orders" in result
    assert "id integer" in result
    assert "NOT NULL" in result
    assert "PRIMARY KEY (id)" in result
    assert "CONSTRAINT orders_pkey PRIMARY KEY (id)" in result
    assert "CHECK ((id > 0))" in result
    assert "CREATE INDEX orders_status_idx" in result


def test_gateway脱敏真实工具输出中的DSN() -> None:
    """网关脱敏规则不让连接串密码进入工具输出。"""
    registry = ToolRegistry()
    registry.register(ShowIndexTool("postgres-production"))
    gateway = ToolGateway(registry)
    connection = FakeConnection(
        [FakeResult([{"exists": 1}]), FakeResult([{"indexname": "idx", "indexdef": "CREATE INDEX idx ON public.orders (password=secret)"}])]
    )
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine", return_value=FakeEngine(connection=connection)
    ):
        result = gateway.invoke("show_index", '{"table": "orders"}')

    assert "[已脱敏]" in result.output
    assert "secret" not in result.output
    safe_dsn = desensitize("postgresql://user:password@host/db")
    assert "password" not in safe_dsn
    assert "user:password@" not in safe_dsn
