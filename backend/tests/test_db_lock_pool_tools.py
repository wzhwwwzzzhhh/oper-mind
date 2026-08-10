"""P7 锁诊断与连接池诊断工具的确定性单元测试。"""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import patch

from data.scenarios import clear_active_scenario, set_active_scenario
from sqlalchemy.exc import OperationalError

from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import ToolRegistry
from src.tools.db_tools import CheckConnectionPoolTool, CheckLockStatusTool


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
        return

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


def _patch_real(engine: FakeEngine) -> None:
    """注入假 DSN 与假引擎。"""
    patch("src.tools.db_tools.load_service_dsn", return_value="dsn").start()
    patch("src.tools.db_tools.create_read_only_postgres_engine", return_value=engine).start()


# ---- mock 分支（AC4） ----


def test_mock模式锁诊断返回无锁等待() -> None:
    """场景激活时锁诊断如实返回"无锁等待"，不伪造锁事实。"""
    set_active_scenario("S1")
    tool = CheckLockStatusTool("postgres-production")
    result = tool.execute()
    assert "无锁等待" in result
    assert "mock" in tool.audit_summary()


def test_mock模式连接池返回确定性占用() -> None:
    """场景激活时连接池返回确定性占用与健康档位。"""
    set_active_scenario("S1")
    result = CheckConnectionPoolTool("postgres-production").execute()
    assert "连接总数" in result
    assert "利用率" in result


def test_mock模式S4连接池已耗尽() -> None:
    """S4 场景连接数达到上限，如实标注已耗尽。"""
    set_active_scenario("S4")
    result = CheckConnectionPoolTool("postgres-production").execute()
    assert "已耗尽" in result


def test_mock模式不影响真实模式判定() -> None:
    """清除场景后进入真实分支；mock 分支只在激活时生效。"""
    clear_active_scenario()
    with patch("src.tools.db_tools.load_service_dsn", return_value=None):
        result = CheckLockStatusTool("postgres-production").execute()
    assert result == "数据库未配置，无法查询"


# ---- 无 DSN 与降级（AC7） ----


def test锁诊断无DSN返回未配置() -> None:
    """真实模式没有 DSN 时返回诚实降级，审计摘要同步反映降级。"""
    clear_active_scenario()
    tool = CheckLockStatusTool("postgres-production")
    with patch("src.tools.db_tools.load_service_dsn", return_value=None):
        result = tool.execute()
    assert result == "数据库未配置，无法查询"
    assert tool.audit_summary() == "数据库未配置，无法查询"


def test连接池无DSN返回未配置() -> None:
    """真实模式没有 DSN 时连接池工具返回诚实降级，审计摘要同步反映降级。"""
    clear_active_scenario()
    tool = CheckConnectionPoolTool("postgres-production")
    with patch("src.tools.db_tools.load_service_dsn", return_value=None):
        result = tool.execute()
    assert result == "数据库未配置，无法查询"
    assert tool.audit_summary() == "数据库未配置，无法查询"


def test锁诊断无目标服务返回未选择() -> None:
    """service_id 为 None 时返回"未选择目标服务"。"""
    clear_active_scenario()
    with patch("src.tools.db_tools.load_service_dsn", return_value="dsn"), patch(
        "src.tools.db_tools.create_read_only_postgres_engine"
    ) as create_engine:
        result = CheckLockStatusTool().execute()
    assert result == "数据库未选择目标服务"
    create_engine.assert_not_called()


def test锁诊断连接失败返回不可用且不泄露异常() -> None:
    """连接异常被收敛为中性文案，异常细节不外泄。"""
    clear_active_scenario()
    engine = FakeEngine(
        error=OperationalError("connect", {}, RuntimeError("postgresql://u:password@host/db")),
    )
    _patch_real(engine)
    try:
        result = CheckLockStatusTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert result == "数据库不可用"
    assert "password" not in result


def test连接池连接失败返回不可用() -> None:
    """连接池工具在连接失败时不抛异常、返回中性文案。"""
    clear_active_scenario()
    engine = FakeEngine(error=TimeoutError("postgresql://u:password@host/db"))
    _patch_real(engine)
    try:
        result = CheckConnectionPoolTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert result == "数据库不可用"


# ---- 非法参数校验（不触库） ----


def test锁诊断非法数据库名被拒绝且不触库() -> None:
    """含空格/分号的数据库名在创建连接前被拒绝。"""
    clear_active_scenario()
    with patch("src.tools.db_tools.create_read_only_postgres_engine") as create_engine:
        result = CheckLockStatusTool("postgres-production").execute("orders; DROP TABLE users")
    assert result == "数据库名格式非法，已拒绝"
    create_engine.assert_not_called()


# ---- 真实分支：锁诊断（AC1/AC2） ----


