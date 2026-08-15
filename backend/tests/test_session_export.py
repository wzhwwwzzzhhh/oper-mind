"""P8 会话导出 `GET /sessions/{id}/export` 的安全摘要文档测试（AC1–AC7）。"""

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
from sqlalchemy.exc import OperationalError

from src.api.v1.dependencies import V1Services
from src.application.action_services import ActionApplicationService
from src.application.services import RunApplicationService, SessionApplicationService
from src.application.session_export import SessionExportApplicationService
from src.domain.diagnosis import DiagnosisSeverity, MessageRole, RunStatus, SessionStatus
from src.domain.records import (
    DiagnosisResultData,
    DiagnosisRunData,
    MessageData,
    SessionData,
)
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisResultRepository,
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemySessionExportStore,
    SqlAlchemySessionRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

SENSITIVE_SK = "sk-abcdef123456"
SENSITIVE_DSN_WITH_PASSWORD = "postgresql://admin:hunter2@db.internal:5432/app"  # noqa: S105
SENSITIVE_DSN_BARE = "postgresql://prod-db:5432/app"


class _DeterministicExecutor:
    def stream(self, _query: str) -> Iterator[object]:
        yield from ()


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> PersistenceRuntime:
    database_path = tmp_path / "session-export.sqlite3"
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


@pytest.fixture
def v1_services(persistence_runtime: PersistenceRuntime) -> V1Services:
    return V1Services(
        session_factory=persistence_runtime.session_factory,
        session_service=SessionApplicationService(persistence_runtime.session_factory),
        run_service=RunApplicationService(
            persistence_runtime.session_factory,
            _DeterministicExecutor(),
            ConservativeResultAssembler(),
        ),
        action_service=ActionApplicationService(persistence_runtime.session_factory, executor=None),
        session_export_service=SessionExportApplicationService(
            lambda: SqlAlchemySessionExportStore(persistence_runtime.session_factory())
        ),
    )


@pytest.fixture
def v1_client(
    monkeypatch: pytest.MonkeyPatch, v1_services: V1Services
) -> Iterator[TestClient]:
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", "")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", v1_services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client


def _insert_session(
    runtime: PersistenceRuntime,
    *,
    title: str,
    created_at: datetime | None = None,
) -> UUID:
    session_id = uuid4()
    moment = created_at or datetime.now(UTC)
    session = runtime.session_factory()
    try:
        SqlAlchemySessionRepository(session).add(
            SessionData(
                id=session_id,
                title=title,
                status=SessionStatus.ACTIVE,
                created_at=moment,
                updated_at=moment,
            )
        )
        session.commit()
    finally:
        session.close()
    return session_id


def _insert_message(
    runtime: PersistenceRuntime,
    *,
    session_id: UUID,
    role: MessageRole,
    content: str,
    created_at: datetime,
) -> UUID:
    message_id = uuid4()
    session = runtime.session_factory()
    try:
        SqlAlchemyMessageRepository(session).add(
            MessageData(
                id=message_id,
                session_id=session_id,
                role=role,
                content=content,
                created_at=created_at,
            )
        )
        session.commit()
    finally:
        session.close()
    return message_id


def _insert_run(
    runtime: PersistenceRuntime,
    *,
    session_id: UUID,
    input_message_id: UUID,
    service_id: str | None,
    status: RunStatus,
    created_at: datetime,
    error_code: str | None = None,
    error_message: str | None = None,
) -> UUID:
    run_id = uuid4()
    session = runtime.session_factory()
    try:
        SqlAlchemyDiagnosisRunRepository(session).add(
            DiagnosisRunData(
                id=run_id,
                session_id=session_id,
                trace_id=uuid4(),
                input_message_id=input_message_id,
                service_id=service_id,
                status=status,
                created_at=created_at,
                error_code=error_code,
                error_message=error_message,
            )
        )
        session.commit()
    finally:
        session.close()
    return run_id


