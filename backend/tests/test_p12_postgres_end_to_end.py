"""P12 PostgreSQL binding 到 DBAgent Tool 菜单的离线接线证据。"""

import json
import math
import time
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg.errors import InsufficientPrivilege, InvalidPassword, QueryCanceled
from sqlalchemy.exc import OperationalError

from scripts.run_p12_real_readonly_acceptance import DeterministicLocalDriver
from src.agents.db_agent import DBAgent
from src.application.contracts import CreateRunCommand
from src.application.errors import ServiceContextRequiredError
from src.application.service_center import CreateServiceSessionCommand
from src.application.service_registration import RegisterServiceCommand
from src.core.bootstrap import build_coordinator
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import Tool, ToolRegistry
from src.domain.diagnosis import RUN_TERMINAL_STATUSES, RunEventType, RunStatus
from src.domain.services import (
    SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
    BindingOrigin,
    BoundServiceCapabilities,
)
from src.infrastructure.persistence.database import Base, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyRunEventRepository,
)
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
from src.tools.db_tools import CheckLockStatusTool, ExplainTool
from src.tools.service_health_tools import PostgresHealthOverviewTool


class _Llm:
    pass


class _Capability:
    def capability_kind(self):
        return "postgres"

    def agent_health_snapshot(self):
        raise AssertionError("构造 Agent 不应访问服务")

    def explain_select(self, sql):
        raise AssertionError(sql)

    def show_indexes(self, table):
        raise AssertionError(table)

    def show_create_table(self, table):
        raise AssertionError(table)

    def check_locks(self):
        raise AssertionError("构造 Agent 不应访问服务")


def test_bound_postgres_health_investigation_exposes_only_health_tool() -> None:
    capability = _Capability()
    agent = DBAgent(
        _Llm(),
        service_id="pg.dynamic",
        binding=BoundServiceCapabilities(
            service_id="pg.dynamic",
            kind="postgres",
            supported_investigations=frozenset({"service_health_pressure.v1"}),
            capability=capability,
        ),
        enable_long_term_memory=False,
    )

    health_tools = agent._tool_registry_for_query(SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY)
    assert [item["function"]["name"] for item in health_tools.get_schemas()] == [
        "check_connection_pool"
    ]
    assert [item["function"]["name"] for item in agent.tools.get_schemas()] == [
        "explain_sql",
        "show_index",
        "show_create_table",
        "check_lock_status",
    ]
    assert agent._tool_timeout_by_name == {"check_connection_pool": 15.0}


def test_agent_rejects_service_id_binding_mismatch_before_access() -> None:
    try:
        DBAgent(
            _Llm(),
            service_id="other",
            binding=BoundServiceCapabilities(
                service_id="pg.dynamic",
                kind="postgres",
                supported_investigations=frozenset({"service_health_pressure.v1"}),
                capability=_Capability(),
            ),
            enable_long_term_memory=False,
        )
    except ValueError as error:
        assert "不一致" in str(error)
    else:
        raise AssertionError("service_id 不匹配必须失败关闭")


class _SlowTool(Tool):
    def __init__(self, name: str) -> None:
        super().__init__(name, "slow", {"type": "object", "properties": {}})

    def execute(self) -> str:
        time.sleep(0.04)
        return "late"


def test_gateway_per_tool_budget_does_not_change_default_timeout() -> None:
    registry = ToolRegistry()
    registry.register(_SlowTool("health"))
    registry.register(_SlowTool("legacy"))
    gateway = ToolGateway(registry, timeout_seconds=0.01, timeout_by_tool={"health": 0.1})
    try:
        assert gateway.invoke("health", "{}").record.status == "ok"
        assert gateway.invoke("legacy", "{}").record.status == "timeout"
    finally:
        gateway.shutdown()


@pytest.mark.parametrize("budget", [0, -1, math.nan, math.inf, True, "1"])
def test_gateway_rejects_invalid_tool_budget(budget: object) -> None:
    registry = ToolRegistry()
    registry.register(_SlowTool("health"))
    with pytest.raises(ValueError, match="有限正数"):
        ToolGateway(registry, timeout_by_tool={"health": budget})  # type: ignore[dict-item]


def test_gateway_rejects_budget_for_unregistered_tool() -> None:
    with pytest.raises(ValueError, match="未注册"):
        ToolGateway(ToolRegistry(), timeout_by_tool={"missing": 1.0})


