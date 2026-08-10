"""P8 独立消息通道——普通消息轻量回复的 API 测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.contracts import DiagnosisExecutionError, DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.application.plain_messages import PLAIN_REPLY_PREFIX, PLAIN_REPLY_TEMPLATE, PlainMessageApplicationService
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import create_persistence_runtime

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _DeterministicExecutor:
    """不访问真实 Agent、只输出一条安全事件的确定性执行器。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        yield DiagnosisExecutionEvent(type=RunEventType.ROUTE_DECIDED, node="route")
        yield DiagnosisExecutionResult(strategy="direct")


def _upgrade_temporary_database(database_path: Path) -> None:
    """只通过 Alembic 在临时 SQLite 文件创建 schema。"""
    environment = os.environ.copy()
    environment.update(
        {
            "PYTHONPATH": os.pathsep.join((str(BACKEND_ROOT), str(PROJECT_ROOT))),
            "OPERMIND_APP_DATABASE_URL": f"sqlite:///{database_path.as_posix()}",
            "OPERMIND_API_KEY": "mock",
            "OPERMIND_BASE_URL": "http://mock",
            "OPERMIND_MODEL": "mock",
        }
    )
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


@pytest.fixture
def v1_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以迁移后的临时 SQLite 装配含独立消息通道的 v1 客户端。"""
    database_path = tmp_path / "p8-plain-message.sqlite3"
    _upgrade_temporary_database(database_path)
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    services = V1Services(
        session_factory=runtime.session_factory,
        session_service=SessionApplicationService(runtime.session_factory),
        run_service=RunApplicationService(
            runtime.session_factory,
            _DeterministicExecutor(),
            ConservativeResultAssembler(),
        ),
        plain_message_service=PlainMessageApplicationService(runtime.session_factory),
    )

    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    runtime.engine.dispose()


def _create_session(client: TestClient, title: str = "P8 普通消息会话") -> dict[str, object]:
    response = client.post("/api/v1/sessions", json={"title": title})
    assert response.status_code == 201
    return response.json()["session"]


def test_普通消息返回轻量回复且不创建Run(v1_client: TestClient) -> None:
    """AC1/AC3：普通消息只回一条 assistant 普通回复，不创建新 Run、不触发调查。"""
    session = _create_session(v1_client)
    session_id = session["id"]

    response = v1_client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": "谢谢"})

    assert response.status_code == 201
    payload = response.json()
    user_message = payload["user_message"]
    assistant_message = payload["assistant_message"]
    assert user_message["role"] == "user"
    assert user_message["content"] == "谢谢"
    assert user_message["run_id"] is None
    assert assistant_message["role"] == "assistant"
    assert assistant_message["run_id"] is None
    assert PLAIN_REPLY_PREFIX in assistant_message["content"]
    assert "未启动调查" in assistant_message["content"]

    messages = v1_client.get(f"/api/v1/sessions/{session_id}/messages").json()["items"]
    assert [item["role"] for item in messages] == ["user", "assistant"]
    assert all(item["run_id"] is None for item in messages)

    runs = v1_client.get(f"/api/v1/sessions/{session_id}/runs").json()["items"]
    assert runs == []


def test_调查意图消息返回409且不创建任何消息(v1_client: TestClient) -> None:
    """AC2 服务端判定面：调查意图不落库，由前端回退到 Run 主链路。"""
    session = _create_session(v1_client)
    session_id = session["id"]

    response = v1_client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": "排查慢查询"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "INVESTIGATION_REQUIRED"
    messages = v1_client.get(f"/api/v1/sessions/{session_id}/messages").json()["items"]
    assert messages == []


def test_助手回复内容为确定性模板且不含伪造结果(v1_client: TestClient) -> None:
    """AC3：普通回复明确说明未启动调查，不伪造调查结果。"""
    session = _create_session(v1_client)
    response = v1_client.post(f"/api/v1/sessions/{session['id']}/messages", json={"content": "好的，明白了"})
    assert response.status_code == 201
    content = response.json()["assistant_message"]["content"]
    assert content.startswith(PLAIN_REPLY_PREFIX)
    assert "未启动调查" in content
    assert "慢查询" in content or "连接池" in content or "索引" in content


def test_普通消息支持同一会话多轮(v1_client: TestClient) -> None:
    """多轮普通对话逐条落库并保持 user→assistant 顺序。"""
    session = _create_session(v1_client)
    session_id = session["id"]
    for text in ("你好", "谢谢"):
        response = v1_client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": text})
        assert response.status_code == 201
    messages = v1_client.get(f"/api/v1/sessions/{session_id}/messages").json()["items"]
    assert [item["content"] for item in messages if item["role"] == "user"] == ["你好", "谢谢"]
    assert [item["content"] for item in messages if item["role"] == "assistant"] == [
        PLAIN_REPLY_TEMPLATE,
        PLAIN_REPLY_TEMPLATE,
    ]


def test_会话不存在返回404(v1_client: TestClient) -> None:
    """不存在的会话返回 404，不创建任何消息。"""
    response = v1_client.post(f"/api/v1/sessions/{uuid4()}/messages", json={"content": "谢谢"})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "SESSION_NOT_FOUND"


def test_已归档会话返回409(v1_client: TestClient) -> None:
    """已归档会话不可发消息。"""
    session = _create_session(v1_client)
    session_id = session["id"]
    archived = v1_client.patch(f"/api/v1/sessions/{session_id}", json={"status": "archived"})
    assert archived.status_code == 200

    response = v1_client.post(f"/api/v1/sessions/{session_id}/messages", json={"content": "谢谢"})
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "SESSION_ARCHIVED"


def test_空内容返回422(v1_client: TestClient) -> None:
    """空白内容由字段校验拒绝。"""
    session = _create_session(v1_client)
    response = v1_client.post(f"/api/v1/sessions/{session['id']}/messages", json={"content": "   "})
    assert response.status_code == 422