def _insert_result(
    runtime: PersistenceRuntime,
    *,
    run_id: UUID,
    summary: str,
    created_at: datetime,
    severity: DiagnosisSeverity = DiagnosisSeverity.MEDIUM,
    confidence: float = 0.9,
) -> None:
    session = runtime.session_factory()
    try:
        SqlAlchemyDiagnosisResultRepository(session).add(
            DiagnosisResultData(
                run_id=run_id,
                summary=summary,
                severity=severity,
                confidence=confidence,
                root_causes=[],
                evidence=[
                    {
                        "id": str(uuid4()),
                        "source_type": "database",
                        "source_name": "postgres_read_only",
                        "title": "orders 表缺联合索引",
                        "summary": "只读数据库事实支持缺索引信号。",
                        "locator": None,
                        "observed_at": None,
                        "attributes": {"table": "orders"},
                    }
                ],
                impact=None,
                recommendations=[],
                risks=[],
                requires_approval=False,
                agent_summary=[],
                report_markdown="## 诊断报告\n订单服务变慢与缺索引有关。",
                created_at=created_at,
            )
        )
        session.commit()
    finally:
        session.close()


def _insert_exportable_session(runtime: PersistenceRuntime, title: str = "慢查询排查") -> tuple[UUID, list[UUID]]:
    """插入一个带消息时间线 + 成功 Run + 结果的会话，返回 (session_id, [message_ids])。"""
    base = datetime.now(UTC)
    session_id = _insert_session(runtime, title=title, created_at=base)
    user_id = _insert_message(
        runtime, session_id=session_id, role=MessageRole.USER, content="订单服务变慢，帮我排查慢查询。", created_at=base
    )
    assistant_id = _insert_message(
        runtime,
        session_id=session_id,
        role=MessageRole.ASSISTANT,
        content="这是普通对话回复：本次未启动调查。",
        created_at=base + timedelta(seconds=1),
    )
    system_id = _insert_message(
        runtime,
        session_id=session_id,
        role=MessageRole.SYSTEM,
        content="会话已创建",
        created_at=base + timedelta(seconds=2),
    )
    run_id = _insert_run(
        runtime,
        session_id=session_id,
        input_message_id=user_id,
        service_id="pg-orders",
        status=RunStatus.SUCCEEDED,
        created_at=base + timedelta(seconds=3),
    )
    _insert_result(
        runtime,
        run_id=run_id,
        summary="订单服务变慢与 orders 表缺少联合索引有关。",
        created_at=base + timedelta(seconds=4),
    )
    return session_id, [user_id, assistant_id, system_id]