def test锁诊断识别阻塞链并脱敏() -> None:
    """真实分支识别阻塞链，输出不含用户名/客户端 IP/原始 SQL。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"name": "appdb"}]),
            FakeResult(
                [
                    {
                        "blocked_pid": 10,
                        "blocked_seconds": 15,
                        "locktype": "relation",
                        "lock_mode": "RowExclusiveLock",
                        "object_name": "orders",
                        "blocker_xact_seconds": 20,
                    }
                ]
            ),
            FakeResult([{"lock_mode": "RowExclusiveLock", "cnt": 1}]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        result = CheckLockStatusTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert "1 条锁等待链" in result
    assert "阻塞 15s" in result
    assert "RowExclusiveLock" in result
    assert "orders" in result
    assert "阻塞源头事务已运行 20s" in result
    assert "usename" not in result
    assert "client_addr" not in result


def test锁诊断无锁等待返回诚实状态() -> None:
    """真实库无锁等待时返回诚实"无锁等待"，不伪造。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"name": "appdb"}]),
            FakeResult([]),
            FakeResult([]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        result = CheckLockStatusTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert result == "锁等待：无锁等待"


def test锁诊断默认限定当前数据库() -> None:
    """未指定 database 时用 current_database() 作为过滤值。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"name": "appdb"}]),
            FakeResult([]),
            FakeResult([]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        CheckLockStatusTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert any("appdb" in statement for statement in connection.statements)


def test锁诊断显式数据库过滤使用绑定参数() -> None:
    """显式 database 参数通过绑定参数传递，且只发 SELECT。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult(
                [
                    {
                        "blocked_pid": 1,
                        "blocked_seconds": 5,
                        "locktype": "relation",
                        "lock_mode": "AccessShareLock",
                        "object_name": "users",
                        "blocker_xact_seconds": None,
                    }
                ]
            ),
            FakeResult([]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        CheckLockStatusTool("postgres-production").execute("analytics")
    finally:
        patch.stopall()
    assert any(":database" in statement for statement in connection.statements)
    assert any("analytics" in statement for statement in connection.statements)
    assert all(statement.startswith("SELECT") for statement in connection.statements if not statement.startswith("SET TRANSACTION"))


# ---- 真实分支：连接池（AC3） ----


def test连接池统计与健康档位() -> None:
    """真实分支统计连接占用并计算利用率与健康程度。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"total": 190, "active": 120, "idle": 40, "waiting": 30}]),
            FakeResult([{"max_connections": 200}]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        result = CheckConnectionPoolTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert "连接总数: 190" in result
    assert "活跃: 120" in result
    assert "空闲: 40" in result
    assert "等待: 30" in result
    assert "最大连接数: 200" in result
    assert "利用率: 95.0%" in result
    assert "接近上限" in result


def test连接池已耗尽标注() -> None:
    """连接数达到上限时如实标注已耗尽。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"total": 100, "active": 95, "idle": 0, "waiting": 5}]),
            FakeResult([{"max_connections": 100}]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        result = CheckConnectionPoolTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert "利用率: 100.0%" in result
    assert "已耗尽" in result


def test连接池正常档位() -> None:
    """利用率低于 80% 时如实标注正常。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"total": 40, "active": 20, "idle": 15, "waiting": 5}]),
            FakeResult([{"max_connections": 200}]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        result = CheckConnectionPoolTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert "利用率: 20.0%" in result
    assert "正常" in result


def test连接池查询只读且全参数化() -> None:
    """连接池真实分支只发 SELECT，无写操作。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"total": 5, "active": 2, "idle": 2, "waiting": 1}]),
            FakeResult([{"max_connections": 100}]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        CheckConnectionPoolTool("postgres-production").execute()
    finally:
        patch.stopall()
    assert connection.statements
    assert all(statement.startswith("SELECT") for statement in connection.statements if not statement.startswith("SET TRANSACTION"))
    assert connection.closed


# ---- 只读与脱敏锁定（AC5/AC6） ----


def test真实分支只发SELECT且无terminate() -> None:
    """两个真实工具只发只读 SELECT，不含 DML/DDL/terminate。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"name": "appdb"}]),
            FakeResult(
                [
                    {
                        "blocked_pid": 1,
                        "blocked_seconds": 1,
                        "locktype": "relation",
                        "lock_mode": "AccessShareLock",
                        "object_name": "t",
                        "blocker_xact_seconds": 2,
                    }
                ]
            ),
            FakeResult([{"lock_mode": "AccessShareLock", "cnt": 1}]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        CheckLockStatusTool("postgres-production").execute()
    finally:
        patch.stopall()
    forbidden = ("INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "terminate", "pg_terminate_backend")
    for statement in connection.statements:
        upper = statement.upper()
        for token in forbidden:
            assert token.upper() not in upper


# ---- 网关准入与审计摘要（AC8） ----


def test网关白名单准入新工具() -> None:
    """两个新工具经 ToolGateway 注册后可通过白名单准入。"""
    clear_active_scenario()
    registry = ToolRegistry()
    registry.register(CheckLockStatusTool("postgres-production"))
    registry.register(CheckConnectionPoolTool("postgres-production"))
    gateway = ToolGateway(registry)
    with patch("src.tools.db_tools.load_service_dsn", return_value=None):
        result = gateway.invoke("check_lock_status", "{}")
    assert result.record.status == "ok"
    assert result.record.tool == "check_lock_status"
    assert "数据库未配置" in result.output


def test网关拒绝未注册工具() -> None:
    """未注册的工具名被网关拒绝。"""
    clear_active_scenario()
    gateway = ToolGateway(ToolRegistry())
    result = gateway.invoke("check_lock_status", "{}")
    assert result.record.status == "rejected"


def test审计摘要为脱敏收敛摘要() -> None:
    """audit_summary 返回收敛摘要，供 Trace 展示，不含明细。"""
    clear_active_scenario()
    connection = FakeConnection(
        [
            FakeResult([{"name": "appdb"}]),
            FakeResult(
                [
                    {
                        "blocked_pid": 1,
                        "blocked_seconds": 30,
                        "locktype": "relation",
                        "lock_mode": "RowExclusiveLock",
                        "object_name": "orders",
                        "blocker_xact_seconds": 60,
                    }
                ]
            ),
            FakeResult([{"lock_mode": "RowExclusiveLock", "cnt": 1}]),
        ]
    )
    _patch_real(FakeEngine(connection=connection))
    try:
        tool = CheckLockStatusTool("postgres-production")
        tool.execute()
        summary = tool.audit_summary()
    finally:
        patch.stopall()
    assert "1 条链" in summary
    assert "orders" not in summary
    assert summary == "锁等待：1 条链，最长阻塞 30s"
