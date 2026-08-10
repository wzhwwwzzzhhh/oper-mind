"""P8 全局提案列表 `GET /action-proposals` 的安全摘要与分页测试。"""

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
from src.application.contracts import (
    CreateRunCommand,
    CreateSessionCommand,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
)
from src.application.services import RunApplicationService, SessionApplicationService
from src.domain.actions import ActionProposalData, ActionProposalStatus
from src.domain.diagnosis import RunEventType
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.action_repositories import SqlAlchemyActionProposalRepository
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

ACTION_ID = "postgres.orders_compound_index_rebuild.v1"


class _DeterministicExecutor:
    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        yield DiagnosisExecutionEvent(type=RunEventType.ROUTE_DECIDED, node="route")
        yield DiagnosisExecutionResult(strategy="direct")


@pytest.fixture
def persistence_runtime(tmp_path: Path) -> PersistenceRuntime:
    database_path = tmp_path / "proposal-list.sqlite3"
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


def _digest() -> str:
    return uuid4().hex * 2  # 64 字符


def _make_proposal(source_run_id: UUID, status: ActionProposalStatus, created_at: datetime) -> ActionProposalData:
    return ActionProposalData(
        source_run_id=source_run_id,
        action_id=ACTION_ID,
        action_digest=_digest(),
        status=status,
        mode="target",
        title="重建受控靶场联合索引",
        description="只对受控靶场固定目标执行代码内联合索引动作。",
        target={"service_id": "postgres-target", "table": "orders"},
        root_cause_id=uuid4(),
        evidence_ids=[uuid4(), uuid4(), uuid4()],
        risk_summary="受控靶场结构变更。",
        verification_plan=["确认目标表存在"],
        created_at=created_at,
        updated_at=created_at,
    )


def _insert(runtime: PersistenceRuntime, proposal: ActionProposalData) -> None:
    session = runtime.session_factory()
    try:
        SqlAlchemyActionProposalRepository(session).add(proposal)
        session.commit()
    finally:
        session.close()


def _create_run(runtime: PersistenceRuntime) -> UUID:
    """创建真实 Run 作为提案的 source_run_id（满足外键约束）。"""
    session_service = SessionApplicationService(runtime.session_factory)
    run_service = RunApplicationService(
        runtime.session_factory,
        _DeterministicExecutor(),
        ConservativeResultAssembler(),
    )
    session_data = session_service.create_session(CreateSessionCommand(title="提案来源会话"))
    from src.application.contracts import CreateRunCommand

    accepted = run_service.accept_run(
        CreateRunCommand(session_id=session_data.id, query="检查服务状态", idempotency_key=uuid4())
    )
    return accepted.run.id


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


def test_提案列表返回安全摘要且不含证据原文(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC7/AC9：列表返回白名单摘要字段，不含证据原文或未脱敏明细。"""
    proposal = _make_proposal(_create_run(persistence_runtime), ActionProposalStatus.PENDING_APPROVAL, datetime.now(UTC))
    _insert(persistence_runtime, proposal)

    response = v1_client.get("/api/v1/action-proposals")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert set(item.keys()) == {
        "id", "source_run_id", "action_id", "status", "mode", "title", "created_at", "updated_at",
    }
    assert item["id"] == str(proposal.id)
    assert item["status"] == "pending_approval"
    assert item["action_id"] == ACTION_ID
    for forbidden in ("description", "target", "evidence_ids", "risk_summary", "verification_plan", "action_digest", "root_cause_id"):
        assert forbidden not in item


def test_提案列表状态过滤只返回匹配项(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """AC8：按状态过滤只返回匹配状态的提案。"""
    now = datetime.now(UTC)
    pending = _make_proposal(_create_run(persistence_runtime), ActionProposalStatus.PENDING_APPROVAL, now - timedelta(minutes=2))
    approved = _make_proposal(_create_run(persistence_runtime), ActionProposalStatus.APPROVED, now - timedelta(minutes=1))
    _insert(persistence_runtime, pending)
    _insert(persistence_runtime, approved)

    response = v1_client.get("/api/v1/action-proposals", params={"status": "pending_approval"})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["id"] == str(pending.id)
    assert items[0]["status"] == "pending_approval"


def test_提案列表按创建时间倒序分页(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """cursor 分页：按创建时间倒序，下一页只含更早的提案。"""
    now = datetime.now(UTC)
    first = _make_proposal(_create_run(persistence_runtime), ActionProposalStatus.PENDING_APPROVAL, now)
    second = _make_proposal(_create_run(persistence_runtime), ActionProposalStatus.PENDING_APPROVAL, now - timedelta(minutes=1))
    third = _make_proposal(_create_run(persistence_runtime), ActionProposalStatus.PENDING_APPROVAL, now - timedelta(minutes=2))
    for proposal in (first, second, third):
        _insert(persistence_runtime, proposal)

    page_one = v1_client.get("/api/v1/action-proposals", params={"limit": 2})
    assert page_one.status_code == 200
    body_one = page_one.json()
    assert [item["id"] for item in body_one["items"]] == [str(first.id), str(second.id)]
    assert body_one["page"]["has_more"] is True
    assert body_one["page"]["next_cursor"] is not None

    page_two = v1_client.get(
        "/api/v1/action-proposals",
        params={"limit": 2, "cursor": body_one["page"]["next_cursor"]},
    )
    assert page_two.status_code == 200
    body_two = page_two.json()
    assert [item["id"] for item in body_two["items"]] == [str(third.id)]
    assert body_two["page"]["has_more"] is False
    assert body_two["page"]["next_cursor"] is None


def test_空列表返回诚实空态(persistence_runtime: PersistenceRuntime, v1_client: TestClient) -> None:
    """无提案时返回空列表与 has_more=false，不伪造。"""
    response = v1_client.get("/api/v1/action-proposals")
    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["page"]["has_more"] is False


def test_非法状态过滤返回422(v1_client: TestClient) -> None:
    """非法状态值由参数校验拒绝。"""
    response = v1_client.get("/api/v1/action-proposals", params={"status": "not_a_status"})
    assert response.status_code == 422


def test_非法游标返回400(v1_client: TestClient) -> None:
    """非法 cursor 由解码层拒绝。"""
    response = v1_client.get("/api/v1/action-proposals", params={"cursor": "not-a-cursor"})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CURSOR"