def test_导出包含会话标题与消息时间线(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC1：导出文档包含会话标题与消息时间线（user/assistant/system 安全投影）。"""
    session_id, _ = _insert_exportable_session(persistence_runtime)

    response = v1_client.get(f"/api/v1/sessions/{session_id}/export")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    text = response.text
    assert "# 慢查询排查" in text
    assert "订单服务变慢，帮我排查慢查询。" in text
    assert "这是普通对话回复：本次未启动调查。" in text
    assert "会话已创建" in text
    assert "## 对话时间线" in text


def test_导出包含Run结论摘要(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC2：导出包含各 Run 的结论摘要（query/status/severity/confidence/summary/证据摘要）。"""
    session_id, _ = _insert_exportable_session(persistence_runtime)

    response = v1_client.get(f"/api/v1/sessions/{session_id}/export")

    assert response.status_code == 200
    text = response.text
    assert "## 调查摘要" in text
    assert "**问题**：订单服务变慢，帮我排查慢查询。" in text
    assert "**状态**：succeeded" in text
    assert "**目标服务**：pg-orders" in text
    assert "**严重度**：medium" in text
    assert "**置信度**：0.9" in text
    assert "**结论**：订单服务变慢与 orders 表缺少联合索引有关。" in text
    assert "orders 表缺联合索引" in text
    assert "只读数据库事实支持缺索引信号。" in text


def test_会话不存在返回404(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC3：会话不存在返回 404 SESSION_NOT_FOUND。"""
    response = v1_client.get(f"/api/v1/sessions/{uuid4()}/export")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_空会话返回明确空态(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC4：无可导出内容时返回明确空态文档，不抛错、不伪造。"""
    session_id = _insert_session(persistence_runtime, title="空会话")

    response = v1_client.get(f"/api/v1/sessions/{session_id}/export")

    assert response.status_code == 200
    text = response.text
    assert "# 空会话" in text
    assert "无可导出内容" in text


def test_读取失败返回503(v1_client: TestClient, v1_services: V1Services) -> None:
    """AC5：数据读取失败返回 503 EXPORT_UNAVAILABLE，不返回半截文档。"""
    def _raising_factory() -> object:
        raise OperationalError("SELECT 1", {}, Exception("数据库不可用"))

    object.__setattr__(
        v1_services,
        "session_export_service",
        SessionExportApplicationService(_raising_factory),  # type: ignore[arg-type]
    )

    response = v1_client.get(f"/api/v1/sessions/{uuid4()}/export")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EXPORT_UNAVAILABLE"


def test_导出不含敏感内容(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC6：导出不含 sk- 密钥、完整 DSN（含/不含凭据）与原始错误文本。"""
    base = datetime.now(UTC)
    session_id = _insert_session(runtime=persistence_runtime, title="敏感内容会话", created_at=base)
    user_id = _insert_message(
        persistence_runtime,
        session_id=session_id,
        role=MessageRole.USER,
        content=f"连接串是 {SENSITIVE_DSN_WITH_PASSWORD}，密钥 {SENSITIVE_SK}，生产库 {SENSITIVE_DSN_BARE}",
        created_at=base,
    )
    _insert_run(
        persistence_runtime,
        session_id=session_id,
        input_message_id=user_id,
        service_id=None,
        status=RunStatus.FAILED,
        created_at=base + timedelta(seconds=1),
        error_code="DIAGNOSIS_FAILED",
        error_message="内部错误：连接磁盘阵列失败，堆栈 traceback 未脱敏",
    )

    response = v1_client.get(f"/api/v1/sessions/{session_id}/export")

    assert response.status_code == 200
    text = response.text
    for forbidden in (SENSITIVE_DSN_WITH_PASSWORD, SENSITIVE_SK, SENSITIVE_DSN_BARE, "hunter2", "磁盘阵列"):
        assert forbidden not in text
    assert "[已脱敏" in text
    assert "诊断执行失败，请稍后重试" in text


def test_重复导出一致(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC7：相同会话重复导出内容一致（确定性，不含导出时间等不稳定字段）。"""
    session_id, _ = _insert_exportable_session(persistence_runtime)

    first = v1_client.get(f"/api/v1/sessions/{session_id}/export")
    second = v1_client.get(f"/api/v1/sessions/{session_id}/export")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.text == second.text


def test_大会话截断并在文档注明(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """大会话：消息超过 500 条时只导出最近 500 条并在文档头部注明截断。"""
    base = datetime.now(UTC)
    session_id = _insert_session(persistence_runtime, title="大会话", created_at=base)
    earliest = _insert_message(
        persistence_runtime, session_id=session_id, role=MessageRole.USER, content="最早的一条消息", created_at=base
    )
    for index in range(504):
        _insert_message(
            persistence_runtime,
            session_id=session_id,
            role=MessageRole.USER,
            content=f"消息 {index}",
            created_at=base + timedelta(seconds=index + 1),
        )
    _insert_run(
        persistence_runtime,
        session_id=session_id,
        input_message_id=earliest,
        service_id=None,
        status=RunStatus.CANCELLED,
        created_at=base + timedelta(seconds=600),
    )

    response = v1_client.get(f"/api/v1/sessions/{session_id}/export")

    assert response.status_code == 200
    text = response.text
    assert "仅导出最近 500 条消息" in text
    assert "最早的一条消息" not in text
    assert "消息 503" in text