class _Rows:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def all(self):
        return [self.row]


class _Connection:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, statement):
        sql = str(statement)
        self.statements.append(sql)
        if sql == "SET TRANSACTION READ ONLY":
            return _Rows(None)
        if "pg_stat_activity" in sql:
            return _Rows({"total": 5, "active": 2, "idle": 2, "waiting": 1})
        return _Rows({"max_connections": 100})

    def close(self):
        return None


class _Engine:
    def __init__(self, *, cleanup_fail: bool = False, connect_fail: bool = False) -> None:
        self.connection = _Connection()
        self.cleanup_fail = cleanup_fail
        self.connect_fail = connect_fail

    def connect(self):
        if self.connect_fail:
            raise TimeoutError("secret timeout")
        return self.connection

    def dispose(self):
        if self.cleanup_fail:
            raise RuntimeError("secret cleanup")


class _RepeatHealthCallsDriver:
    def chat(self, messages, tools=None, **kwargs):
        del messages, tools, kwargs
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "first",
                    "type": "function",
                    "function": {"name": "check_connection_pool", "arguments": "{}"},
                },
                {
                    "id": "second",
                    "type": "function",
                    "function": {"name": "check_connection_pool", "arguments": "{}"},
                },
            ],
        }


def test_postgres_health_query_executes_at_most_one_tool_call() -> None:
    engine = _Engine()
    connector = PostgresServiceConnector(
        "postgresql://placeholder",
        engine=engine,  # type: ignore[arg-type]
        instance_id="pg.dynamic",
    )
    agent = DBAgent(
        _RepeatHealthCallsDriver(),  # type: ignore[arg-type]
        service_id="pg.dynamic",
        binding=BoundServiceCapabilities(
            service_id="pg.dynamic",
            kind="postgres",
            supported_investigations=frozenset(
                {"postgres_slow_query.v1", "service_health_pressure.v1"}
            ),
            capability=connector.agent_capability(),
        ),
        enable_long_term_memory=False,
    )

    assert agent.run(SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY) == "本次只读调查已达到工具调用上限"
    assert len(agent.get_tool_invocations()) == 1
    assert len(engine.connection.statements) == 3


def test_postgres_bound_health_executes_readonly_set_and_two_fixed_queries() -> None:
    engine = _Engine()
    connector = PostgresServiceConnector("postgresql://placeholder", engine=engine)  # type: ignore[arg-type]
    result = PostgresHealthOverviewTool(connector).execute()
    payload = json.loads(result.output)

    assert len(engine.connection.statements) == 3
    assert engine.connection.statements[0] == "SET TRANSACTION READ ONLY"
    assert "FROM pg_stat_activity" in engine.connection.statements[1]
    assert "FROM pg_settings" in engine.connection.statements[2]
    assert payload == {
        "active_connections": 2,
        "availability": "healthy",
        "idle_connections": 2,
        "max_connections": 100,
        "observed_at": payload["observed_at"],
        "source_status": "available",
        "total_connections": 5,
        "waiting_connections": 1,
        "utilization": 0.05,
        "health": "normal",
    }


def test_postgres_cleanup_failure_is_honest_and_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = PostgresServiceConnector("postgresql://placeholder")
    monkeypatch.setattr(connector, "_create_engine", lambda: _Engine(cleanup_fail=True))
    result = PostgresHealthOverviewTool(connector).execute()
    assert result.status == "ok"
    assert json.loads(result.output)["source_status"] == "cleanup_unknown"
    assert "secret" not in result.output


