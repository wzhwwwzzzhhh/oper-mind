"""P8 全局 Run 列表 `GET /runs` 的安全摘要、过滤与分页测试。"""

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
from src.application.action_services import ActionApplicationService
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import MessageRole, RunStatus, SessionStatus
from src.domain.records import DiagnosisRunData, MessageData, SessionData
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemyDiagnosisRunRepository,
    SqlAlchemyMessageRepository,
    SqlAlchemySessionRepository,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _DeterministicExecutor:
    def stream(self, _query: str) -> Iterator[object]:
        yield from ()


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> PersistenceRuntime:
    database_path = tmp_path / "runs-list.sqlite3"
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
def v1_client(monkeypatch: pytest.MonkeyPatch, persistence_runtime: PersistenceRuntime) -> Iterator[TestClient]:
    services = V1Services(
        session_factory=persistence_runtime.session_factory,
        session_service=SessionApplicationService(persistence_runtime.session_factory),
        run_service=RunApplicationService(
            persistence_runtime.session_factory,
            _DeterministicExecutor(),
            ConservativeResultAssembler(),
        ),
        action_service=ActionApplicationService(persistence_runtime.session_factory, executor=None),
    )
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", "")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client


def _insert_run_graph(
    runtime: PersistenceRuntime,
    *,
    session_title: str,
    run_id: UUID,
    session_id: UUID,
    message_id: UUID,
    trace_id: UUID,
    service_id: str | None,
    status: RunStatus,
    created_at: datetime,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    """经 Repository 落一组满足外键的 Session + Message + Run。"""
    session = runtime.session_factory()
    try:
        session_repository = SqlAlchemySessionRepository(session)
        session_repository.add(
            SessionData(
                id=session_id,
                title=session_title,
                status=SessionStatus.ACTIVE,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.flush()
        message_repository = SqlAlchemyMessageRepository(session)
        message_repository.add(
            MessageData(
                id=message_id,
                session_id=session_id,
                role=MessageRole.USER,
                content="检查全局列表",
                created_at=created_at,
            )
        )
        session.flush()
        run_repository = SqlAlchemyDiagnosisRunRepository(session)
        run_repository.add(
            DiagnosisRunData(
                id=run_id,
                session_id=session_id,
                trace_id=trace_id,
                input_message_id=message_id,
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


def _run_args(now: datetime) -> dict[str, object]:
    """生成一组互不相同的 UUID 与创建时间。"""
    return {
        "run_id": uuid4(),
        "session_id": uuid4(),
        "message_id": uuid4(),
        "trace_id": uuid4(),
        "created_at": now,
    }


def test_跨会话跨服务返回安全摘要分页列表(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC1：跨会话跨服务返回 Run 安全摘要，按发起时间倒序，含会话标题。"""
    now = datetime.now(UTC)
    first = _run_args(now)
    _insert_run_graph(
        persistence_runtime, session_title="跨会话一", service_id="postgres-production", status=RunStatus.SUCCEEDED, **first
    )
    second = _run_args(now - timedelta(minutes=1))
    _insert_run_graph(
        persistence_runtime, session_title="跨会话二", service_id="redis-production", status=RunStatus.QUEUED, **second
    )

    response = v1_client.get("/api/v1/runs")

    assert response.status_code == 200
    body = response.json()
    items = body["items"]
    assert [item["id"] for item in items] == [str(first["run_id"]), str(second["run_id"])]
    assert items[0]["session_id"] == str(first["session_id"])
    assert items[0]["session_title"] == "跨会话一"
    assert items[0]["service_id"] == "postgres-production"
    assert items[0]["status"] == "succeeded"
    assert items[0]["created_at"] is not None
    assert body["page"]["has_more"] is False


def test_状态过滤只返回匹配状态的Run(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC2：按状态过滤只返回匹配状态的 Run。"""
    now = datetime.now(UTC)
    succeeded = _run_args(now - timedelta(minutes=1))
    _insert_run_graph(
        persistence_runtime, session_title="已成功", service_id=None, status=RunStatus.SUCCEEDED, **succeeded
    )
    queued = _run_args(now)
    _insert_run_graph(persistence_runtime, session_title="排队中", service_id=None, status=RunStatus.QUEUED, **queued)

    response = v1_client.get("/api/v1/runs", params={"status": "queued"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(queued["run_id"])]
    assert items[0]["status"] == "queued"


def test_服务过滤只返回该服务的Run且不存在服务返回空列表(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC3：service_id 过滤只返回该服务的 Run；不存在的 service_id 返回空列表不抛错。"""
    now = datetime.now(UTC)
    target = _run_args(now)
    _insert_run_graph(
        persistence_runtime, session_title="靶场会话", service_id="postgres-target", status=RunStatus.SUCCEEDED, **target
    )
    other = _run_args(now - timedelta(minutes=1))
    _insert_run_graph(
        persistence_runtime, session_title="生产会话", service_id="postgres-production", status=RunStatus.FAILED, **other
    )

    matched = v1_client.get("/api/v1/runs", params={"service_id": "postgres-target"})
    assert matched.status_code == 200
    assert [item["id"] for item in matched.json()["items"]] == [str(target["run_id"])]

    missing = v1_client.get("/api/v1/runs", params={"service_id": "not-exist"})
    assert missing.status_code == 200
    assert missing.json()["items"] == []
    assert missing.json()["page"]["has_more"] is False


def test_摘要字段白名单且失败错误经白名单映射(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC4：摘要只含白名单字段；失败 Run 的错误经安全映射，不泄漏原始错误文本。"""
    now = datetime.now(UTC)
    failed = _run_args(now)
    _insert_run_graph(
        persistence_runtime,
        session_title="失败会话",
        service_id="postgres-production",
        status=RunStatus.FAILED,
        error_code="DIAGNOSIS_FAILED",
        error_message="诊断执行失败，请稍后重试",
        **failed,
    )

    response = v1_client.get("/api/v1/runs")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert set(item.keys()) == {"id", "session_id", "session_title", "service_id", "status", "created_at", "error"}
    assert item["error"] == {"code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}
    for forbidden in ("trace_id", "input_message_id", "result", "error_code", "error_message", "evidence", "summary"):
        assert forbidden not in item


def test_非白名单错误文本被收敛为通用摘要(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC4 纵深防御：未注册的错误文本一律收敛为通用摘要，绝不透传。"""
    now = datetime.now(UTC)
    raw = _run_args(now)
    _insert_run_graph(
        persistence_runtime,
        session_title="异常会话",
        service_id=None,
        status=RunStatus.FAILED,
        error_code="UNKNOWN_FAILURE",
        error_message="connect: 10.0.0.1:5432 password=secret",
        **raw,
    )

    response = v1_client.get("/api/v1/runs")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["error"] == {"code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}


def test_按创建时间倒序cursor分页(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """cursor 分页：按创建时间倒序，下一页只含更早的 Run。"""
    now = datetime.now(UTC)
    first = _run_args(now)
    second = _run_args(now - timedelta(minutes=1))
    third = _run_args(now - timedelta(minutes=2))
    for index, args in enumerate((first, second, third), start=1):
        _insert_run_graph(
            persistence_runtime, session_title=f"分页会话{index}", service_id=None, status=RunStatus.SUCCEEDED, **args
        )

    page_one = v1_client.get("/api/v1/runs", params={"limit": 2})
    assert page_one.status_code == 200
    body_one = page_one.json()
    assert [item["id"] for item in body_one["items"]] == [str(first["run_id"]), str(second["run_id"])]
    assert body_one["page"]["has_more"] is True
    assert body_one["page"]["next_cursor"] is not None

    page_two = v1_client.get("/api/v1/runs", params={"limit": 2, "cursor": body_one["page"]["next_cursor"]})
    assert page_two.status_code == 200
    body_two = page_two.json()
    assert [item["id"] for item in body_two["items"]] == [str(third["run_id"])]
    assert body_two["page"]["has_more"] is False
    assert body_two["page"]["next_cursor"] is None


def test_空列表返回诚实空态(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """无 Run 时返回空列表与 has_more=false，不伪造。"""
    response = v1_client.get("/api/v1/runs")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["page"]["has_more"] is False


def test_非法状态与非法游标返回明确错误(v1_client: TestClient) -> None:
    """参数非法返回明确错误：非法 status 422，非法 cursor 400。"""
    bad_status = v1_client.get("/api/v1/runs", params={"status": "not_a_status"})
    assert bad_status.status_code == 422

    bad_cursor = v1_client.get("/api/v1/runs", params={"cursor": "not-a-cursor"})
    assert bad_cursor.status_code == 400
    assert bad_cursor.json()["error"]["code"] == "INVALID_CURSOR"
