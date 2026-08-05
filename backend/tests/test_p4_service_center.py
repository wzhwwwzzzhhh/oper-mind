"""P4 服务中心 PostgreSQL Connector 的 API 级冒烟测试。"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import AbstractContextManager
from typing import Any

from src.api.v1.resources import service_resource
from src.api.v1.dependencies import build_v1_services_for_runtime
from src.application.service_center import ServiceCenterApplicationService
from src.domain.services import ServiceAvailability, ServiceRegistry
from src.infrastructure.services.postgres_connector import PostgresServiceConnector


class FakeResult:
    """提供服务 Connector 所需的最小结果接口。"""

    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self._row = row

    def mappings(self) -> FakeResult:
        """模拟 SQLAlchemy mappings 结果。"""
        return self

    def first(self) -> dict[str, Any] | None:
        """返回一行指标。"""
        return self._row


class FakeConnection(AbstractContextManager[Any]):
    """按固定查询顺序返回假结果的只读连接。"""

    def __init__(self, results: Iterator[FakeResult]) -> None:
        self._results = results

    def __enter__(self) -> FakeConnection:
        """进入连接上下文。"""
        return self

    def __exit__(self, *_args: object) -> None:
        """退出连接上下文。"""
        return None

    def execute(self, statement: object) -> FakeResult:
        """忽略查询文本，只返回预置的结构化结果。"""
        sql = str(statement)
        if sql.startswith("SET TRANSACTION READ ONLY") or sql.startswith("SELECT 1"):
            return FakeResult()
        return next(self._results)


class FakeEngine:
    """提供服务快照所需的最小 Engine 接口。"""

    def __init__(self, connection: FakeConnection) -> None:
        self._connection = connection

    def connect(self) -> FakeConnection:
        """返回假只读连接。"""
        return self._connection


def _unused_session_factory() -> Any:
    """服务列表/详情冒烟不触发持久化读取。"""
    raise AssertionError("服务中心列表和详情不应创建应用数据库 Session")


def _service_center(connector: PostgresServiceConnector) -> ServiceCenterApplicationService:
    """用假持久化入口和静态 Connector 构造服务中心。"""
    return ServiceCenterApplicationService(
        _unused_session_factory,
        ServiceRegistry((connector,)),
    )


def test_无凭据服务中心资源可以映射() -> None:
    """无 DSN 时列表和资源映射均返回未配置状态。"""
    views = _service_center(PostgresServiceConnector(None)).list_services()

    assert len(views) == 1
    resource = service_resource(views[0])
    assert resource.id == "postgres-production"
    assert resource.kind == "postgres"
    assert resource.snapshot.availability == ServiceAvailability.NOT_CONFIGURED.value


def test_健康分支服务中心资源可以映射() -> None:
    """健康快照可通过服务资源映射并保留无慢查询信号。"""
    connector = PostgresServiceConnector(
        "postgresql://u:p@h/db",
        engine=FakeEngine(
            FakeConnection(
                iter(
                    [
                        FakeResult({"numbackends": 3}),
                        FakeResult({"calls": 0, "p50_ms": 1.0, "p95_ms": 3.0}),
                    ]
                )
            )
        ),
    )

    resource = service_resource(_service_center(connector).get_service("postgres-production"))

    assert resource.snapshot.availability == ServiceAvailability.HEALTHY.value
    assert resource.snapshot.database.signal == "no_slow_query_detected"


def test_get_service可以映射() -> None:
    """按 PostgreSQL 服务 ID 获取的资源同样可以完成映射。"""
    connector = PostgresServiceConnector(None)
    resource = service_resource(_service_center(connector).get_service("postgres-production"))

    assert resource.id == "postgres-production"
    assert resource.snapshot.availability == ServiceAvailability.NOT_CONFIGURED.value


def test_多实例服务中心各自返回实例定义() -> None:
    """两个 PostgreSQL 实例可以同时注册并保留各自身份。"""
    services = ServiceCenterApplicationService(
        _unused_session_factory,
        ServiceRegistry(
            (
                PostgresServiceConnector(None, instance_id="postgres-production", title="生产 PostgreSQL 主库"),
                PostgresServiceConnector(None, instance_id="postgres-staging", title="预发布 PostgreSQL 主库"),
            )
        ),
    )

    views = services.list_services()

    assert [view.definition.id for view in views] == ["postgres-production", "postgres-staging"]
    assert [view.snapshot.availability for view in views] == [
        ServiceAvailability.NOT_CONFIGURED,
        ServiceAvailability.NOT_CONFIGURED,
    ]


def test_默认装配为每个实例读取各自环境变量(monkeypatch: Any) -> None:
    """默认 v1 装配不会把一个实例的 DSN 复用到另一个实例。"""
    monkeypatch.setenv("OPERMIND_SERVICE_POSTGRES_PRODUCTION_DSN", "production-secret")
    monkeypatch.setenv("OPERMIND_SERVICE_POSTGRES_STAGING_DSN", "staging-secret")

    class Runtime:
        session_factory = _unused_session_factory

    services = build_v1_services_for_runtime(Runtime(), lambda: object())
    connectors = services.service_center._registry.list_connectors()  # type: ignore[union-attr]

    assert [connector.definition().id for connector in connectors] == ["postgres-production", "postgres-staging"]
    assert [connector._dsn for connector in connectors] == ["production-secret", "staging-secret"]  # type: ignore[attr-defined]
