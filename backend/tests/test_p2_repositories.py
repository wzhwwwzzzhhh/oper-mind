"""P2.2b SQLAlchemy Repository 的查询与事务边界验证。"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy.orm import Session

from src.domain.diagnosis import DiagnosisSeverity, MessageRole, RunEventType, RunStatus, SessionStatus
from src.domain.records import (
    DiagnosisResultData,
    DiagnosisRunData,
    MessageData,
    RunEventData,
    RunIdempotencyKeyData,
    SessionData,
)
from src.infrastructure.persistence.database import create_persistence_runtime
from src.infrastructure.persistence.models import SessionRecord
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemyRunEventRepository,
    SqlAlchemyRunIdempotencyKeyRepository,
    SqlAlchemySessionRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _migration_environment(database_path: Path) -> dict[str, str]:
    """构造不依赖测试执行目录的临时数据库迁移环境。"""
    environment = os.environ.copy()
    existing_python_path = environment.get("PYTHONPATH")
    python_path = [str(BACKEND_ROOT), str(PROJECT_ROOT)]
    if existing_python_path:
        python_path.append(existing_python_path)
    environment.update(
        {
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
            "PYTHONPATH": os.pathsep.join(python_path),
        }
    )
    return environment


@pytest.fixture
def repository_session(tmp_path: Path):
    """迁移独立临时 SQLite 并提供由测试控制事务的 Session。"""
    database_path = tmp_path / "repositories.sqlite3"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=tmp_path,
        env=_migration_environment(database_path),
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr

    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    session = runtime.session_factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        runtime.engine.dispose()


def _time(second: int) -> datetime:
    """生成固定且可排序的 UTC aware 测试时间。"""
    return datetime(2026, 7, 26, 9, 0, second, tzinfo=UTC)


def _uuid(number: int) -> UUID:
    """生成可预测的 UUID，便于验证复合排序。"""
    return UUID(int=number)


def _add_session(repository: SqlAlchemySessionRepository, number: int, created_at: datetime) -> SessionData:
    """构造并 staged add 一个测试 Session。"""
    session = SessionData(
        id=_uuid(number),
        title=f"会话 {number}",
        status=SessionStatus.ACTIVE,
        created_at=created_at,
        updated_at=created_at,
    )
    repository.add(session)
    return session


def _add_run_graph(session: Session, created_at: datetime) -> tuple[SessionData, MessageData, DiagnosisRunData]:
    """通过 Repository staged add 一组满足外键的 Session、Message 与 Run。"""
    session_repository = SqlAlchemySessionRepository(session)
    message_repository = SqlAlchemyMessageRepository(session)
    run_repository = SqlAlchemyDiagnosisRunRepository(session)

    session_data = _add_session(session_repository, 100, created_at)
    session.flush()
    message_data = MessageData(
        id=_uuid(101),
        session_id=session_data.id,
        role=MessageRole.USER,
        content="检查 Repository",
        created_at=created_at,
    )
    message_repository.add(message_data)
    session.flush()
    run_data = DiagnosisRunData(
        id=_uuid(102),
        session_id=session_data.id,
        trace_id=_uuid(103),
        input_message_id=message_data.id,
        service_id="postgres-staging",
        status=RunStatus.QUEUED,
        created_at=created_at,
    )
    run_repository.add(run_data)
    session.flush()
    return session_data, message_data, run_data


def test_repositories_六类对象可staged_add并读取(repository_session: Session) -> None:
    """六类 Repository 均可在调用方事务内写入并返回领域数据对象。"""
    session_data, message_data, run_data = _add_run_graph(repository_session, _time(1))
    event_data = RunEventData(
        id=_uuid(104),
        run_id=run_data.id,
        sequence=1,
        type=RunEventType.RUN_QUEUED,
        occurred_at=_time(2),
        data={"source": "repository-test"},
    )
    result_data = DiagnosisResultData(
        id=_uuid(105),
        run_id=run_data.id,
        summary="安全结果",
        severity=DiagnosisSeverity.LOW,
        confidence=0.5,
        root_causes=[],
        evidence=[],
        recommendations=[],
        risks=[],
        requires_approval=False,
        agent_summary=[],
        created_at=_time(3),
    )
    idempotency_data = RunIdempotencyKeyData(
        id=_uuid(106),
        session_id=session_data.id,
        endpoint="/api/v1/sessions/{session_id}/runs",
        idempotency_key=_uuid(107),
        request_fingerprint="a" * 64,
        run_id=run_data.id,
        expires_at=_time(30),
        created_at=_time(4),
    )

    event_repository = SqlAlchemyRunEventRepository(repository_session)
    result_repository = SqlAlchemyDiagnosisResultRepository(repository_session)
    idempotency_repository = SqlAlchemyRunIdempotencyKeyRepository(repository_session)
    event_repository.add(event_data)
    result_repository.add(result_data)
    idempotency_repository.add(idempotency_data)
    repository_session.flush()

    assert SqlAlchemySessionRepository(repository_session).get_by_id(session_data.id) == session_data
    assert SqlAlchemyMessageRepository(repository_session).get_by_id(message_data.id) == message_data
    assert SqlAlchemyDiagnosisRunRepository(repository_session).get_by_id(run_data.id) == run_data
    assert event_repository.list_by_run(run_data.id, cursor=None, limit=10).items == [event_data]
    assert result_repository.get_by_run_id(run_data.id) == result_data
    assert idempotency_repository.get_by_scope(
        session_data.id,
        idempotency_data.endpoint,
        idempotency_data.idempotency_key,
    ) == idempotency_data


def test_session_message_run_event分页遵循固定排序(repository_session: Session) -> None:
    """四类列表查询以 P0.3/P2.1 固定顺序和复合 cursor 读取 limit + 1。"""
    session_repository = SqlAlchemySessionRepository(repository_session)
    session_one = _add_session(session_repository, 1, _time(1))
    session_two = _add_session(session_repository, 2, _time(2))
    session_three = _add_session(session_repository, 3, _time(2))
    archived = SessionData(
        id=_uuid(4),
        title="归档会话",
        status=SessionStatus.ARCHIVED,
        created_at=_time(4),
        updated_at=_time(4),
        archived_at=_time(4),
    )
    session_repository.add(archived)
    repository_session.flush()

    first_sessions = session_repository.list_page(cursor=None, limit=2, status=SessionStatus.ACTIVE)
    assert [item.id for item in first_sessions.items] == [session_three.id, session_two.id]
    assert first_sessions.has_more is True
    assert first_sessions.next_cursor is not None
    second_sessions = session_repository.list_page(
        cursor=first_sessions.next_cursor,
        limit=2,
        status=SessionStatus.ACTIVE,
    )
    assert [item.id for item in second_sessions.items] == [session_one.id]
    assert second_sessions.has_more is False
    assert session_repository.list_page(cursor=None, limit=10, status=SessionStatus.ARCHIVED).items == [archived]

    message_repository = SqlAlchemyMessageRepository(repository_session)
    message_one = MessageData(
        id=_uuid(11), session_id=session_one.id, role=MessageRole.USER, content="一", created_at=_time(5)
    )
    message_two = MessageData(
        id=_uuid(12), session_id=session_one.id, role=MessageRole.SYSTEM, content="二", created_at=_time(6)
    )
    message_three = MessageData(
        id=_uuid(13), session_id=session_one.id, role=MessageRole.ASSISTANT, content="三", created_at=_time(6)
    )
    message_repository.add(message_one)
    message_repository.add(message_two)
    message_repository.add(message_three)
    repository_session.flush()
    first_messages = message_repository.list_by_session(session_one.id, cursor=None, limit=2)
    assert [item.id for item in first_messages.items] == [message_one.id, message_two.id]
    assert first_messages.has_more is True
    assert first_messages.next_cursor is not None
    second_messages = message_repository.list_by_session(session_one.id, cursor=first_messages.next_cursor, limit=2)
    assert [item.id for item in second_messages.items] == [message_three.id]

    run_repository = SqlAlchemyDiagnosisRunRepository(repository_session)
    run_one = DiagnosisRunData(
        id=_uuid(21),
        session_id=session_one.id,
        trace_id=_uuid(121),
        input_message_id=message_one.id,
        created_at=_time(7),
    )
    run_two = DiagnosisRunData(
        id=_uuid(22),
        session_id=session_one.id,
        trace_id=_uuid(122),
        input_message_id=message_two.id,
        created_at=_time(8),
    )
    run_three = DiagnosisRunData(
        id=_uuid(23),
        session_id=session_one.id,
        trace_id=_uuid(123),
        input_message_id=message_three.id,
        created_at=_time(8),
    )
    run_repository.add(run_one)
    run_repository.add(run_two)
    run_repository.add(run_three)
    repository_session.flush()
    first_runs = run_repository.list_by_session(session_one.id, cursor=None, limit=2)
    assert [item.id for item in first_runs.items] == [run_three.id, run_two.id]
    assert first_runs.has_more is True
    assert first_runs.next_cursor is not None
    assert [item.id for item in run_repository.list_by_session(session_one.id, first_runs.next_cursor, 2).items] == [
        run_one.id
    ]

    event_repository = SqlAlchemyRunEventRepository(repository_session)
    for sequence in (1, 2, 3):
        event_repository.add(
            RunEventData(
                id=_uuid(30 + sequence),
                run_id=run_one.id,
                sequence=sequence,
                type=RunEventType.RUN_QUEUED if sequence == 1 else RunEventType.AGENT_DONE,
                occurred_at=_time(10 + sequence),
                data={"sequence": sequence},
            )
        )
    repository_session.flush()
    first_events = event_repository.list_by_run(run_one.id, cursor=None, limit=2)
    assert [item.sequence for item in first_events.items] == [1, 2]
    assert first_events.has_more is True
    assert first_events.next_cursor is not None
    assert [item.sequence for item in event_repository.list_by_run(run_one.id, first_events.next_cursor, 2).items] == [3]


def test_repositories_不自行提交或回滚(repository_session: Session, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repository 只能 staged add/read，事务提交和回滚始终由调用方负责。"""
    session_repository = SqlAlchemySessionRepository(repository_session)
    session_data = SessionData(id=_uuid(200), title="事务边界", created_at=_time(20), updated_at=_time(20))

    def forbid_transaction_control() -> None:
        raise AssertionError("Repository 不得自行控制事务。")

    monkeypatch.setattr(repository_session, "commit", forbid_transaction_control)
    monkeypatch.setattr(repository_session, "rollback", forbid_transaction_control)
    session_repository.add(session_data)
    repository_session.flush()
    assert session_repository.get_by_id(session_data.id) == session_data
    assert repository_session.get(SessionRecord, session_data.id) is not None


