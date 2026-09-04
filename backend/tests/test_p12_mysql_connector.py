"""P12 MySQL Connector 固定 SQL、失败与 cleanup 探针。"""

import json

import pytest
from sqlalchemy.exc import OperationalError

from src.application.service_registration import ServiceRegistrationApplicationService
from src.domain.services import ServiceAvailability, ServiceRegistry
from src.infrastructure.services.mysql_connector import MySqlServiceConnector
from src.tools.service_health_tools import MySqlHealthOverviewTool


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Connection:
    def __init__(self, *, missing_uptime: bool = False) -> None:
        self.statements: list[str] = []
        self.missing_uptime = missing_uptime

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if "STATUS" in sql:
            rows = [
                    {"Variable_name": "Uptime", "Value": "10"},
                    {"Variable_name": "Threads_connected", "Value": "4"},
                    {"Variable_name": "Threads_running", "Value": "2"},
                    {"Variable_name": "Slow_queries", "Value": "1"},
                ]
            if self.missing_uptime:
                rows = [row for row in rows if row["Variable_name"] != "Uptime"]
            return _Rows(rows)
        return _Rows([{"Variable_name": "max_connections", "Value": "100"}])


class _Engine:
    def __init__(self, *, fail: bool = False, cleanup_fail: bool = False, missing_uptime: bool = False) -> None:
        self.connection = _Connection(missing_uptime=missing_uptime)
        self.fail = fail
        self.cleanup_fail = cleanup_fail
        self.disposed = False

    def connect(self):
        if self.fail:
            raise TimeoutError("connection failed")
        return self.connection

    def dispose(self):
        self.disposed = True
        if self.cleanup_fail:
            raise RuntimeError("secret cleanup")


def test_mysql_uses_only_two_fixed_statements_and_safe_scalars() -> None:
    engine = _Engine()
    connector = MySqlServiceConnector(
        "mysql+pymysql://readonly@example.invalid",
        engine=engine,
    )
    result = MySqlHealthOverviewTool(connector).execute()
    payload = json.loads(result.output)

    assert engine.connection.statements == [
        "SHOW GLOBAL STATUS WHERE Variable_name IN "
        "('Uptime','Threads_connected','Threads_running','Slow_queries')",
        "SHOW GLOBAL VARIABLES WHERE Variable_name = 'max_connections'",
    ]
    assert payload == {
        "availability": "healthy",
        "current_connections": 4,
        "max_connections": 100,
        "observed_at": payload["observed_at"],
        "running_connections": 2,
        "slow_query_count": 1,
        "source_status": "available",
        "uptime_seconds": 10,
    }
    assert "secret" not in result.output


@pytest.mark.parametrize(
    "dsn",
    [
        "mysql://user@example.invalid",
        "mysql+pymysql://example.invalid",
        "mysql+pymysql://user@example.invalid/business",
        "mysql+pymysql://user@example.invalid?charset=utf8",
    ],
)
def test_mysql_rejects_out_of_scope_dsn(dsn: str) -> None:
    with pytest.raises(ValueError):
        MySqlServiceConnector(dsn)


def test_mysql_not_configured_and_failure_are_safe() -> None:
    assert MySqlServiceConnector(None).health_snapshot().availability is ServiceAvailability.NOT_CONFIGURED
    failed = MySqlServiceConnector(
        "mysql+pymysql://readonly@example.invalid",
        engine=_Engine(fail=True),
    ).health_snapshot()
    assert failed.availability is ServiceAvailability.UNAVAILABLE


def test_mysql_engine_has_fixed_timeouts_and_null_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_create_engine(dsn: str, **kwargs):
        captured.update({"dsn": dsn, **kwargs})
        engine = _Engine()
        captured["created_engine"] = engine
        return engine

    monkeypatch.setattr("src.infrastructure.services.mysql_connector.create_engine", fake_create_engine)
    connector = MySqlServiceConnector("mysql+pymysql://readonly@example.invalid")

    assert connector.health_snapshot().availability is ServiceAvailability.HEALTHY
    created_engine = captured["created_engine"]
    assert isinstance(created_engine, _Engine)
    assert created_engine.disposed is True
    assert captured["pool_pre_ping"] is False
    assert getattr(captured["poolclass"], "__name__", None) == "NullPool"
    assert captured["connect_args"] == {
        "connect_timeout": 3,
        "read_timeout": 3,
        "write_timeout": 3,
        "charset": "utf8mb4",
    }


def test_mysql_missing_required_scalar_fails_closed() -> None:
    connector = MySqlServiceConnector(
        "mysql+pymysql://readonly@example.invalid",
        engine=_Engine(missing_uptime=True),
    )
    snapshot = connector.health_snapshot()
    result = MySqlHealthOverviewTool(connector).execute()
    assert snapshot.availability is ServiceAvailability.UNAVAILABLE
    assert snapshot.failure_code == "malformed_fact"
    assert result.status == "unavailable"
    assert json.loads(result.output)["failure_code"] == "malformed_fact"

    registration = ServiceRegistrationApplicationService(  # type: ignore[arg-type]
        lambda: None,
        ServiceRegistry((connector,)),
        None,
    )
    connection = registration.test_connection("mysql-local")
    assert connection.availability is ServiceAvailability.UNAVAILABLE
    assert connection.error_code == "connection_failed"


def test_mysql_cleanup_failure_is_honest_and_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = MySqlServiceConnector("mysql+pymysql://readonly@example.invalid")
    monkeypatch.setattr(connector, "_create_engine", lambda: _Engine(cleanup_fail=True))
    result = MySqlHealthOverviewTool(connector).execute()
    assert result.status == "ok"
    assert json.loads(result.output)["source_status"] == "cleanup_unknown"
    assert "secret" not in result.output


def test_mysql_primary_and_cleanup_failure_has_closed_code(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = MySqlServiceConnector("mysql+pymysql://readonly@example.invalid")
    monkeypatch.setattr(
        connector,
        "_create_engine",
        lambda: _Engine(fail=True, cleanup_fail=True),
    )
    result = MySqlHealthOverviewTool(connector).execute()
    assert result.status == "unavailable"
    assert json.loads(result.output)["failure_code"] == "cleanup_failed"


def test_mysql_classifies_wrapped_timeout_and_driver_codes() -> None:
    assert MySqlServiceConnector._failure_code(
        OperationalError("statement", {}, TimeoutError("secret"))
    ) == "operation_timeout"
    assert MySqlServiceConnector._failure_code(Exception(1045, "secret")) == "permission_denied"


def test_mysql_duplicate_required_metric_is_malformed() -> None:
    connection = _Connection()
    original_execute = connection.execute

    def duplicate_status(statement):
        rows = original_execute(statement)
        if "STATUS" in str(statement):
            return _Rows([*rows._rows, {"Variable_name": "Uptime", "Value": "11"}])
        return rows

    connection.execute = duplicate_status  # type: ignore[method-assign]
    engine = _Engine()
    engine.connection = connection
    result = MySqlHealthOverviewTool(
        MySqlServiceConnector("mysql+pymysql://readonly@example.invalid", engine=engine)
    ).execute()
    assert result.status == "unavailable"
    assert json.loads(result.output)["failure_code"] == "malformed_fact"