def test_postgres_primary_and_cleanup_failure_has_closed_code(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = PostgresServiceConnector("postgresql://placeholder")
    monkeypatch.setattr(
        connector,
        "_create_engine",
        lambda: _Engine(cleanup_fail=True, connect_fail=True),
    )
    result = PostgresHealthOverviewTool(connector).execute()
    assert result.status == "unavailable"
    assert json.loads(result.output)["failure_code"] == "cleanup_failed"


def test_postgres_classifies_wrapped_timeout_and_authentication() -> None:
    authentication_error = type("AuthenticationError", (Exception,), {})()
    assert PostgresServiceConnector._failure_code(
        OperationalError("statement", {}, TimeoutError("secret"))
    ) == "operation_timeout"
    assert PostgresServiceConnector._failure_code(authentication_error) == "permission_denied"
    assert PostgresServiceConnector._failure_code(InsufficientPrivilege("secret")) == "permission_denied"
    assert PostgresServiceConnector._failure_code(InvalidPassword("secret")) == "permission_denied"
    assert PostgresServiceConnector._failure_code(QueryCanceled("secret")) == "operation_timeout"


def test_bound_postgres_ignores_global_scenario_and_uses_capability() -> None:
    from data.scenarios import clear_active_scenario, set_active_scenario

    engine = _Engine()
    connector = PostgresServiceConnector("postgresql://placeholder", engine=engine)  # type: ignore[arg-type]
    set_active_scenario("S2")
    try:
        result = PostgresHealthOverviewTool(connector).execute()
    finally:
        clear_active_scenario()
    assert result.status == "ok"
    assert any("pg_stat_activity" in statement for statement in engine.connection.statements)


def test_bound_legacy_postgres_tool_ignores_global_scenario() -> None:
    from data.scenarios import clear_active_scenario, set_active_scenario

    engine = _Engine()
    connector = PostgresServiceConnector("postgresql://placeholder", engine=engine)  # type: ignore[arg-type]
    capability = connector.agent_capability()
    set_active_scenario("S2")
    try:
        output = ExplainTool("pg.dynamic", capability).execute("SELECT 1")
    finally:
        clear_active_scenario()
    assert "EXPLAIN 执行计划" in output
    assert any(statement.startswith("EXPLAIN (FORMAT JSON) SELECT 1") for statement in engine.connection.statements)


def test_bound_lock_adapter_forces_current_database_scope() -> None:
    class _LockRows:
        def __init__(self, rows):
            self.rows = rows

        def mappings(self):
            return self

        def all(self):
            return self.rows

    class _LockConnection:
        def __init__(self, current_rows=None) -> None:
            self.calls: list[tuple[str, dict[str, str] | None]] = []
            self.current_rows = [{"name": "bound_db"}] if current_rows is None else current_rows

        def execute(self, statement, params=None):
            sql = str(statement)
            self.calls.append((sql, params))
            if "current_database()" in sql:
                return _LockRows(self.current_rows)
            return _LockRows([])

        def close(self):
            return None

    class _LockEngine:
        def __init__(self, current_rows=None) -> None:
            self.connection = _LockConnection(current_rows)

        def connect(self):
            return self.connection

        def dispose(self):
            return None

    engine = _LockEngine()
    connector = PostgresServiceConnector(
        "postgresql://placeholder",
        engine=engine,  # type: ignore[arg-type]
        instance_id="pg.dynamic",
    )
    capability = connector.agent_capability()
    tool = CheckLockStatusTool("pg.dynamic", capability)

    assert tool.parameters == {"type": "object", "properties": {}, "additionalProperties": False}
    assert "无锁等待" in tool.execute()
    scoped = [(sql, params) for sql, params in engine.connection.calls if "FROM pg_locks" in sql]
    assert len(scoped) == 2
    assert all("b.datname = :database" in sql for sql, _ in scoped)
    assert all(params == {"database": "bound_db"} for _, params in scoped)

    for malformed_rows in ([], [{}], [{"name": ""}], [{"name": "one"}, {"name": "two"}]):
        malformed_engine = _LockEngine(malformed_rows)
        malformed_connector = PostgresServiceConnector(
            "postgresql://placeholder",
            engine=malformed_engine,  # type: ignore[arg-type]
            instance_id="pg.dynamic",
        )
        malformed_output = CheckLockStatusTool(
            "pg.dynamic",
            malformed_connector.agent_capability(),
        ).execute()
        assert "范围不可用" in malformed_output
        assert len(malformed_engine.connection.calls) == 2  # SET READ ONLY + current_database
        assert not any("FROM pg_locks" in sql for sql, _ in malformed_engine.connection.calls)


def test_dynamic_postgres_registration_to_run_uses_one_binding_and_one_terminal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.api.v1 import dependencies

    test_master_material = "-".join(("p12", "test", "master", "material")) + "-" + ("0" * 32)
    monkeypatch.setenv("OPERMIND_SECRET_KEY", test_master_material)
    runtime = create_persistence_runtime(f"sqlite:///{(tmp_path / 'p12-e2e.sqlite3').as_posix()}")
    Base.metadata.create_all(runtime.engine)
    engine = _Engine()

    def connector_factory(kind, dsn, instance_id, title, masked_tail, origin):
        assert kind == "postgres"
        return PostgresServiceConnector(
            dsn,
            engine=engine,  # type: ignore[arg-type]
            instance_id=instance_id,
            title=title,
            dsn_masked_tail=masked_tail,
            binding_origin=origin,
        )

    monkeypatch.setattr(dependencies, "build_service_connector", connector_factory)

    def coordinator_factory(service_id, binding):
        return build_coordinator(
            DeterministicLocalDriver("check_connection_pool"),
            service_id=service_id,
            binding=binding,
        )

    services = dependencies.build_v1_services_for_runtime(runtime, coordinator_factory)
    registration = services.service_registration
    registry = services.service_registry
    center = services.service_center
    assert registration is not None and registry is not None and center is not None
    registration.create(
        RegisterServiceCommand(
            kind="postgres",
            instance_id="pg.dynamic",
            title="动态 PG",
            dsn="postgresql://readonly:masked@example.invalid/db",
        )
    )
    assert registration.test_connection("pg.dynamic").availability.value == "healthy"
    binding = registry.resolve_binding("pg.dynamic", expected_kind="postgres")
    assert binding.origin == BindingOrigin.from_reference("registry:pg.dynamic")

    session_data = center.create_service_session(CreateServiceSessionCommand(service_id="pg.dynamic"))
    accepted = services.run_service.accept_run(
        CreateRunCommand(
            session_id=session_data.id,
            query=SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
            idempotency_key=uuid4(),
            service_id="pg.dynamic",
        )
    )
    completed = services.run_service.execute_run(accepted.run.id)
    assert completed.status is RunStatus.SUCCEEDED
    assert completed.status in RUN_TERMINAL_STATUSES

    database_session = runtime.session_factory()
    try:
        events = SqlAlchemyRunEventRepository(database_session).list_by_run(
            completed.id, cursor=None, limit=100
        ).items
        result = SqlAlchemyDiagnosisResultRepository(database_session).get_by_run_id(completed.id)
    finally:
        database_session.close()
    terminal = [
        event
        for event in events
        if event.type in {RunEventType.RUN_SUCCEEDED, RunEventType.RUN_FAILED, RunEventType.RUN_CANCELLED}
    ]
    assert [event.type for event in terminal] == [RunEventType.RUN_SUCCEEDED]
    tool_events = [event for event in events if event.type is RunEventType.TOOL_INVOKED]
    assert len(tool_events) == 1
    assert tool_events[0].data["service_id"] == "pg.dynamic"
    assert tool_events[0].data["status"] == "ok"
    assert result is not None
    assert "只读健康事实：" in result.report_markdown
    assert "total_connections" in result.report_markdown
    assert not any(
        forbidden in result.report_markdown.lower()
        for forbidden in ("dsn", "password", "username", "nonce", "secret", "processlist")
    )
    assert any("pg_stat_activity" in statement for statement in engine.connection.statements)

    with pytest.raises(ServiceContextRequiredError):
        services.run_service.accept_run(
            CreateRunCommand(
                session_id=session_data.id,
                query="数据库连接压力指标",
                idempotency_key=uuid4(),
                service_id="postgres-production",
            )
        )

    registration.delete("pg.dynamic")
    removed_run = services.run_service.accept_run(
        CreateRunCommand(
            session_id=session_data.id,
            query="数据库连接压力指标",
            idempotency_key=uuid4(),
            service_id="pg.dynamic",
        )
    ).run
    assert services.run_service.execute_run(removed_run.id).status is RunStatus.FAILED
    database_session = runtime.session_factory()
    try:
        removed_events = SqlAlchemyRunEventRepository(database_session).list_by_run(
            removed_run.id, cursor=None, limit=100
        ).items
        removed_result = SqlAlchemyDiagnosisResultRepository(database_session).get_by_run_id(removed_run.id)
    finally:
        database_session.close()
        runtime.engine.dispose()
    assert [
        event.type
        for event in removed_events
        if event.type in {RunEventType.RUN_SUCCEEDED, RunEventType.RUN_FAILED, RunEventType.RUN_CANCELLED}
    ] == [RunEventType.RUN_FAILED]
    assert not any(event.type is RunEventType.TOOL_INVOKED for event in removed_events)
    assert removed_result is None
