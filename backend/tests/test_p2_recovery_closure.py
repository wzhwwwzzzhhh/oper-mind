"""P2.5 刷新恢复与会话诊断闭环验收。"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from src.api.v1.dependencies import V1Services
from src.application.contracts import DiagnosisExecutionError, DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.models import (
    DiagnosisResultRecord,
    DiagnosisRunRecord,
    MessageRecord,
    RunEventRecord,
    SessionRecord,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _CountingExecutor:
    """只记录调用次数并输出确定性安全结果的执行器。"""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def stream(self, query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """输出一条受控路由事件和最终结果。"""
        self.queries.append(query)
        yield DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="route",
            occurred_at=datetime.now(UTC),
        )
        yield DiagnosisExecutionResult(strategy="direct")


class _UnsafeFailingExecutor:
    """模拟带有连接串、令牌和 SQL 的内部执行失败。"""

    def __init__(self) -> None:
        self.queries: list[str] = []

    def stream(self, query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        """抛出不得离开服务端边界的原始异常。"""
        self.queries.append(query)
        raise DiagnosisExecutionError(
            code="POSTGRES_CONNECTION_FAILED",
            message="postgresql://admin:token@db.example SELECT * FROM secrets",
        )
        yield DiagnosisExecutionResult()


@dataclass(frozen=True)
class _RecoveryApi:
    """绑定迁移临时库和确定性服务的 API 测试装配。"""

    app: FastAPI
    executor: _CountingExecutor | _UnsafeFailingExecutor
    runtime: PersistenceRuntime


def _upgrade_temporary_database(database_path: Path) -> None:
    """仅通过 Alembic 创建隔离的刷新验收数据库。"""
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


def _build_recovery_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    executor: _CountingExecutor | _UnsafeFailingExecutor,
) -> _RecoveryApi:
    """以已迁移临时库安装可跨 TestClient 使用的 v1 服务。"""
    database_path = tmp_path / "p2-recovery.sqlite3"
    _upgrade_temporary_database(database_path)
    database_url = f"sqlite:///{database_path.as_posix()}"
    runtime = create_persistence_runtime(database_url)
    services = V1Services(
        session_factory=runtime.session_factory,
        session_service=SessionApplicationService(runtime.session_factory),
        run_service=RunApplicationService(
            runtime.session_factory,
            executor,
            ConservativeResultAssembler(),
        ),
    )

    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", database_url)
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    return _RecoveryApi(app=api_module.app, executor=executor, runtime=runtime)


@pytest.fixture
def recovery_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[_RecoveryApi]:
    """提供成功执行路径的独立刷新恢复装配。"""
    harness = _build_recovery_api(monkeypatch, tmp_path, _CountingExecutor())
    try:
        yield harness
    finally:
        harness.runtime.engine.dispose()


@pytest.fixture
def failing_recovery_api(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[_RecoveryApi]:
    """提供执行失败路径的独立刷新恢复装配。"""
    harness = _build_recovery_api(monkeypatch, tmp_path, _UnsafeFailingExecutor())
    try:
        yield harness
    finally:
        harness.runtime.engine.dispose()


def _create_session(client: TestClient) -> str:
    """创建本测试的持久化会话并返回 ID。"""
    response = client.post("/api/v1/sessions", json={"title": "P2.5 刷新恢复"})
    assert response.status_code == 201
    return response.json()["session"]["id"]


def _create_run(client: TestClient, session_id: str, query: str) -> tuple[str, str]:
    """受理 Run，返回 Run ID 与稳定 trace ID。"""
    response = client.post(
        f"/api/v1/sessions/{session_id}/runs",
        headers={"Idempotency-Key": str(uuid4())},
        json={"query": query},
    )
    assert response.status_code == 202
    run = response.json()["run"]
    return run["id"], run["trace_id"]


def _persistence_snapshot(runtime: PersistenceRuntime, session_id: str) -> dict[str, object]:
    """读取当前持久化状态，用于证明恢复 GET/SSE 不产生写入。"""
    session_uuid = UUID(session_id)
    session = runtime.session_factory()
    try:
        record = session.get(SessionRecord, session_uuid)
        assert record is not None
        runs = list(
            session.scalars(
                select(DiagnosisRunRecord)
                .where(DiagnosisRunRecord.session_id == session_uuid)
                .order_by(DiagnosisRunRecord.created_at.asc(), DiagnosisRunRecord.id.asc())
            )
        )
        return {
            "session": (record.status, record.updated_at, record.archived_at),
            "runs": tuple(
                (
                    item.id,
                    item.status,
                    item.next_event_sequence,
                    item.error_code,
                    item.error_message,
                    item.started_at,
                    item.finished_at,
                )
                for item in runs
            ),
            "messages": session.scalar(
                select(func.count()).select_from(MessageRecord).where(MessageRecord.session_id == session_uuid)
            ),
            "events": tuple(
                (
                    item.id,
                    session.scalar(select(func.count()).select_from(RunEventRecord).where(RunEventRecord.run_id == item.id)),
                )
                for item in runs
            ),
            "results": tuple(
                (
                    item.id,
                    session.scalar(
                        select(func.count()).select_from(DiagnosisResultRecord).where(DiagnosisResultRecord.run_id == item.id)
                    ),
                )
                for item in runs
            ),
        }
    finally:
        session.close()


def _sse_frames(payload: str) -> list[dict[str, object]]:
    """解析完整持久化 SSE 重放内容。"""
    if not payload.strip():
        return []
    frames: list[dict[str, object]] = []
    for frame in payload.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        frames.append({"id": int(lines["id"]), "event": lines["event"], "data": json.loads(lines["data"])})
    return frames


def test_p2_refresh恢复成功Run消息结果事件与终态SSE(recovery_api: _RecoveryApi) -> None:
    """新请求上下文只能从持久化资源恢复成功 Run，绝不重复执行或写入。"""
    with TestClient(recovery_api.app, raise_server_exceptions=False) as initial_client:
        session_id = _create_session(initial_client)
        first_run_id, _ = _create_run(initial_client, session_id, "检查刷新恢复的第一条诊断")
        second_run_id, second_trace_id = _create_run(initial_client, session_id, "检查刷新恢复的第二条诊断")
        before_refresh = _persistence_snapshot(recovery_api.runtime, session_id)
        assert recovery_api.executor.queries == ["检查刷新恢复的第一条诊断", "检查刷新恢复的第二条诊断"]

    with TestClient(recovery_api.app, raise_server_exceptions=False) as refreshed_client:
        session = refreshed_client.get(f"/api/v1/sessions/{session_id}")
        assert session.status_code == 200
        assert session.json()["session"]["id"] == session_id

        first_page = refreshed_client.get(f"/api/v1/sessions/{session_id}/runs", params={"limit": 1})
        assert first_page.status_code == 200
        assert first_page.json()["page"]["has_more"] is True
        first_item = first_page.json()["items"][0]
        assert first_item["status"] == "succeeded"
        cursor = first_page.json()["page"]["next_cursor"]
        assert isinstance(cursor, str) and cursor

        second_page = refreshed_client.get(
            f"/api/v1/sessions/{session_id}/runs",
            params={"limit": 1, "cursor": cursor},
        )
        assert second_page.status_code == 200
        assert second_page.json()["page"]["has_more"] is False
        restored_ids = {first_item["id"], second_page.json()["items"][0]["id"]}
        assert restored_ids == {first_run_id, second_run_id}

        restored_run = refreshed_client.get(f"/api/v1/runs/{second_run_id}")
        assert restored_run.status_code == 200
        run = restored_run.json()["run"]
        assert run["status"] == "succeeded"
        assert run["trace_id"] == second_trace_id
        assert run["result"] is not None
        assert run["error"] is None

        messages = refreshed_client.get(f"/api/v1/sessions/{session_id}/messages")
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()["items"]] == ["user", "assistant", "user", "assistant"]
        assert {item["run_id"] for item in messages.json()["items"] if item["role"] == "assistant"} == {
            first_run_id,
            second_run_id,
        }

        events = refreshed_client.get(f"/api/v1/runs/{second_run_id}/events")
        assert events.status_code == 200
        event_items = events.json()["items"]
        assert event_items[-1]["type"] == "run_succeeded"
        assert events.json()["meta"]["trace_id"] == second_trace_id

        replay = refreshed_client.get(f"/api/v1/runs/{second_run_id}/stream")
        assert replay.status_code == 200
        frames = _sse_frames(replay.text)
        assert [frame["id"] for frame in frames] == [item["sequence"] for item in event_items]
        assert all(frame["data"]["meta"]["trace_id"] == second_trace_id for frame in frames)

        terminal_reconnect = refreshed_client.get(
            f"/api/v1/runs/{second_run_id}/stream",
            headers={"Last-Event-ID": str(event_items[-1]["sequence"])},
        )
        assert terminal_reconnect.status_code == 200
        assert terminal_reconnect.text == ""

        openapi = refreshed_client.get("/openapi.json")
        assert openapi.status_code == 200
        paths = openapi.json()["paths"]
        assert "get" in paths["/api/v1/sessions/{session_id}/runs"]
        assert "post" in paths["/api/v1/sessions/{session_id}/runs"]
        # 旧 /diagnose CoT 接口已移除，不应再出现在公开契约中。
        assert "/diagnose" not in paths
        assert "/diagnose/stream" not in paths
        schema = paths["/api/v1/sessions/{session_id}/runs"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert schema["$ref"].endswith("/DiagnosisRunListResponse")
        parameters = {parameter["name"] for parameter in paths["/api/v1/sessions/{session_id}/runs"]["get"]["parameters"]}
        assert {"session_id", "cursor", "limit"}.issubset(parameters)
        session_post_parameters = paths["/api/v1/sessions"]["post"].get("parameters", [])
        assert all(parameter["name"].lower() != "idempotency-key" for parameter in session_post_parameters)
        response_schema = openapi.json()["components"]["schemas"]["DiagnosisRunListResponse"]
        assert {"items", "page", "meta"}.issubset(response_schema["properties"])

    assert _persistence_snapshot(recovery_api.runtime, session_id) == before_refresh
    assert recovery_api.executor.queries == ["检查刷新恢复的第一条诊断", "检查刷新恢复的第二条诊断"]


def test_p2_refresh恢复失败Run仅暴露安全错误并关闭SSE(failing_recovery_api: _RecoveryApi) -> None:
    """失败 Run 跨刷新保留安全终态、事件和用户输入，不泄露内部异常。"""
    query = "模拟安全失败后的刷新恢复"
    with TestClient(failing_recovery_api.app, raise_server_exceptions=False) as initial_client:
        session_id = _create_session(initial_client)
        run_id, trace_id = _create_run(initial_client, session_id, query)
        before_refresh = _persistence_snapshot(failing_recovery_api.runtime, session_id)
        assert failing_recovery_api.executor.queries == [query]

    with TestClient(failing_recovery_api.app, raise_server_exceptions=False) as refreshed_client:
        listed = refreshed_client.get(f"/api/v1/sessions/{session_id}/runs")
        assert listed.status_code == 200
        listed_run = listed.json()["items"][0]
        assert listed_run["id"] == run_id
        assert listed_run["status"] == "failed"
        assert listed_run["error"] == {"code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}

        restored = refreshed_client.get(f"/api/v1/runs/{run_id}")
        assert restored.status_code == 200
        run = restored.json()["run"]
        assert run["trace_id"] == trace_id
        assert run["result"] is None
        assert run["error"] == listed_run["error"]

        messages = refreshed_client.get(f"/api/v1/sessions/{session_id}/messages")
        assert messages.status_code == 200
        assert [item["role"] for item in messages.json()["items"]] == ["user"]

        events = refreshed_client.get(f"/api/v1/runs/{run_id}/events")
        assert events.status_code == 200
        event_items = events.json()["items"]
        assert event_items[-1]["type"] == "run_failed"
        assert event_items[-1]["data"] == {"state": "failed", "code": "DIAGNOSIS_FAILED"}
        assert events.json()["meta"]["trace_id"] == trace_id

        replay = refreshed_client.get(f"/api/v1/runs/{run_id}/stream")
        assert replay.status_code == 200
        frames = _sse_frames(replay.text)
        assert frames[-1]["data"]["event"]["type"] == "run_failed"
        assert all(frame["data"]["meta"]["trace_id"] == trace_id for frame in frames)
        assert "postgresql://" not in replay.text
        assert "token@" not in replay.text
        assert "SELECT * FROM secrets" not in replay.text

        terminal_reconnect = refreshed_client.get(
            f"/api/v1/runs/{run_id}/stream",
            params={"after_sequence": event_items[-1]["sequence"]},
        )
        assert terminal_reconnect.status_code == 200
        assert terminal_reconnect.text == ""

    assert _persistence_snapshot(failing_recovery_api.runtime, session_id) == before_refresh
    assert failing_recovery_api.executor.queries == [query]
