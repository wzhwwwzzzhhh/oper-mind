"""P2.4 `/api/v1` 与持久化 SSE 重放测试。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.contracts import DiagnosisExecutionError, DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _DeterministicExecutor:
    """不访问真实 Agent、只输出一条安全事件的确定性执行器。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """输出固定的路由事件和完成结果。"""
        yield DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="route",
            occurred_at=datetime.now(timezone.utc),
        )
        yield DiagnosisExecutionResult(strategy="direct")

class _LeakingExecutor:
    """模拟携带内部连接串、SQL 和令牌的执行错误。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """抛出不允许持久化或返回的原始错误。"""
        raise DiagnosisExecutionError(
            code="POSTGRES_CONNECTION_FAILED",
            message="postgresql://admin:token@db.example SELECT * FROM secrets",
        )
        yield DiagnosisExecutionResult()


def _upgrade_temporary_database(database_path: Path) -> None:
    """只通过 Alembic 在临时 SQLite 文件创建 P2 schema。"""
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
    """以迁移后的临时 SQLite 和确定性执行器构建 v1 API 客户端。"""
    database_path = tmp_path / "p2-api.sqlite3"
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


def _create_session(client: TestClient, title: str = "P2.4 会话") -> dict[str, object]:
    """创建测试会话并断言 v1 元数据。"""
    response = client.post("/api/v1/sessions", json={"title": title})
    assert response.status_code == 201
    assert response.headers["X-Request-Id"] == response.json()["meta"]["request_id"]
    return response.json()["session"]


def _run_headers() -> dict[str, str]:
    """为每个测试请求生成独立 UUID 幂等键。"""
    return {"Idempotency-Key": str(uuid4())}


def _sse_frames(payload: str) -> list[dict[str, object]]:
    """解析本测试中的完整 SSE 重放文本。"""
    frames: list[dict[str, object]] = []
    for frame in payload.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        frames.append({"id": int(lines["id"]), "event": lines["event"], "data": json.loads(lines["data"])})
    return frames


def test_v1_session资源分页更新归档与UTCZ序列化(v1_client: TestClient) -> None:
    """Session 资源遵循 v1 meta、cursor、UTC Z 和逻辑归档契约。"""
    created = _create_session(v1_client, "  需要归档的会话  ")
    session_id = created["id"]

    assert created["title"] == "需要归档的会话"
    assert created["created_at"].endswith("Z")
    listed = v1_client.get("/api/v1/sessions", params={"limit": 1})
    assert listed.status_code == 200
    assert listed.json()["items"][0]["id"] == session_id
    assert listed.json()["page"]["has_more"] is False

    supplied_request_id = str(uuid4())
    echoed = v1_client.get("/api/v1/sessions", headers={"X-Request-Id": supplied_request_id})
    assert echoed.status_code == 200
    assert echoed.headers["X-Request-Id"] == supplied_request_id
    assert echoed.json()["meta"]["request_id"] == supplied_request_id

    second = _create_session(v1_client, "用于 cursor 的第二个会话")
    first_page = v1_client.get("/api/v1/sessions", params={"limit": 1})
    assert first_page.status_code == 200
    assert first_page.json()["page"]["has_more"] is True
    next_cursor = first_page.json()["page"]["next_cursor"]
    assert isinstance(next_cursor, str) and next_cursor
    second_page = v1_client.get("/api/v1/sessions", params={"limit": 1, "cursor": next_cursor})
    assert second_page.status_code == 200
    assert second_page.json()["items"][0]["id"] in {session_id, second["id"]}
    assert second_page.json()["items"][0]["id"] != first_page.json()["items"][0]["id"]

    updated = v1_client.patch(f"/api/v1/sessions/{session_id}", json={"title": "已改名"})
    assert updated.status_code == 200
    assert updated.json()["session"]["title"] == "已改名"

    no_op = v1_client.patch(f"/api/v1/sessions/{session_id}", json={"status": "active"})
    assert no_op.status_code == 200
    assert no_op.json()["session"]["updated_at"] == updated.json()["session"]["updated_at"]

    deleted = v1_client.delete(f"/api/v1/sessions/{session_id}")
    assert deleted.status_code == 204
    repeated = v1_client.delete(f"/api/v1/sessions/{session_id}")
    assert repeated.status_code == 204

    forbidden = v1_client.post(
        f"/api/v1/sessions/{session_id}/runs",
        headers=_run_headers(),
        json={"query": "归档后不可运行"},
    )
    assert forbidden.status_code == 409
    assert forbidden.json()["error"]["code"] == "SESSION_ARCHIVED"


def test_v1_run幂等后台执行事件和结构化结果(v1_client: TestClient) -> None:
    """Run 受理返回 queued，后台执行落盘，重试不创建第二个 Run。"""
    session = _create_session(v1_client)
    session_id = session["id"]
    headers = _run_headers()
    accepted = v1_client.post(
        f"/api/v1/sessions/{session_id}/runs",
        headers=headers,
        json={"query": "检查 API 的持久化诊断"},
    )
    assert accepted.status_code == 202
    body = accepted.json()
    run_id = body["run"]["id"]
    trace_id = body["run"]["trace_id"]
    assert body["run"]["status"] == "queued"
    assert body["meta"]["trace_id"] == trace_id
    assert accepted.headers["X-Trace-Id"] == trace_id

    replay = v1_client.post(
        f"/api/v1/sessions/{session_id}/runs",
        headers=headers,
        json={"query": "检查 API 的持久化诊断"},
    )
    assert replay.status_code == 202
    assert replay.json()["run"]["id"] == run_id

    conflict = v1_client.post(
        f"/api/v1/sessions/{session_id}/runs",
        headers=headers,
        json={"query": "不同诊断请求"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    completed = v1_client.get(f"/api/v1/runs/{run_id}")
    assert completed.status_code == 200
    run = completed.json()["run"]
    assert run["status"] == "succeeded"
    assert run["result"]["severity"] == "info"
    assert run["result"]["evidence"] == []
    assert run["error"] is None

    messages = v1_client.get(f"/api/v1/sessions/{session_id}/messages")
    assert messages.status_code == 200
    assert [item["role"] for item in messages.json()["items"]] == ["user", "assistant"]


def test_v1_events_sse重放续传与游标错误(v1_client: TestClient) -> None:
    """SSE event id 一一映射已提交 sequence，Last-Event-ID 可断线续传。"""
    session = _create_session(v1_client)
    accepted = v1_client.post(
        f"/api/v1/sessions/{session['id']}/runs",
        headers=_run_headers(),
        json={"query": "检查 SSE 重放"},
    )
    run_id = accepted.json()["run"]["id"]

    events = v1_client.get(f"/api/v1/runs/{run_id}/events")
    assert events.status_code == 200
    sequences = [item["sequence"] for item in events.json()["items"]]
    assert sequences == [1, 2, 3, 4]
    assert [item["type"] for item in events.json()["items"]] == [
        "run_queued", "run_started", "route_decided", "run_succeeded",
    ]

    stream = v1_client.get(f"/api/v1/runs/{run_id}/stream")
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    frames = _sse_frames(stream.text)
    assert [frame["id"] for frame in frames] == sequences
    assert all(frame["event"] == "run_event" for frame in frames)
    assert frames[-1]["data"]["event"]["type"] == "run_succeeded"

    resumed = v1_client.get(
        f"/api/v1/runs/{run_id}/stream",
        headers={"Last-Event-ID": "2"},
    )
    assert [frame["id"] for frame in _sse_frames(resumed.text)] == [3, 4]

    mismatched = v1_client.get(
        f"/api/v1/runs/{run_id}/stream",
        params={"after_sequence": "1"},
        headers={"Last-Event-ID": "2"},
    )
    assert mismatched.status_code == 400
    assert mismatched.json()["error"]["code"] == "INVALID_EVENT_CURSOR"

    invalid = v1_client.get(f"/api/v1/runs/{run_id}/stream", headers={"Last-Event-ID": "999"})
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "INVALID_EVENT_CURSOR"


def test_v1安全错误请求ID与旧接口契约隔离(v1_client: TestClient) -> None:
    """v1 错误始终带 meta，旧接口仍保持阶段一错误结构。"""
    invalid_request_id = v1_client.get("/api/v1/sessions", headers={"X-Request-Id": "not-a-uuid"})
    assert invalid_request_id.status_code == 400
    assert invalid_request_id.json()["error"]["code"] == "INVALID_REQUEST_ID"
    assert UUID(invalid_request_id.json()["meta"]["request_id"])

    invalid_payload = v1_client.post("/api/v1/sessions", json={"title": "  "})
    assert invalid_payload.status_code == 422
    assert invalid_payload.json()["error"]["code"] == "VALIDATION_ERROR"
    assert invalid_payload.json()["error"]["details"][0]["field"] == "title"

    missing = v1_client.get(f"/api/v1/runs/{uuid4()}")
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "RUN_NOT_FOUND"

    legacy = v1_client.get("/diagnose/stream")
    assert legacy.status_code == 422
    assert legacy.json()["code"] == "VALIDATION_ERROR"
    assert "meta" not in legacy.json()


def test_v1执行失败脱敏并以持久化终态事件关闭SSE(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """内部执行错误不得进入 Run、HTTP 或 SSE，认领后的失败必须可重放。"""
    database_path = tmp_path / "p2-api-failure.sqlite3"
    _upgrade_temporary_database(database_path)
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    services = V1Services(
        session_factory=runtime.session_factory,
        session_service=SessionApplicationService(runtime.session_factory),
        run_service=RunApplicationService(
            runtime.session_factory,
            _LeakingExecutor(),
            ConservativeResultAssembler(),
        ),
    )
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    try:
        with TestClient(api_module.app, raise_server_exceptions=False) as client:
            session = _create_session(client, "脱敏失败会话")
            accepted = client.post(
                f"/api/v1/sessions/{session['id']}/runs",
                headers=_run_headers(),
                json={"query": "触发内部错误"},
            )
            assert accepted.status_code == 202
            run_id = accepted.json()["run"]["id"]

            run_response = client.get(f"/api/v1/runs/{run_id}")
            assert run_response.status_code == 200
            run = run_response.json()["run"]
            assert run["status"] == "failed"
            assert run["error"] == {"code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}
            serialized_run = run_response.text
            assert "postgresql://" not in serialized_run
            assert "SELECT * FROM secrets" not in serialized_run
            assert "token" not in serialized_run

            stream = client.get(f"/api/v1/runs/{run_id}/stream")
            frames = _sse_frames(stream.text)
            assert frames[-1]["data"]["event"]["type"] == "run_failed"
            assert frames[-1]["data"]["event"]["data"] == {"state": "failed", "code": "DIAGNOSIS_FAILED"}
            assert "postgresql://" not in stream.text
            assert "SELECT * FROM secrets" not in stream.text
            assert "token" not in stream.text
    finally:
        runtime.engine.dispose()
