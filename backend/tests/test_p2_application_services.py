"""P2.3 Session/Run Application Service 的事务与诊断适配验证。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from src.application.contracts import (
    CreateRunCommand,
    CreateSessionCommand,
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
)
from src.application.errors import (
    IdempotencyKeyReusedError,
    RunInputMessageInvalidError,
    SessionArchivedError,
    SessionNotFoundError,
)
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import MessageRole, RunEventType, RunStatus, SessionStatus
from src.domain.records import DiagnosisRunData, MessageData
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRunEventRepository,
    SqlAlchemySessionRepository,
)


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
        """记录调用，验证执行前 Run 已提交为 running。"""
        self.calls.append(query)
        if self.running_visible is not None:
            self.running_visible()
        if self.error is not None:
            raise self.error
        yield from self.items


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> PersistenceRuntime:
    """在独立临时 SQLite 中执行 migration 并返回应用持久化运行时。"""
    database_path = tmp_path / "application-service.sqlite3"
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
        cwd=tmp_path,
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
    """创建确定性安全执行事件。"""
    return DiagnosisExecutionEvent(
        type=event_type,
        node=node,
        occurred_at=datetime.now(timezone.utc),
        data={"raw": "不得持久化"},
    )


def _load_events(runtime: PersistenceRuntime, run_id: UUID):
    """读取 RunEvent 并确保测试 Session 被关闭。"""
    session = runtime.session_factory()
    try:
        return SqlAlchemyRunEventRepository(session).list_by_run(run_id, cursor=None, limit=20).items
    finally:
        session.close()


def test_session创建归档与归档后拒绝受理(persistence_runtime: PersistenceRuntime) -> None:
    """Session Service 创建/归档均短事务，归档 Session 不能再接受 Run。"""
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        FakeExecutor(),
        ConservativeResultAssembler(),
    )

    created = session_service.create_session(CreateSessionCommand(title="  P2.3 会话  "))
    assert created.title == "P2.3 会话"
    archived = session_service.archive_session(created.id)
    assert archived.status == SessionStatus.ARCHIVED
    assert archived.archived_at is not None
    assert session_service.archive_session(created.id) == archived

    with pytest.raises(SessionArchivedError):
        run_service.accept_run(
            CreateRunCommand(session_id=created.id, query="归档后不允许受理", idempotency_key=uuid4())
        )
    with pytest.raises(SessionNotFoundError):
        session_service.archive_session(uuid4())


def test_run受理幂等重放冲突与受理事务(persistence_runtime: PersistenceRuntime) -> None:
    """受理事务必须原子写入 Message/Run/Key/queued 事件，并按指纹处理幂等。"""
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    session_data = session_service.create_session(CreateSessionCommand(title="幂等会话"))
    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        FakeExecutor(),
        ConservativeResultAssembler(),
    )
    idempotency_key = uuid4()
    command = CreateRunCommand(
        session_id=session_data.id,
        query="  检查 CPU 告警  ",
        idempotency_key=idempotency_key,
    )

    accepted = run_service.accept_run(command)
    replayed = run_service.accept_run(command)
    assert accepted.replayed is False
    assert replayed.replayed is True
    assert replayed.run.id == accepted.run.id
    assert accepted.run.status == RunStatus.QUEUED
    assert accepted.run.next_event_sequence == 2

    with pytest.raises(IdempotencyKeyReusedError):
        run_service.accept_run(
            CreateRunCommand(
                session_id=session_data.id,
                query="检查不同告警",
                idempotency_key=idempotency_key,
            )
        )

    session = persistence_runtime.session_factory()
    try:
        stored_session = SqlAlchemySessionRepository(session).get_by_id(session_data.id)
        assert stored_session is not None
        assert stored_session.updated_at >= accepted.run.created_at
        messages = SqlAlchemyMessageRepository(session).list_by_session(session_data.id, cursor=None, limit=10).items
        assert len(messages) == 1
        assert messages[0].role.value == "user"
        assert messages[0].content == "检查 CPU 告警"
        assert [event.sequence for event in _load_events(persistence_runtime, accepted.run.id)] == [1]
        assert _load_events(persistence_runtime, accepted.run.id)[0].type == RunEventType.RUN_QUEUED
    finally:
        session.close()


def test_run执行成功在无事务区间调用执行器并写入安全终态(persistence_runtime: PersistenceRuntime) -> None:
    """queued → running 提交后才执行，成功事务原子写入 Result/助手消息/终态。"""
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    session_data = session_service.create_session(CreateSessionCommand(title="成功执行"))
    run_id_holder: dict[str, UUID] = {}

    def assert_running_visible() -> None:
        """执行器运行时可从独立 Session 读取已提交 running Run。"""
        session = persistence_runtime.session_factory()
        try:
            run = SqlAlchemyDiagnosisRunRepository(session).get_by_id(run_id_holder["run_id"])
            assert run is not None
            assert run.status == RunStatus.RUNNING
        finally:
            session.close()

    executor = FakeExecutor(
        items=[
            _event(RunEventType.ROUTE_DECIDED),
            _event(RunEventType.AGENT_DONE, node="db"),
            DiagnosisExecutionResult(strategy="direct"),
        ],
        running_visible=assert_running_visible,
    )
    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        executor,
        ConservativeResultAssembler(),
    )
    accepted = run_service.accept_run(
        CreateRunCommand(session_id=session_data.id, query="检查数据库", idempotency_key=uuid4())
    )
    run_id_holder["run_id"] = accepted.run.id

    completed = run_service.execute_run(accepted.run.id)
    assert completed.status == RunStatus.SUCCEEDED
    assert executor.calls == ["检查数据库"]
    assert run_service.execute_run(accepted.run.id).status == RunStatus.SUCCEEDED
    assert executor.calls == ["检查数据库"]

    events = _load_events(persistence_runtime, accepted.run.id)
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
    assert [event.type for event in events] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.ROUTE_DECIDED,
        RunEventType.AGENT_DONE,
        RunEventType.RUN_SUCCEEDED,
    ]
    assert events[2].data == {"node": "route"}
    assert events[3].data == {"node": "db"}

    session = persistence_runtime.session_factory()
    try:
        result = SqlAlchemyDiagnosisResultRepository(session).get_by_run_id(accepted.run.id)
        stored_session = SqlAlchemySessionRepository(session).get_by_id(session_data.id)
        messages = SqlAlchemyMessageRepository(session).list_by_session(session_data.id, cursor=None, limit=10).items
        assert result is not None
        assert stored_session is not None
        assert completed.finished_at is not None
        assert stored_session.updated_at >= completed.finished_at
        assert result.confidence == 0.0
        assistant_messages = [item for item in messages if item.role.value == "assistant"]
        assert len(assistant_messages) == 1
        assert assistant_messages[0].run_id == accepted.run.id
        assert assistant_messages[0].session_id == session_data.id
    finally:
        session.close()


def test_run执行失败写入安全错误与终态事件(persistence_runtime: PersistenceRuntime) -> None:
    """执行器错误不可泄露内部原因，必须转换为失败 Run 与 run_failed 事件。"""
    session_data = SessionApplicationService(persistence_runtime.session_factory).create_session(
        CreateSessionCommand(title="失败执行")
    )
    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        FakeExecutor(error=DiagnosisExecutionError(code="UPSTREAM_TIMEOUT", message="上游超时，请稍后重试")),
        ConservativeResultAssembler(),
    )
    accepted = run_service.accept_run(
        CreateRunCommand(session_id=session_data.id, query="检查超时", idempotency_key=uuid4())
    )

    failed = run_service.execute_run(accepted.run.id)
    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "DIAGNOSIS_FAILED"
    assert failed.error_message == "诊断执行失败，请稍后重试"
    session = persistence_runtime.session_factory()
    try:
        assert SqlAlchemyDiagnosisResultRepository(session).get_by_run_id(accepted.run.id) is None
    finally:
        session.close()
    events = _load_events(persistence_runtime, accepted.run.id)
    assert [event.type for event in events] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_FAILED,
    ]
    assert events[-1].data == {"state": "failed", "code": "DIAGNOSIS_FAILED"}


def test_result组装失败回滚成功事务但保持running(persistence_runtime: PersistenceRuntime) -> None:
    """成功事务失败时 Result/助手消息/成功终态必须整体回滚。"""

    class InvalidAssembler:
        """故意返回错误 run_id，模拟组装器边界失败。"""

        def assemble(self, run, result):
            return ConservativeResultAssembler().assemble(run.model_copy(update={"id": uuid4()}), result)

    session_data = SessionApplicationService(persistence_runtime.session_factory).create_session(
        CreateSessionCommand(title="回滚验证")
    )
    run_service = RunApplicationService(
        persistence_runtime.session_factory,
        FakeExecutor(),
        InvalidAssembler(),
    )
    accepted = run_service.accept_run(
        CreateRunCommand(session_id=session_data.id, query="触发组装失败", idempotency_key=uuid4())
    )

    failed = run_service.execute_run(accepted.run.id)
    assert failed.status == RunStatus.FAILED
    events = _load_events(persistence_runtime, accepted.run.id)
    assert [event.type for event in events] == [
        RunEventType.RUN_QUEUED,
        RunEventType.RUN_STARTED,
        RunEventType.RUN_FAILED,
    ]
    session = persistence_runtime.session_factory()
    try:
        assert SqlAlchemyDiagnosisResultRepository(session).get_by_run_id(accepted.run.id) is None
        messages = SqlAlchemyMessageRepository(session).list_by_session(session_data.id, cursor=None, limit=10).items
        assert [message.role.value for message in messages] == ["user"]
    finally:
        session.close()



def test_run执行拒绝跨Session输入消息(persistence_runtime: PersistenceRuntime) -> None:
    """应用服务必须补足 messages.run_id/input_message 无物理跨表一致性约束。"""
    session_service = SessionApplicationService(persistence_runtime.session_factory)
    owning_session = session_service.create_session(CreateSessionCommand(title="Run 所属会话"))
    other_session = session_service.create_session(CreateSessionCommand(title="输入消息所属会话"))
    executor = FakeExecutor()

    session = persistence_runtime.session_factory()
    try:
        message_repository = SqlAlchemyMessageRepository(session)
        run_repository = SqlAlchemyDiagnosisRunRepository(session)
        input_message = MessageData(
            session_id=other_session.id,
            role=MessageRole.USER,
            content="跨 Session 输入",
        )
        message_repository.add(input_message)
        session.flush()
        invalid_run = DiagnosisRunData(
            session_id=owning_session.id,
            input_message_id=input_message.id,
            status=RunStatus.QUEUED,
        )
        run_repository.add(invalid_run)
        session.commit()
    finally:
        session.close()

    service = RunApplicationService(
        persistence_runtime.session_factory,
        executor,
        ConservativeResultAssembler(),
    )
    failed = service.execute_run(invalid_run.id)
    assert failed.status == RunStatus.FAILED
    assert failed.error_code == "DIAGNOSIS_FAILED"
    assert failed.error_message == "诊断执行失败，请稍后重试"
    assert executor.calls == []
    events = _load_events(persistence_runtime, invalid_run.id)
    assert [event.type for event in events] == [RunEventType.RUN_FAILED]
    assert events[-1].data == {"state": "failed", "code": "DIAGNOSIS_FAILED"}



def test_执行事件拒绝非UTC时间() -> None:
    """执行器在进入 Application Service 前不得提供 naive 时间。"""
    with pytest.raises(ValueError, match="UTC aware"):
        DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="route",
            occurred_at=datetime(2026, 7, 26, 9, 0, 0),
        )
