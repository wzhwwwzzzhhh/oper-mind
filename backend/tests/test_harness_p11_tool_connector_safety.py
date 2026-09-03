"""P11 S2 Tool、Connector、默认离线与真实测试前门。"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import AbstractContextManager
from pathlib import Path
from threading import Event
from typing import Any, Literal

import pytest
import redis
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

import src.core.tool_gateway as tool_gateway_module
from scripts.check_p11_real_resource_preflight import (
    CREDENTIAL_REF_ENV,
    OPT_IN_ENV,
    OPT_IN_VALUE,
    TARGET_ENV,
    PreflightSafeStop,
    check_preflight,
)
from src.application.knowledge import KnowledgeReaderService
from src.config import load_action_mode
from src.core.agent import BaseAgent
from src.core.graph import _tool_traces
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import Tool, ToolRegistry
from src.domain.services import ServiceAvailability
from src.infrastructure.logs.log_source import LogSourceConnector
from src.infrastructure.services.postgres_connector import PostgresServiceConnector
from src.infrastructure.services.postgres_engine import create_read_only_postgres_engine
from src.infrastructure.services.redis_connector import RedisServiceConnector
from src.tools import db_tools
from src.tools.db_tools import ExplainTool, ShowIndexTool
from src.tools.knowledge_tools import SearchKnowledgeTool

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
SENSITIVE_SENTINEL = "postgresql://admin:secret@real-host/prod token=late-secret"


def _registry(*tools: Tool) -> ToolRegistry:
    registry = ToolRegistry()
    for tool in tools:
        registry.register(tool)
    return registry


class BlockingTool(Tool):
    """用 Event 精确控制运行中 Tool 的迟到结果或异常。"""

    def __init__(self, name: str, outcome: Literal["result", "error"] = "result") -> None:
        super().__init__(name=name, description="P11 blocking fake", parameters={"type": "object"})
        self.outcome = outcome
        self.started = Event()
        self.release = Event()
        self.finished = Event()
        self.calls = 0
        self.audit_calls = 0

    def execute(self) -> str:
        self.calls += 1
        self.started.set()
        assert self.release.wait(timeout=5)
        self.finished.set()
        if self.outcome == "error":
            raise RuntimeError(SENSITIVE_SENTINEL)
        return SENSITIVE_SENTINEL

    def audit_summary(self) -> str:
        self.audit_calls += 1
        return SENSITIVE_SENTINEL


class CountingTool(Tool):
    """记录排队 future 是否曾被补执行。"""

    def __init__(self) -> None:
        super().__init__(name="queued", description="P11 queued fake", parameters={"type": "object"})
        self.calls = 0

    def execute(self) -> str:
        self.calls += 1
        return "不应执行"


class ImmediateTimeoutErrorTool(Tool):
    """立即抛出同名 TimeoutError，用于区分 Gateway 等待超时。"""

    def __init__(self) -> None:
        super().__init__(name="self_timeout", description="P11 timeout fake", parameters={"type": "object"})

    def execute(self) -> str:
        raise TimeoutError(SENSITIVE_SENTINEL)


@pytest.mark.parametrize("outcome", ["result", "error"])
def test_运行中Tool超时关闭接纳并隔离迟到内容(
    outcome: Literal["result", "error"],
) -> None:
    tool = BlockingTool("running", outcome)
    gateway = ToolGateway(_registry(tool), timeout_seconds=0.03)
    try:
        started = time.monotonic()
        result = gateway.invoke(tool.name, "{}")
        elapsed = time.monotonic() - started
        assert tool.started.is_set()
        assert elapsed < 0.5
        assert result.record.status == "timeout"
        assert result.record.wait_status == "timed_out"
        assert result.record.acceptance_status == "closed"
        assert result.record.underlying_execution_status == "stop_state_unknown"
        assert "已中止" not in result.output
        assert "已停止" not in result.output
        frozen = result.model_dump_json()

        tool.release.set()
        assert tool.finished.wait(timeout=2)
        assert result.model_dump_json() == frozen
        assert tool.audit_calls == 0
        assert SENSITIVE_SENTINEL not in frozen
    finally:
        tool.release.set()
        gateway.shutdown()


def test_排队future超时取消后永不补执行() -> None:
    running = BlockingTool("running")
    queued = CountingTool()
    gateway = ToolGateway(_registry(running, queued), timeout_seconds=0.03)
    try:
        first = gateway.invoke(running.name, "{}")
        assert first.record.underlying_execution_status == "stop_state_unknown"
        assert running.started.is_set()

        second = gateway.invoke(queued.name, "{}")
        assert second.record.status == "timeout"
        assert second.record.wait_status == "timed_out"
        assert second.record.acceptance_status == "closed"
        assert second.record.underlying_execution_status == "cancelled_before_start"
        assert "排队执行已取消" in second.output

        running.release.set()
        assert running.finished.wait(timeout=2)
        gateway.shutdown()
        assert queued.calls == 0
    finally:
        running.release.set()
        gateway.shutdown()


def test_Tool自身TimeoutError不等于Gateway等待超时() -> None:
    tool = ImmediateTimeoutErrorTool()
    gateway = ToolGateway(_registry(tool), timeout_seconds=1)
    try:
        result = gateway.invoke(tool.name, "{}")
    finally:
        gateway.shutdown()

    assert result.record.status == "error"
    assert result.record.wait_status == "completed"
    assert result.record.acceptance_status == "accepted"
    assert result.record.underlying_execution_status == "completed"
    assert SENSITIVE_SENTINEL not in result.model_dump_json()


def test_shutdown取消排队future不得误报为已完成(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created: list[ObservableExecutor] = []

    class ObservableExecutor(ThreadPoolExecutor):
        def __init__(self, max_workers: int) -> None:
            super().__init__(max_workers=max_workers)
            self.submission_count = 0
            self.second_submitted = Event()
            created.append(self)

        def submit(self, fn: Any, /, *args: Any, **kwargs: Any):
            future = super().submit(fn, *args, **kwargs)
            self.submission_count += 1
            if self.submission_count == 2:
                self.second_submitted.set()
            return future

    monkeypatch.setattr(tool_gateway_module, "ThreadPoolExecutor", ObservableExecutor)
    running = BlockingTool("shutdown-running")
    queued = CountingTool()
    gateway = ToolGateway(_registry(running, queued), timeout_seconds=2)
    callers = ThreadPoolExecutor(max_workers=2)
    try:
        first = callers.submit(gateway.invoke, running.name, "{}")
        assert running.started.wait(timeout=1)
        second = callers.submit(gateway.invoke, queued.name, "{}")
        assert created[0].second_submitted.wait(timeout=1)

        gateway.shutdown()
        result = second.result(timeout=1)

        assert result.record.status == "error"
        assert result.record.wait_status == "completed"
        assert result.record.acceptance_status == "closed"
        assert result.record.underlying_execution_status == "cancelled_before_start"
        assert queued.calls == 0

        running.release.set()
        assert first.result(timeout=1).record.status == "ok"
    finally:
        running.release.set()
        gateway.shutdown()
        callers.shutdown(wait=True, cancel_futures=True)


class TimeoutLLM:
    """首轮调用 blocking Tool，次轮给出固定安全答案。"""

    def __init__(self, tool_name: str) -> None:
        self.tool_name = tool_name
        self.calls = 0
        self.received: list[list[dict[str, Any]]] = []

    def chat(self, messages: list[dict[str, Any]], **kwargs: object) -> dict[str, Any]:
        del kwargs
        self.calls += 1
        self.received.append([dict(message) for message in messages])
        if self.calls == 1:
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "p11-call",
                        "type": "function",
                        "function": {"name": self.tool_name, "arguments": "{}"},
                    }
                ],
            }
        return {"role": "assistant", "content": "安全失败结论"}


def test_迟到Tool结果不进入Agent记忆结果或公开Trace(monkeypatch: pytest.MonkeyPatch) -> None:
    tool = BlockingTool("agent-running")
    llm = TimeoutLLM(tool.name)

    def short_gateway(registry: ToolRegistry) -> ToolGateway:
        return ToolGateway(registry, timeout_seconds=0.03)

    monkeypatch.setattr("src.core.agent.ToolGateway", short_gateway)
    agent = BaseAgent(
        llm=llm,  # type: ignore[arg-type]
        tools=_registry(tool),
        system_prompt="P11 safe agent",
        enable_long_term_memory=False,
    )
    try:
        answer = agent.run("执行工具")
        accepted_before_release = json.dumps(
            {
                "answer": answer,
                "memory": agent.get_conversation_history(),
                "records": [record.model_dump() for record in agent.get_tool_invocations()],
                "trace": _tool_traces(agent),
            },
            ensure_ascii=False,
            default=str,
        )
        tool.release.set()
        assert tool.finished.wait(timeout=2)
        accepted_after_release = json.dumps(
            {
                "answer": answer,
                "memory": agent.get_conversation_history(),
                "records": [record.model_dump() for record in agent.get_tool_invocations()],
                "trace": _tool_traces(agent),
            },
            ensure_ascii=False,
            default=str,
        )
    finally:
        tool.release.set()

    assert answer == "安全失败结论"
    assert accepted_after_release == accepted_before_release
    assert SENSITIVE_SENTINEL not in accepted_after_release
    assert tool.audit_calls == 0
    assert len(agent.get_tool_invocations()) == 1


class FakeResult:
    def __init__(self, row: dict[str, Any] | None = None) -> None:
        self.row = row

    def mappings(self) -> FakeResult:
        return self

    def first(self) -> dict[str, Any] | None:
        return self.row


class FakePgConnection(AbstractContextManager[Any]):
    def __init__(self, *, exit_error: bool = False) -> None:
        self.statements: list[str] = []
        self.exit_error = exit_error
        self.results = iter(
            [
                FakeResult({"numbackends": 2}),
                FakeResult({"calls": 0, "p50_ms": 1.0, "p95_ms": 2.0}),
            ]
        )

    def __enter__(self) -> FakePgConnection:
        return self

    def __exit__(self, *args: object) -> None:
        del args
        if self.exit_error:
            raise RuntimeError(SENSITIVE_SENTINEL)

    def execute(self, statement: object) -> FakeResult:
        sql = str(statement)
        self.statements.append(sql)
        if sql.startswith(("SET TRANSACTION READ ONLY", "SELECT 1")):
            return FakeResult()
        return next(self.results)


class FakePgEngine:
    def __init__(self, connection: FakePgConnection, *, dispose_error: bool = False) -> None:
        self.connection = connection
        self.dispose_error = dispose_error
        self.disposed = False

    def connect(self) -> FakePgConnection:
        return self.connection

    def dispose(self) -> None:
        self.disposed = True
        if self.dispose_error:
            raise RuntimeError(SENSITIVE_SENTINEL)


def test_PostgreSQL资源超时和驱动参数由factory精确设置(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    engine = FakePgEngine(FakePgConnection())

    def fake_create_engine(url: object, **kwargs: object) -> FakePgEngine:
        captured["url"] = url
        captured["kwargs"] = kwargs
        return engine

    monkeypatch.setattr("src.infrastructure.services.postgres_engine.create_engine", fake_create_engine)
    returned = create_read_only_postgres_engine("postgresql://user:password@host/database")

    assert returned is engine
    assert make_url(captured["url"]).drivername == "postgresql+psycopg"
    connect_args = captured["kwargs"]["connect_args"]
    assert connect_args == {"connect_timeout": 3, "options": "-c statement_timeout=3000"}


@pytest.mark.parametrize("exit_error", [False, True])
def test_PostgreSQL只读快照与主流程失败语义(exit_error: bool) -> None:
    connection = FakePgConnection(exit_error=exit_error)
    snapshot = PostgresServiceConnector(
        "postgresql://user:password@host/database",
        engine=FakePgEngine(connection),  # type: ignore[arg-type]
    ).health_snapshot()

    assert connection.statements[0] == "SET TRANSACTION READ ONLY"
    assert all(
        statement.startswith(("SET TRANSACTION READ ONLY", "SELECT"))
        for statement in connection.statements
    )
    expected = ServiceAvailability.UNAVAILABLE if exit_error else ServiceAvailability.HEALTHY
    assert snapshot.availability is expected
    assert SENSITIVE_SENTINEL not in snapshot.model_dump_json()


@pytest.mark.parametrize(
    ("exit_error", "expected"),
    [
        (False, ServiceAvailability.HEALTHY),
        (True, ServiceAvailability.UNAVAILABLE),
    ],
)
def test_PostgreSQLdispose失败保留可信快照且日志脱敏(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    exit_error: bool,
    expected: ServiceAvailability,
) -> None:
    engine = FakePgEngine(FakePgConnection(exit_error=exit_error), dispose_error=True)
    connector = PostgresServiceConnector("postgresql://user:password@host/database")
    monkeypatch.setattr(connector, "_create_engine", lambda: engine)

    snapshot = connector.health_snapshot()

    assert snapshot.availability is expected
    assert engine.disposed is True
    assert "PostgreSQL 连接清理失败" in caplog.text
    assert SENSITIVE_SENTINEL not in caplog.text
    assert "password@host" not in caplog.text


def test_PostgreSQL非法查询和标识符在连接前拒绝(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0

    def forbidden_connection(service_id: str | None) -> None:
        nonlocal calls
        del service_id
        calls += 1
        raise AssertionError("非法输入不得尝试连接")

    monkeypatch.setattr(db_tools, "_real_connection", forbidden_connection)

    assert "已拒绝" in ExplainTool("postgres-production").execute("DELETE FROM users")
    assert "已拒绝" in ExplainTool("postgres-production").execute("SELECT 1; SELECT 2")
    assert "已拒绝" in ShowIndexTool("postgres-production").execute("users;DROP TABLE users")
    assert calls == 0


class FakeRedisClient:
    def __init__(self, *, close_error: bool = False, command_error: bool = False) -> None:
        self.close_error = close_error
        self.command_error = command_error
        self.commands: list[str] = []

    def _record(self, name: str) -> None:
        self.commands.append(name)
        if self.command_error:
            raise RuntimeError(SENSITIVE_SENTINEL)

    def ping(self) -> bool:
        self._record("ping")
        return True

    def info(self, section: str) -> dict[str, int]:
        self._record(f"info:{section}")
        return {"used_memory": 64}

    def client_list(self) -> list[dict[str, str]]:
        self._record("client_list")
        return [{"addr": "fake"}]

    def slowlog_len(self) -> int:
        self._record("slowlog_len")
        return 0

    def close(self) -> None:
        if self.close_error:
            raise RuntimeError(SENSITIVE_SENTINEL)


@pytest.mark.parametrize(
    ("command_error", "close_error", "expected"),
    [
        (False, False, ServiceAvailability.HEALTHY),
        (True, False, ServiceAvailability.UNAVAILABLE),
        (False, True, ServiceAvailability.HEALTHY),
        (True, True, ServiceAvailability.UNAVAILABLE),
    ],
)
def test_Redis限时只读命令与失败收敛(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    command_error: bool,
    close_error: bool,
    expected: ServiceAvailability,
) -> None:
    captured: dict[str, Any] = {}
    client = FakeRedisClient(close_error=close_error, command_error=command_error)

    def fake_from_url(dsn: str, **kwargs: object) -> FakeRedisClient:
        captured["dsn_seen"] = bool(dsn)
        captured["kwargs"] = kwargs
        return client

    monkeypatch.setattr(redis.Redis, "from_url", fake_from_url)
    snapshot = RedisServiceConnector("redis://:secret@host/0").health_snapshot()

    assert snapshot.availability is expected
    assert captured["kwargs"] == {
        "socket_connect_timeout": 3.0,
        "socket_timeout": 3.0,
        "decode_responses": True,
    }
    expected_commands = ["ping"] if command_error else [
        "ping",
        "info:memory",
        "client_list",
        "slowlog_len",
    ]
    assert client.commands == expected_commands
    serialized = snapshot.model_dump_json() + caplog.text
    assert SENSITIVE_SENTINEL not in serialized
    assert "redis://" not in serialized
    if close_error:
        assert "Redis 连接关闭失败" in caplog.text


def test_普通测试环境默认离线且低层入口失败关闭() -> None:
    assert not any(
        name.startswith("OPERMIND_SERVICE_") and name.endswith(("_DSN", "_LOG_DIR"))
        for name in os.environ
    )
    assert os.environ["OPERMIND_API_KEY"] == "mock"
    assert os.environ["OPERMIND_BASE_URL"] == "http://mock.invalid"
    assert os.environ["OPERMIND_MODEL"] == "mock"
    assert os.environ["OPERMIND_APP_DATABASE_URL"].startswith("sqlite:///")
    assert load_action_mode() == "mock"

    with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
        socket.getaddrinfo("external.example", 443)
    for resolver, arguments in (
        (socket.gethostbyname, ("external.example",)),
        (socket.gethostbyname_ex, ("external.example",)),
        (socket.gethostbyaddr, ("203.0.113.1",)),
        (socket.getnameinfo, (("203.0.113.1", 443), 0)),
    ):
        with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
            resolver(*arguments)
    with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
        socket.create_connection(("127.0.0.1", 1), timeout=0.01)
    left, right = socket.socketpair()
    with left, right:
        assert left.fileno() >= 0
        assert right.fileno() >= 0
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as direct_socket,
        pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"),
    ):
        direct_socket.connect(("127.0.0.1", 1))
    with (
        socket.socket(socket.AF_INET, socket.SOCK_STREAM) as direct_socket,
        pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"),
    ):
        direct_socket.connect_ex(("127.0.0.1", 1))
    with (
        socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as datagram_socket,
        pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"),
    ):
        datagram_socket.sendto(b"blocked", ("127.0.0.1", 9))
    with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
        create_engine("postgresql+psycopg://user:password@external.invalid/db").connect()
    with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
        redis.Redis.from_url("redis://:secret@external.invalid/0").ping()
    with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
        LogSourceConnector("D:/external-real-logs").search("error", None)
    with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
        SearchKnowledgeTool("D:/external-real-knowledge").execute("error")
    with pytest.raises(RuntimeError, match=r"^OFFLINE_TEST_EXTERNAL_ACCESS_BLOCKED$"):
        _ = KnowledgeReaderService("D:/external-real-knowledge").root


def test_带真实配置哨兵的子进程在collection前被净化() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_SERVICE_POSTGRES_TARGET_DSN": SENSITIVE_SENTINEL,
            "OPERMIND_SERVICE_POSTGRES_PRODUCTION_LOG_DIR": "D:/external-real-logs",
            "OPERMIND_KNOWLEDGE_DIR": "D:/external-real-knowledge",
            "OPERMIND_PG_DSN": SENSITIVE_SENTINEL,
            "OPERMIND_APP_DATABASE_URL": SENSITIVE_SENTINEL,
            "OPERMIND_API_KEY": "real-provider-key",
            "OPERMIND_BASE_URL": "https://provider.invalid",
            "OPERMIND_MODEL": "real-provider-model",
            "PYTHONPATH": os.pathsep.join(
                [str(BACKEND_ROOT), str(PROJECT_ROOT), environment.get("PYTHONPATH", "")]
            ),
        }
    )
    script = (
        "import os, runpy; runpy.run_path('tests/conftest.py'); "
        "assert 'OPERMIND_SERVICE_POSTGRES_TARGET_DSN' not in os.environ; "
        "assert 'OPERMIND_SERVICE_POSTGRES_PRODUCTION_LOG_DIR' not in os.environ; "
        "assert os.environ['OPERMIND_KNOWLEDGE_DIR'] == ''; "
        "assert os.environ['OPERMIND_PG_DSN'] == ''; "
        "assert os.environ['OPERMIND_APP_DATABASE_URL'].startswith('sqlite:///'); "
        "assert os.environ['OPERMIND_API_KEY'] == 'mock'; "
        "assert os.environ['OPERMIND_BASE_URL'] == 'http://mock.invalid'; "
        "assert os.environ['OPERMIND_MODEL'] == 'mock'; "
        "from src.config import load_action_mode; assert load_action_mode() == 'mock'; "
        "print('offline-ok')"
    )

    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=BACKEND_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "offline-ok"
    assert SENSITIVE_SENTINEL not in completed.stdout + completed.stderr


@pytest.mark.parametrize(
    ("environment", "code"),
    [
        ({}, "P11_REAL_TEST_OPT_IN_REQUIRED"),
        ({OPT_IN_ENV: OPT_IN_VALUE}, "P11_REAL_TEST_TARGET_REQUIRED"),
        (
            {OPT_IN_ENV: OPT_IN_VALUE, TARGET_ENV: "postgres-production"},
            "P11_REAL_TEST_CREDENTIAL_REF_REQUIRED",
        ),
        (
            {
                OPT_IN_ENV: OPT_IN_VALUE,
                TARGET_ENV: "postgres-production",
                CREDENTIAL_REF_ENV: "OPERMIND_SERVICE_REDIS_PRODUCTION_DSN",
            },
            "P11_REAL_TEST_CREDENTIAL_REF_MISMATCH",
        ),
        (
            {
                OPT_IN_ENV: OPT_IN_VALUE,
                TARGET_ENV: "postgres-production",
                CREDENTIAL_REF_ENV: "OPERMIND_SERVICE_POSTGRES_PRODUCTION_DSN",
            },
            "P11_REAL_TEST_CREDENTIAL_VALUE_REQUIRED",
        ),
    ],
)
def test_真实测试软件门缺任一条件均在访问前失败关闭(
    environment: dict[str, str],
    code: str,
) -> None:
    with pytest.raises(PreflightSafeStop) as caught:
        check_preflight(environment)

    assert caught.value.code == code
    assert SENSITIVE_SENTINEL not in str(caught.value)


def test_软件门通过仍要求当次人工授权且没有执行访问() -> None:
    credential_ref = "OPERMIND_SERVICE_POSTGRES_PRODUCTION_DSN"
    result = check_preflight(
        {
            OPT_IN_ENV: OPT_IN_VALUE,
            TARGET_ENV: "postgres-production",
            CREDENTIAL_REF_ENV: credential_ref,
            credential_ref: SENSITIVE_SENTINEL,
        }
    )

    assert result.technical_prerequisites == "satisfied"
    assert result.external_access_performed is False
    assert result.human_authorization == "required"
    assert SENSITIVE_SENTINEL not in repr(result)
