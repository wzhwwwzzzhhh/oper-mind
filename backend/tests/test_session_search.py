"""P8 会话搜索 `GET /sessions?q=` 的标题关键词匹配与参数校验测试。"""

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
from src.domain.diagnosis import SessionStatus
from src.domain.records import SessionData
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import SqlAlchemySessionRepository

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _DeterministicExecutor:
    def stream(self, _query: str) -> Iterator[object]:
        yield from ()


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> PersistenceRuntime:
    database_path = tmp_path / "session-search.sqlite3"
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


def _insert_session(
    runtime: PersistenceRuntime,
    *,
    title: str,
    status: SessionStatus = SessionStatus.ACTIVE,
    updated_at: datetime | None = None,
) -> UUID:
    session_id = uuid4()
    created_at = updated_at or datetime.now(UTC)
    session = runtime.session_factory()
    try:
        SqlAlchemySessionRepository(session).add(
            SessionData(
                id=session_id,
                title=title,
                status=status,
                created_at=created_at,
                updated_at=created_at,
            )
        )
        session.commit()
    finally:
        session.close()
    return session_id


def test_标题关键词只返回匹配会话(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC5：q 按标题字面匹配，只返回包含关键词的会话。"""
    _insert_session(persistence_runtime, title="慢查询排查")
    _insert_session(persistence_runtime, title="Redis 缓存调查")
    _insert_session(persistence_runtime, title="索引优化方案")

    response = v1_client.get("/api/v1/sessions", params={"q": "调查"})

    assert response.status_code == 200
    body = response.json()
    assert [item["title"] for item in body["items"]] == ["Redis 缓存调查"]
    assert body["page"]["has_more"] is False


def test_无匹配返回空列表(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC5：无匹配返回空列表与 has_more=false，不抛错。"""
    _insert_session(persistence_runtime, title="慢查询排查")

    response = v1_client.get("/api/v1/sessions", params={"q": "不存在的关键词"})

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["page"]["has_more"] is False


def test_不带q行为与既有契约一致(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC6：无 q 时返回全部会话，按更新时间倒序（兼容扩展，行为不变）。"""
    older = _insert_session(
        persistence_runtime, title="较早会话", updated_at=datetime.now(UTC) - timedelta(minutes=2)
    )
    newer = _insert_session(persistence_runtime, title="较新会话")

    response = v1_client.get("/api/v1/sessions")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(newer), str(older)]
    assert items[0]["status"] == "active"


def test_搜索与状态过滤正交组合(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """q 与 status 独立组合：只搜 active 会话时，归档会话不返回。"""
    _insert_session(persistence_runtime, title="活跃的慢查询会话")
    archived = _insert_session(
        persistence_runtime, title="已归档的慢查询会话", status=SessionStatus.ARCHIVED
    )

    response = v1_client.get("/api/v1/sessions", params={"q": "慢查询", "status": "active"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] != str(archived)
    assert items[0]["title"] == "活跃的慢查询会话"


def test_关键词通配符按字面匹配(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """q 中的 % / _ 按字面处理，不作为 LIKE 通配符。"""
    _insert_session(persistence_runtime, title="命中率 100% 告警")
    _insert_session(persistence_runtime, title="普通会话")

    percent = v1_client.get("/api/v1/sessions", params={"q": "100%"})
    assert percent.status_code == 200
    assert [item["title"] for item in percent.json()["items"]] == ["命中率 100% 告警"]

    wildcard = v1_client.get("/api/v1/sessions", params={"q": "%"})
    assert wildcard.status_code == 200
    assert [item["title"] for item in wildcard.json()["items"]] == ["命中率 100% 告警"]


def test_非法关键词返回明确错误(v1_client: TestClient) -> None:
    """AC7：超长 / 控制字符 / 纯空白关键词返回 422 明确错误。"""
    too_long = v1_client.get("/api/v1/sessions", params={"q": "长" * 101})
    assert too_long.status_code == 422

    control_char = v1_client.get("/api/v1/sessions", params={"q": "关键词\x01"})
    assert control_char.status_code == 422
    assert control_char.json()["error"]["code"] == "VALIDATION_ERROR"

    blank = v1_client.get("/api/v1/sessions", params={"q": "   "})
    assert blank.status_code == 422
    assert blank.json()["error"]["code"] == "VALIDATION_ERROR"


def test_搜索关键词首尾空白被规范化(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """关键词 strip 后参与匹配，不影响结果。"""
    _insert_session(persistence_runtime, title="慢查询排查")

    response = v1_client.get("/api/v1/sessions", params={"q": "  慢查询  "})

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["items"]] == ["慢查询排查"]