def test_repository_数据对象拒绝naive时间() -> None:
    """跨 Repository 边界的时间必须在进入基础设施前已是 UTC aware。"""
    with pytest.raises(ValidationError, match="UTC aware"):
        SessionData(
            title="无时区",
            created_at=datetime(2026, 7, 26, 9, 0, 0),
            updated_at=_time(1),
        )



def test_repository_拒绝非正页大小(repository_session: Session) -> None:
    """分页参数在 Repository 边界必须为正数。"""
    repository = SqlAlchemySessionRepository(repository_session)

    with pytest.raises(ValueError, match="limit"):
        repository.list_page(cursor=None, limit=0)



def test_repository_数据对象校验受控值与数值边界() -> None:
    """Repository 数据对象在进入 ORM 前拒绝无效的受控值和数值。"""
    with pytest.raises(ValidationError):
        DiagnosisResultData(
            id=_uuid(300),
            run_id=_uuid(301),
            summary="无效严重性",
            severity="urgent",
            confidence=0.5,
            root_causes=[],
            evidence=[],
            recommendations=[],
            risks=[],
            requires_approval=False,
            agent_summary=[],
        )
    with pytest.raises(ValidationError):
        RunEventData(
            id=_uuid(302),
            run_id=_uuid(303),
            sequence=0,
            type=RunEventType.RUN_QUEUED,
            data={},
        )
