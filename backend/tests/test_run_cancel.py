"""P8 取消运行中 Run 的应用服务与 API 测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
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
from src.application.errors import RunAlreadyTerminalError, RunNotFoundError
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import RunEventType, RunStatus
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import SqlAlchemyRunEventRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class FakeExecutor:
    """提供可控事件、结果和失败路径的确定性诊断执行器。"""

    def __init__(
        self,
        items: list[DiagnosisExecutionEvent | DiagnosisExecutionResult] | None = None,
        error: DiagnosisExecutionError | None = None,
        running_visible: Callable[[], None] | None = None,
    ) -> None:
        self.items = items or [DiagnosisExecutionResult(strategy="mock")]
        self.error = error
        self.running_visible = running_visible
        self.calls: list[str] = []

    def stream(self, query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        self.calls.append(query)
        if self.running_visible is not None:
            self.running_visible()
        if self.error is not None:
            raise self.error
        yield from self.items


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> PersistenceRuntime:
    """在独立临时 SQLite 中执行 migration 并返回应用持久化运行时。"""
    database_path = tmp_path / "run-cancel.sqlite3"
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


def _event(event_type: RunEventType, node: str = "route") -> DiagnosisExecutionEvent:
    return DiagnosisExecutionEvent(
        type=event_type,
        node=node,
        occurred_at=datetime.now(UTC),
    )


def _load_event_types(runtime: PersistenceRuntime, run_id: UUID) -> list[RunEventType]:
    session = runtime.session_factory()
    try:
        events = SqlAlchemyRunEventRepository(session).list_by_run(run_id, cursor=None, limit=20).items
        return [event.type for event in events]
    finally:
        session.close()


def _build_service(runtime: PersistenceRuntime, executor: FakeExecutor) -> tuple[SessionApplicationService, RunApplicationService]:
    session_service = SessionApplicationService(runtime.session_factory)
    run_service = RunApplicationService(runtime.session_factory, executor, ConservativeResultAssembler())
    return session_service, run_service


def _accept(run_service: RunApplicationService, session_id: UUID, query: str = "执行诊断") -> UUID:
    return run_service.accept_run(
        CreateRunCommand(session_id=session_id, query=query, idempotency_key=uuid4())
    ).run.id


def test_取消queued运行中的Run置为cancelled并写取消事件(persistence_runtime: PersistenceRuntime) -> None:
    """AC4：queued Run 可被取消，状态置 cancelled，事件流写入取消事件。"""
    session_service, run_service = _build_service(persistence_runtime, FakeExecutor())
    session = session_service.create_session(CreateSessionCommand(title="取消 queued"))
    run_id = _accept(run_service, session.id)

    cancelled = run_service.cancel_run(run_id)

    assert cancelled.status == RunStatus.CANCELLED
    assert cancelled.finished_at is not None
    assert _load_event_types(persistence_runtime, run_id) == [RunEventType.RUN_QUEUED, RunEventType.RUN_CANCELLED]


def test_取消running运行中的Run(persistence_runtime: PersistenceRuntime) -> None:
    """AC4：running Run 可被取消。"""
    session_service, run_service = _build_service(persistence_runtime, FakeExecutor())
    session = session_service.create_session(CreateSessionCommand(title="取消 running"))
    run_id = _accept(run_service, session.id)
    claimed = run_service._claim_run(run_id)
    assert claimed[2] is True

    cancelled = run_service.cancel_run(run_id)

    assert cancelled.status == RunStatus.CANCELLED
    assert cancelled.started_at is not None
    assert _load_event_types(persistence_runtime, run_id) == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_CANCELLED,
    ]


def test_已成功Run取消返回错误且状态不变(persistence_runtime: PersistenceRuntime) -> None:
    """AC5：已结束（succeeded）Run 不可取消。"""
    session_service, run_service = _build_service(persistence_runtime, FakeExecutor())
    session = session_service.create_session(CreateSessionCommand(title="已成功"))
    run_id = _accept(run_service, session.id)
    assert run_service.execute_run(run_id).status == RunStatus.SUCCEEDED

    with pytest.raises(RunAlreadyTerminalError):
        run_service.cancel_run(run_id)

    session = persistence_runtime.session_factory()
    try:
        from src.infrastructure.persistence.repositories import SqlAlchemyDiagnosisRunRepository

        stored = SqlAlchemyDiagnosisRunRepository(session).get_by_id(run_id)
    finally:
        session.close()
    assert stored is not None
    assert stored.status == RunStatus.SUCCEEDED


def test_已失败Run取消返回错误(persistence_runtime: PersistenceRuntime) -> None:
    """AC5：已失败 Run 不可取消。"""
    executor = FakeExecutor(error=DiagnosisExecutionError())
    session_service, run_service = _build_service(persistence_runtime, executor)
    session = session_service.create_session(CreateSessionCommand(title="已失败"))
    run_id = _accept(run_service, session.id)
    assert run_service.execute_run(run_id).status == RunStatus.FAILED

    with pytest.raises(RunAlreadyTerminalError):
        run_service.cancel_run(run_id)


def test_重复取消同一Run幂等(persistence_runtime: PersistenceRuntime) -> None:
    """AC6：已取消的 Run 重复取消仍返回成功。"""
    session_service, run_service = _build_service(persistence_runtime, FakeExecutor())
    session = session_service.create_session(CreateSessionCommand(title="幂等取消"))
    run_id = _accept(run_service, session.id)

    first = run_service.cancel_run(run_id)
    second = run_service.cancel_run(run_id)

    assert first.status == RunStatus.CANCELLED
    assert second.status == RunStatus.CANCELLED
    assert _load_event_types(persistence_runtime, run_id).count(RunEventType.RUN_CANCELLED) == 1


def test_不存在Run取消返回错误(persistence_runtime: PersistenceRuntime) -> None:
    """取消不存在的 Run 返回 404。"""
    _, run_service = _build_service(persistence_runtime, FakeExecutor())
    with pytest.raises(RunNotFoundError):
        run_service.cancel_run(uuid4())


def test_queued取消后execute_run不再启动执行(persistence_runtime: PersistenceRuntime) -> None:
    """AC4：排队中取消后，后台执行不再启动。"""
    executor = FakeExecutor(items=[_event(RunEventType.ROUTE_DECIDED), DiagnosisExecutionResult(strategy="direct")])
    session_service, run_service = _build_service(persistence_runtime, executor)
    session = session_service.create_session(CreateSessionCommand(title="排队取消"))
    run_id = _accept(run_service, session.id)
    run_service.cancel_run(run_id)

    result = run_service.execute_run(run_id)

    assert result.status == RunStatus.CANCELLED
    assert executor.calls == []
    assert _load_event_types(persistence_runtime, run_id) == [RunEventType.RUN_QUEUED, RunEventType.RUN_CANCELLED]


def test_执行中取消后事件循环停止追加(persistence_runtime: PersistenceRuntime) -> None:
    """AC4：协作式取消检查点——cancel 后执行循环停止写入后续事件。"""
    executor = FakeExecutor(
        items=[
            _event(RunEventType.ROUTE_DECIDED),
            _event(RunEventType.AGENT_DONE, node="db"),
            DiagnosisExecutionResult(strategy="direct"),
        ]
    )
    session_service, run_service = _build_service(persistence_runtime, executor)
    session = session_service.create_session(CreateSessionCommand(title="协作取消"))
    run_id = _accept(run_service, session.id)

    original_append = run_service._append_event

    def append_then_cancel(
        target_run_id: UUID,
        event_type: RunEventType,
        occurred_at: datetime,
        data: dict[str, Any],
    ) -> None:
        """在写入第一条执行事件后立即取消 Run，模拟执行中途收到取消。"""
        original_append(target_run_id, event_type, occurred_at, data)
        run_service.cancel_run(target_run_id)

    run_service._append_event = append_then_cancel  # type: ignore[method-assign]

    result = run_service.execute_run(run_id)

    assert result.status == RunStatus.CANCELLED
    assert _load_event_types(persistence_runtime, run_id) == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.ROUTE_DECIDED,
        RunEventType.RUN_CANCELLED,
    ]


@pytest.fixture
def v1_client(monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime) -> Iterator[TestClient]:
    """以同一运行时装配 v1 API 客户端。"""
    executor = FakeExecutor()
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    run_service = RunApplicationService(persistence_runtime.session_factory, executor, ConservativeResultAssembler())
    services = V1Services(
        session_factory=persistence_runtime.session_factory,
        session_service=session_service,
        run_service=run_service,
    )

    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", "")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        client.state_store = {"run_service": run_service}  # type: ignore[attr-defined]
        yield client


def test_取消接口对queuedRun返回204(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC4/AC6：POST /runs/{id}/cancel 成功返回 204，Run 状态变 cancelled。"""
    run_service: RunApplicationService = v1_client.state_store["run_service"]  # type: ignore[attr-defined]
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    session = session_service.create_session(CreateSessionCommand(title="接口取消"))
    run_id = _accept(run_service, session.id)

    response = v1_client.post(f"/api/v1/runs/{run_id}/cancel")

    assert response.status_code == 204
    assert v1_client.get(f"/api/v1/runs/{run_id}").json()["run"]["status"] == "cancelled"
    second = v1_client.post(f"/api/v1/runs/{run_id}/cancel")
    assert second.status_code == 204


def test_取消接口对已成功Run返回409(v1_client: TestClient) -> None:
    """AC5：已结束 Run 取消返回 409 RUN_ALREADY_TERMINAL。"""
    created = v1_client.post("/api/v1/sessions", json={"title": "接口已成功"}).json()["session"]
    accepted = v1_client.post(
        f"/api/v1/sessions/{created['id']}/runs",
        json={"query": "检查 CPU"},
        headers={"Idempotency-Key": str(uuid4())},
    )
    assert accepted.status_code == 202
    assert v1_client.get(f"/api/v1/runs/{accepted.json()['run']['id']}").json()["run"]["status"] == "succeeded"

    response = v1_client.post(f"/api/v1/runs/{accepted.json()['run']['id']}/cancel")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RUN_ALREADY_TERMINAL"


def test_取消接口对不存在Run返回404(v1_client: TestClient) -> None:
    """取消不存在的 Run 返回 404。"""
    response = v1_client.post(f"/api/v1/runs/{uuid4()}/cancel")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "RUN_NOT_FOUND"
