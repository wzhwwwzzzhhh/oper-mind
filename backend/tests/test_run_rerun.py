"""P8 调查重跑 `POST /runs/{run_id}/rerun` 的受理、来源关联与幂等测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.contracts import (
    CreateRunCommand,
    CreateSessionCommand,
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
)
from src.application.errors import (
    RunNotTerminalError,
)
from src.application.services import (
    RUN_RERUN_ENDPOINT,
    RunApplicationService,
    SessionApplicationService,
    _rerun_fingerprint,
)
from src.domain.diagnosis import RunEventType, RunStatus
from src.domain.records import RunIdempotencyKeyData
from src.domain.services import ServiceDefinitionData, ServiceRegistry
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyRunIdempotencyKeyRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _DeterministicExecutor:
    """不访问真实 Agent、只输出安全事件的确定性执行器。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        yield DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="route",
            occurred_at=datetime.now(UTC),
        )
        yield DiagnosisExecutionResult(strategy="direct")


class _FailingExecutor:
    """总是执行失败的执行器。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        raise DiagnosisExecutionError(code="INNER_FAILURE", message="内部失败")
        yield DiagnosisExecutionResult()


class _Connector:
    """ServiceRegistry 用的最小服务桩，仅供会话创建的服务标识校验。"""

    def __init__(self, service_id: str) -> None:
        self._service_id = service_id

    def definition(self) -> ServiceDefinitionData:
        return ServiceDefinitionData(
            id=self._service_id,
            title=self._service_id,
            kind="postgres",
            supported_investigations=(),
            action_boundary="只读",
            session_title="调查",
        )

    def health_snapshot(self):
        raise AssertionError("本测试不读取服务快照")


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> PersistenceRuntime:
    database_path = tmp_path / "run-rerun.sqlite3"
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join([str(BACKEND_ROOT), str(PROJECT_ROOT), environment.get("PYTHONPATH", "")]),
        }
    )
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    try:
        yield runtime
    finally:
        runtime.engine.dispose()


def _v1_services(
    persistence_runtime: PersistenceRuntime,
    executor: _DeterministicExecutor | _FailingExecutor,
) -> V1Services:
    registry = ServiceRegistry((_Connector("postgres-production"), _Connector("postgres-staging")))
    return V1Services(
        session_factory=persistence_runtime.session_factory,
        session_service=SessionApplicationService(persistence_runtime.session_factory, registry),
        run_service=RunApplicationService(
            persistence_runtime.session_factory,
            executor,
            ConservativeResultAssembler(),
        ),
    )


@pytest.fixture
def v1_client(monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime) -> Iterator[TestClient]:
    services = _v1_services(persistence_runtime, _DeterministicExecutor())
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", "")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client


@pytest.fixture
def failing_v1_client(
    monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime
) -> Iterator[TestClient]:
    services = _v1_services(persistence_runtime, _FailingExecutor())
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", "")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client


def _run_headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _create_session(client: TestClient, service_id: str | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"title": "重跑测试会话"}
    if service_id is not None:
        payload["service_id"] = service_id
    response = client.post("/api/v1/sessions", json=payload)
    assert response.status_code == 201
    return response.json()["session"]


def _accept_and_finish(client: TestClient, session_id: str, query: str) -> dict[str, object]:
    """创建 Run 并等 background task 执行到终态（成功或失败），返回 Run 资源。"""
    response = client.post(
        f"/api/v1/sessions/{session_id}/runs",
        json={"query": query},
        headers=_run_headers(),
    )
    assert response.status_code == 202
    run_id = response.json()["run"]["id"]
    run = client.get(f"/api/v1/runs/{run_id}").json()["run"]
    assert run["status"] in {"succeeded", "failed"}
    return run


def _input_message_content(client: TestClient, session_id: str, message_id: str) -> str:
    response = client.get(f"/api/v1/sessions/{session_id}/messages", params={"limit": 100})
    assert response.status_code == 200
    for item in response.json()["items"]:
        if item["id"] == message_id:
            return str(item["content"])
    raise AssertionError(f"消息 {message_id} 未找到")


def test_rerun_终态run受理新run并记录来源关联(v1_client: TestClient) -> None:
    """AC1/AC3/AC5/AC9：succeeded Run 重跑受理新 Run，来源与 query 上下文复用，历史 Run 兼容。"""
    session = _create_session(v1_client)
    session_id = str(session["id"])
    original = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    original_id = str(original["id"])

    rerun_response = v1_client.post(f"/api/v1/runs/{original_id}/rerun", headers=_run_headers())
    assert rerun_response.status_code == 202
    rerun = rerun_response.json()["run"]
    rerun_id = str(rerun["id"])
    assert rerun_id != original_id
    assert rerun["rerun_of_run_id"] == original_id

    # AC3：新 Run 复用原问题的 query（经各自的 input message 比对）。
    assert rerun["input_message_id"] != original["input_message_id"]
    assert _input_message_content(v1_client, session_id, str(rerun["input_message_id"])) == (
        _input_message_content(v1_client, session_id, str(original["input_message_id"]))
    )
    # AC3：service 上下文一致（本会话未绑定服务，重跑同样为 null）。
    assert rerun["service_id"] == original["service_id"] is None

    # AC5：新 Run 详情展示来源。
    detail = v1_client.get(f"/api/v1/runs/{rerun_id}").json()["run"]
    assert detail["rerun_of_run_id"] == original_id
    # AC9：历史/普通 Run 来源字段为 null。
    original_detail = v1_client.get(f"/api/v1/runs/{original_id}").json()["run"]
    assert original_detail["rerun_of_run_id"] is None

    # 会话 Run 列表同步包含来源字段。
    listed = v1_client.get(f"/api/v1/sessions/{session_id}/runs", params={"limit": 100}).json()["items"]
    rerun_listed = next(item for item in listed if item["id"] == rerun_id)
    assert rerun_listed["rerun_of_run_id"] == original_id


def test_rerun_复用绑定服务的service上下文(v1_client: TestClient) -> None:
    """AC3：重跑复用原 Run 的 service_id。"""
    session = _create_session(v1_client, service_id="postgres-production")
    session_id = str(session["id"])
    original = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    assert original["service_id"] == "postgres-production"

    rerun_response = v1_client.post(
        f"/api/v1/runs/{original['id']!s}/rerun", headers=_run_headers()
    )
    assert rerun_response.status_code == 202
    assert rerun_response.json()["run"]["service_id"] == "postgres-production"


def test_rerun_失败run可重跑(failing_v1_client: TestClient) -> None:
    """AC1：failed Run 可重跑并记录来源。"""
    client = failing_v1_client
    session = _create_session(client)
    session_id = str(session["id"])
    original = _accept_and_finish(client, session_id, "订单服务变慢，帮我排查。")
    assert original["status"] == "failed"

    rerun_response = client.post(f"/api/v1/runs/{original['id']!s}/rerun", headers=_run_headers())
    assert rerun_response.status_code == 202
    assert rerun_response.json()["run"]["rerun_of_run_id"] == str(original["id"])


def test_rerun_cancelled与queued状态的服务层校验(persistence_runtime: PersistenceRuntime) -> None:
    """AC1/AC2：cancelled 可重跑；queued / running 重跑抛 RunNotTerminalError。"""
    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        _DeterministicExecutor(),
        ConservativeResultAssembler(),
    )
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    session = session_service.create_session(CreateSessionCommand(title="重跑测试会话"))

    def accept() -> UUID:
        accepted = run_service.accept_run(
            CreateRunCommand(
                session_id=session.id,
                query="订单服务变慢，帮我排查。",
                idempotency_key=uuid4(),
            )
        )
        return accepted.run.id

    # queued：受理后不执行 → 重跑被拒。
    queued_id = accept()
    with pytest.raises(RunNotTerminalError):
        run_service.rerun_run(queued_id, uuid4())

    # running：受理后认领为 running → 重跑被拒。
    running_id = accept()
    transition_session = persistence_runtime.session_factory()
    try:
        updated = SqlAlchemyDiagnosisRunRepository(transition_session).transition_status(
            running_id,
            expected_statuses={RunStatus.QUEUED},
            status=RunStatus.RUNNING,
            started_at=datetime.now(UTC),
        )
        assert updated is not None
    finally:
        transition_session.close()
    with pytest.raises(RunNotTerminalError):
        run_service.rerun_run(running_id, uuid4())

    # cancelled：受理 → 取消 → 重跑成功。
    cancelled_id = accept()
    run_service.cancel_run(cancelled_id)
    rerun = run_service.rerun_run(cancelled_id, uuid4())
    assert rerun.run.rerun_of_run_id == cancelled_id
    assert not rerun.replayed


def test_rerun_未终态API返回409明确错误(v1_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC2：queued/running 重跑在 API 层映射为 409 RUN_NOT_TERMINAL。"""

    def _raise_not_terminal(_run_id: UUID, _key: UUID) -> object:
        raise RunNotTerminalError()

    monkeypatch.setattr(v1_client.app.state.v1_services.run_service, "rerun_run", _raise_not_terminal)
    response = v1_client.post(f"/api/v1/runs/{uuid4()}/rerun", headers=_run_headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_NOT_TERMINAL"


def test_rerun_幂等重放不产生重复run(v1_client: TestClient) -> None:
    """AC4：同一幂等键重复重跑同一 Run，返回同一新 Run，不产生重复。"""
    session = _create_session(v1_client)
    session_id = str(session["id"])
    original = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    original_id = str(original["id"])
    key = _run_headers()

    first = v1_client.post(f"/api/v1/runs/{original_id}/rerun", headers=key)
    second = v1_client.post(f"/api/v1/runs/{original_id}/rerun", headers=key)
    assert first.status_code == second.status_code == 202
    assert first.json()["run"]["id"] == second.json()["run"]["id"]

    listed = v1_client.get(f"/api/v1/sessions/{session_id}/runs", params={"limit": 100}).json()["items"]
    assert len(listed) == 2
    assert sum(1 for item in listed if item["rerun_of_run_id"] == original_id) == 1


def test_rerun_同幂等键对不同原run重跑返回指纹冲突(v1_client: TestClient) -> None:
    """AC4 纵深：相同 query 的两个原 Run 用同一幂等键重跑 → 409 IDEMPOTENCY_KEY_REUSED。"""
    session = _create_session(v1_client)
    session_id = str(session["id"])
    first = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    second = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    key = _run_headers()

    ok = v1_client.post(f"/api/v1/runs/{first['id']!s}/rerun", headers=key)
    assert ok.status_code == 202
    conflict = v1_client.post(f"/api/v1/runs/{second['id']!s}/rerun", headers=key)
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_rerun_归档会话拒绝(v1_client: TestClient) -> None:
    """归档会话只读：重跑返回 409 SESSION_ARCHIVED。"""
    session = _create_session(v1_client)
    session_id = str(session["id"])
    original = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    archived = v1_client.delete(f"/api/v1/sessions/{session_id}")
    assert archived.status_code == 204

    response = v1_client.post(f"/api/v1/runs/{original['id']!s}/rerun", headers=_run_headers())
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_ARCHIVED"


def test_rerun_原run不存在返回404(v1_client: TestClient) -> None:
    """原 Run 不存在 → 404 RUN_NOT_FOUND。"""
    response = v1_client.post(f"/api/v1/runs/{uuid4()}/rerun", headers=_run_headers())
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"


def test_rerun_响应无未脱敏内容(v1_client: TestClient, failing_v1_client: TestClient) -> None:
    """AC7：重跑响应只含受控字段；失败重跑的错误经白名单映射。"""
    session = _create_session(v1_client)
    session_id = str(session["id"])
    original = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    response = v1_client.post(f"/api/v1/runs/{original['id']!s}/rerun", headers=_run_headers())
    assert response.status_code == 202
    payload = response.json()
    serialized = str(payload)
    assert "证据" not in serialized and "evidence" not in serialized
    assert "sk-" not in serialized and "postgresql://" not in serialized

    failing = failing_v1_client
    failed_session = _create_session(failing)
    failed_run = _accept_and_finish(failing, str(failed_session["id"]), "订单服务变慢，帮我排查。")
    assert failed_run["status"] == "failed"
    rerun_failed = failing.post(f"/api/v1/runs/{failed_run['id']!s}/rerun", headers=_run_headers())
    assert rerun_failed.status_code == 202


def test_rerun_全局run列表含来源字段(v1_client: TestClient) -> None:
    """AC6 服务端面：GET /runs 摘要携带 rerun_of_run_id。"""
    session = _create_session(v1_client)
    session_id = str(session["id"])
    original = _accept_and_finish(v1_client, session_id, "订单服务变慢，帮我排查。")
    rerun_response = v1_client.post(
        f"/api/v1/runs/{original['id']!s}/rerun", headers=_run_headers()
    )
    assert rerun_response.status_code == 202
    rerun_id = rerun_response.json()["run"]["id"]

    listed = v1_client.get("/api/v1/runs", params={"limit": 100}).json()["items"]
    rerun_item = next(item for item in listed if item["id"] == rerun_id)
    assert rerun_item["rerun_of_run_id"] == str(original["id"])


def _run_alembic(
    command: list[str],
    database_path: Path,
    working_directory: Path,
) -> subprocess.CompletedProcess[str]:
    """通过绝对 alembic.ini 在指定库运行迁移命令。"""
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join([str(BACKEND_ROOT), str(PROJECT_ROOT), environment.get("PYTHONPATH", "")]),
        }
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *command],
        cwd=working_directory,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_rerun_迁移存在来源行时拒绝回滚(tmp_path: Path) -> None:
    """迁移 downgrade 防御：存在 rerun_of_run_id 历史行时拒绝回滚。"""

    from src.infrastructure.persistence.database import create_app_engine

    database_path = tmp_path / "rerun-migration.sqlite3"
    upgrade = _run_alembic(["upgrade", "head"], database_path, PROJECT_ROOT)
    assert upgrade.returncode == 0, upgrade.stderr

    engine = create_app_engine(f"sqlite:///{database_path.as_posix()}")
    try:
        with engine.begin() as connection:
            now = "2026-08-12T00:00:00+00:00"
            session_id = str(uuid4())
            message_id = str(uuid4())
            rerun_message_id = str(uuid4())
            original_run_id = str(uuid4())
            rerun_run_id = str(uuid4())
            connection.exec_driver_sql(
                "INSERT INTO sessions (id, title, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (session_id, "迁移守卫", "active", now, now),
            )
            connection.exec_driver_sql(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?)",
                (message_id, session_id, "订单服务变慢，帮我排查。", now),
            )
            connection.exec_driver_sql(
                "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, 'user', ?, ?)",
                (rerun_message_id, session_id, "订单服务变慢，帮我排查。", now),
            )
            connection.exec_driver_sql(
                "INSERT INTO diagnosis_runs (id, session_id, trace_id, input_message_id, status, next_event_sequence, created_at) "
                "VALUES (?, ?, ?, ?, 'succeeded', 2, ?)",
                (original_run_id, session_id, str(uuid4()), message_id, now),
            )
            connection.exec_driver_sql(
                "INSERT INTO diagnosis_runs (id, session_id, trace_id, input_message_id, status, next_event_sequence, rerun_of_run_id, created_at) "
                "VALUES (?, ?, ?, ?, 'queued', 2, ?, ?)",
                (rerun_run_id, session_id, str(uuid4()), rerun_message_id, original_run_id, now),
            )
    finally:
        engine.dispose()

    downgrade = _run_alembic(["downgrade", "20260811_11_p8_service_registration"], database_path, PROJECT_ROOT)
    assert downgrade.returncode != 0
    assert "拒绝回滚" in downgrade.stderr


