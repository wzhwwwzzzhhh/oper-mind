"""PostgreSQL 只读服务 Connector 的单元测试。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Any
from unittest.mock import patch

from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from src.config import load_service_dsn
from src.domain.services import ServiceAvailability, ServiceRegistry, ServiceSourceStatus
from src.infrastructure.services.postgres_connector import PostgresServiceConnector


class FakeResult:
    """提供 Connector 所需的最小 SQLAlchemy 结果接口。"""

    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row

    def mappings(self) -> FakeResult:
        """模拟 SQLAlchemy 的 mappings 结果。"""
        return self

    def first(self) -> dict[str, Any] | None:
        """返回一行脱敏指标。"""
        return self._row

class FakeConnection(AbstractContextManager[Any]):
    """按查询顺序返回预设结果的假连接。"""

    def __init__(self, results: Iterator[FakeResult]) -> None:
        self._results = results
        self.statements: list[str] = []

    def __enter__(self) -> FakeConnection:
        """进入假连接上下文。"""
        return self

    def __exit__(self, *_args: object) -> None:
        """退出假连接上下文。"""
        return

    def execute(self, statement: object) -> FakeResult:
        """记录 SQL 形状并返回下一项结果。"""
        sql = str(statement)
        self.statements.append(sql)
        if sql.startswith(("SET TRANSACTION READ ONLY", "SELECT 1")):
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

def test_无凭据返回未配置快照() -> None:
    """无 DSN 时不创建连接且返回固定未配置状态。"""
    snapshot = PostgresServiceConnector(None).health_snapshot()

    assert snapshot.availability == ServiceAvailability.NOT_CONFIGURED
    assert snapshot.server_metrics.source_status == ServiceSourceStatus.NOT_CONFIGURED

def test_连接失败返回不可用快照() -> None:
    """连接异常被收敛为不可用，不向调用方抛出。"""
    snapshot = PostgresServiceConnector(
        "postgresql://u:p@h/db",
        engine=FakeEngine(
            error=OperationalError("connect", {}, RuntimeError("connection failed")),
        ),
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.UNAVAILABLE

def test_超时返回不可用快照() -> None:
    """连接超时被收敛为不可用，不向调用方抛出。"""
    snapshot = PostgresServiceConnector(
        "postgresql://u:p@h/db",
        engine=FakeEngine(error=TimeoutError("timed out")),
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.UNAVAILABLE

def test_生产连接强制使用_psycopg驱动() -> None:
    """生产创建 Engine 时把 PostgreSQL URL 固定到 psycopg 驱动。"""
    fake_engine = FakeEngine(error=TimeoutError("timed out"))
    with patch(
        "src.infrastructure.services.postgres_engine.create_engine",
        return_value=fake_engine,
    ) as create_engine:
        snapshot = PostgresServiceConnector("postgresql://u:p@h/db").health_snapshot()

    assert snapshot.availability == ServiceAvailability.UNAVAILABLE
    create_engine.assert_called_once()
    engine_url = create_engine.call_args.args[0]
    assert make_url(engine_url).drivername == "postgresql+psycopg"
    assert create_engine.call_args.kwargs["connect_args"]["connect_timeout"] == 3
    assert fake_engine.disposed

def test_正常连接填充有限指标() -> None:
    """SELECT 1 成功并返回指标时生成健康快照。"""
    connection = FakeConnection(
        iter(
            [
                FakeResult({"numbackends": 8, "xact_commit": 100, "xact_rollback": 2, "blks_read": 40}),
                FakeResult({"calls": 0, "p50_ms": 1.25, "p95_ms": 4.5}),
            ]
        )
    )
    snapshot = PostgresServiceConnector(
        "postgresql://u:p@h/db",
        engine=FakeEngine(connection=connection),
    ).health_snapshot()

    assert snapshot.availability == ServiceAvailability.HEALTHY
    assert snapshot.server_metrics.source_status == ServiceSourceStatus.AVAILABLE
    assert snapshot.server_metrics.window_size == 8
    assert snapshot.server_metrics.slow_query_count == 0
    assert snapshot.server_metrics.p50_ms == 1.25
    assert snapshot.server_metrics.p95_ms == 4.5
    assert snapshot.database.signal.value == "no_slow_query_detected"
    assert connection.statements[0].startswith("SET TRANSACTION READ ONLY")
    assert connection.statements[1].startswith("SELECT 1")

def test_快照不包含凭据或查询原文() -> None:
    """快照序列化只含结构化状态，不携带 DSN 或 SQL 原文。"""
    connection = FakeConnection(iter([FakeResult(None), FakeResult(None)]))
    snapshot = PostgresServiceConnector(
        "postgresql://user:password@host:5432/database",
        engine=FakeEngine(connection=connection),
    ).health_snapshot()
    serialized = str(snapshot.model_dump())

    assert "password" not in serialized
    assert "://" not in serialized
    assert "SELECT 1" not in serialized
    assert "user:password" not in serialized

def test_definition_包含完整静态服务信息() -> None:
    """静态定义包含固定服务 ID、调查能力与边界。"""
    definition = PostgresServiceConnector(None).definition()

    assert definition.id == "postgres-production"
    assert definition.title
    assert definition.kind
    assert definition.supported_investigations
    assert definition.action_boundary
    assert definition.session_title


def test_connector_definition使用实例身份() -> None:
    """不同实例的定义只改变服务身份，不改变只读能力声明。"""
    definition = PostgresServiceConnector(
        None,
        instance_id="postgres-staging",
        title="预发布 PostgreSQL 主库",
    ).definition()

    assert definition.id == "postgres-staging"
    assert definition.title == "预发布 PostgreSQL 主库"
    assert definition.kind == "postgres"


def test_实例凭据环境变量互不串扰(monkeypatch: Any) -> None:
    """每个实例仅读取自身命名空间的 DSN。"""
    monkeypatch.setenv("OPERMIND_SERVICE_POSTGRES_PRODUCTION_DSN", "production-secret")
    monkeypatch.setenv("OPERMIND_SERVICE_POSTGRES_STAGING_DSN", "staging-secret")

    assert load_service_dsn("postgres-production") == "production-secret"
    assert load_service_dsn("postgres-staging") == "staging-secret"


def test_注册表拒绝重复实例_id() -> None:
    """重复服务 ID 不能覆盖已注册 Connector。"""
    first = PostgresServiceConnector(None, instance_id="postgres-staging")
    second = PostgresServiceConnector(None, instance_id="postgres-staging")

    try:
        ServiceRegistry((first, second))
    except ValueError as error:
        assert "唯一" in str(error)
    else:
        raise AssertionError("重复服务 ID 应被拒绝")