def test_rerun_唯一键竞争后幂等重读(persistence_runtime: PersistenceRuntime) -> None:
    """并发竞争：重跑唯一键冲突后经 _load_rerun_idempotency_after_conflict 重读返回同键 Run。"""
    from sqlalchemy.exc import IntegrityError


    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        _DeterministicExecutor(),
        ConservativeResultAssembler(),
    )
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    session = session_service.create_session(CreateSessionCommand(title="重跑竞争会话"))
    original = run_service.accept_run(
        CreateRunCommand(session_id=session.id, query="订单服务变慢，帮我排查。", idempotency_key=uuid4())
    )
    transition_session = persistence_runtime.session_factory()
    try:
        updated = SqlAlchemyDiagnosisRunRepository(transition_session).transition_status(
            original.run.id,
            expected_statuses={RunStatus.QUEUED},
            status=RunStatus.SUCCEEDED,
            finished_at=datetime.now(UTC),
        )
        assert updated is not None
        transition_session.commit()
    finally:
        transition_session.close()

    # 模拟并发竞争方已落库的 RERUN 作用域幂等记录（指纹匹配）。
    pre_read_session = persistence_runtime.session_factory()
    try:
        command = run_service._build_rerun_command(pre_read_session, original.run.id, uuid4())
    finally:
        pre_read_session.close()
    idempotency_key = uuid4()
    insert_session = persistence_runtime.session_factory()
    try:
        SqlAlchemyRunIdempotencyKeyRepository(insert_session).add(
            RunIdempotencyKeyData(
                session_id=session.id,
                endpoint=RUN_RERUN_ENDPOINT,
                idempotency_key=idempotency_key,
                request_fingerprint=_rerun_fingerprint(original.run.id, command.query, command.service_id),
                run_id=original.run.id,
                expires_at=datetime.now(UTC) + timedelta(hours=24),
                created_at=datetime.now(UTC),
            )
        )
        insert_session.commit()
    finally:
        insert_session.close()

    replayed = run_service._load_rerun_idempotency_after_conflict(
        original.run.id, idempotency_key, IntegrityError("模拟唯一键竞争", None, None)
    )
    assert replayed.replayed
    assert replayed.run.id == original.run.id
