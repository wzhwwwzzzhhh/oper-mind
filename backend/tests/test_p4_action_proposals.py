"""P4.2 固定 Proposal、审批、执行与 Verify 的 API 回归测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import build_v1_services_for_runtime
from src.domain.actions import build_orders_index_repair_proposal
from src.infrastructure.diagnosis.demo_orders.action_executor import (
    ActionPreconditionBlockedError,
    PostgresOrdersIndexRepairExecutor,
    ProbeResult,
)
from src.infrastructure.diagnosis.demo_orders.result_assembler import DemoOrdersEvidenceResultAssembler
from src.infrastructure.diagnosis.demo_orders.executor import DemoOrdersInvestigationExecutor
from src.infrastructure.diagnosis.demo_orders.settings import DemoOrdersEvidenceSettings, EvidenceMode
from src.infrastructure.persistence.action_repositories import SqlAlchemyActionProposalRepository
from src.infrastructure.persistence.models import ActionProposalRecord
from src.infrastructure.persistence.database import create_persistence_runtime


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


def _upgrade_temporary_database(database_path: Path) -> None:
    """只经 Alembic 创建独立应用元数据 schema。"""
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
def p4_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """提供启用确定性 mock 靶场的完整 P4.2 API 客户端。"""
    database_path = tmp_path / "p4-actions.sqlite3"
    _upgrade_temporary_database(database_path)
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    services = build_v1_services_for_runtime(
        runtime,
        object(),
        demo_orders_settings=DemoOrdersEvidenceSettings(mode=EvidenceMode.MOCK),
        app_database_url=f"sqlite:///{database_path.as_posix()}",
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


def _create_confirmed_proposal(client: TestClient) -> tuple[str, dict[str, object]]:
    """运行 P4.1 mock 调查并读取自动生成的 P4.2 Proposal。"""
    session = client.post("/api/v1/sessions", json={"title": "P4.2 订单慢查询"})
    assert session.status_code == 201
    session_id = session.json()["session"]["id"]
    accepted = client.post(
        f"/api/v1/sessions/{session_id}/runs",
        headers={"Idempotency-Key": str(uuid4())},
        json={"query": "订单服务变慢，帮我排查慢查询"},
    )
    assert accepted.status_code == 202
    run = client.get(f"/api/v1/runs/{accepted.json()['run']['id']}")
    assert run.status_code == 200
    result = run.json()["run"]["result"]
    assert result["severity"] == "high"
    assert result["confidence"] == 0.95
    assert result["requires_approval"] is True
    proposal_response = client.get(f"/api/v1/runs/{accepted.json()['run']['id']}/action-proposal")
    assert proposal_response.status_code == 200
    proposal = proposal_response.json()["proposal"]
    assert proposal is not None
    assert proposal["status"] == "pending_approval"
    assert proposal["mode"] == "mock"
    return proposal["id"], proposal


def test_mock_proposal_approval_execute_verify_and_event_timeline(p4_client: TestClient) -> None:
    """完整 mock 闭环明确标记模拟，且不公开 SQL、请求 ID 或原始日志。"""
    proposal_id, proposal = _create_confirmed_proposal(p4_client)
    assert proposal["action_id"] == "postgres.orders.rebuild_missing_user_created_index.v1"
    assert proposal["target"] == {"service": "order-service", "scope": "订单慢查询受控靶场"}
    assert "CREATE INDEX" not in str(proposal)

    approval_key = str(uuid4())
    approved = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/approval",
        headers={"Idempotency-Key": approval_key},
        json={"decision": "approve"},
    )
    assert approved.status_code == 200
    approved_body = approved.json()["proposal"]
    assert approved_body["status"] == "approved"
    assert approved_body["approval"]["actor"] == "local_operator"
    assert approved_body["approval"]["decision"] == "approve"

    replay = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/approval",
        headers={"Idempotency-Key": approval_key},
        json={"decision": "approve"},
    )
    assert replay.status_code == 200
    conflict = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/approval",
        headers={"Idempotency-Key": approval_key},
        json={"decision": "reject", "comment": "不执行"},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_KEY_REUSED"

    execute = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/executions",
        headers={"Idempotency-Key": str(uuid4())},
        json={},
    )
    assert execute.status_code == 202
    assert execute.json()["execution"]["mode"] == "mock"

    final = p4_client.get(f"/api/v1/action-proposals/{proposal_id}")
    assert final.status_code == 200
    final_proposal = final.json()["proposal"]
    assert final_proposal["status"] == "verified"
    assert final_proposal["execution"]["status"] == "succeeded"
    assert final_proposal["verification"]["mode"] == "mock"
    assert final_proposal["verification"]["facts"]["probe_count"] == 3
    assert final_proposal["verification"]["facts"]["matched_log_count"] == 3
    assert "request_id" not in str(final_proposal)

    events = p4_client.get(f"/api/v1/action-proposals/{proposal_id}/events")
    assert events.status_code == 200
    items = events.json()["items"]
    assert [item["sequence"] for item in items] == list(range(1, len(items) + 1))
    assert [item["type"] for item in items] == [
        "proposal_created",
        "approval_recorded",
        "execution_requested",
        "execution_started",
        "precondition_checked",
        "execution_completed",
        "verification_started",
        "verification_completed",
    ]
    assert "CREATE INDEX" not in str(items)


def test_rejected_proposal_cannot_create_execution(p4_client: TestClient) -> None:
    """拒绝是终态，后续执行声明必须被状态机拒绝且不触发 mock executor。"""
    proposal_id, _ = _create_confirmed_proposal(p4_client)
    rejected = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/approval",
        headers={"Idempotency-Key": str(uuid4())},
        json={"decision": "reject", "comment": "暂不处理"},
    )
    assert rejected.status_code == 200
    assert rejected.json()["proposal"]["status"] == "rejected"
    execution = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/executions",
        headers={"Idempotency-Key": str(uuid4())},
        json={},
    )
    assert execution.status_code == 409
    assert execution.json()["error"]["code"] == "ACTION_PROPOSAL_INVALID_STATE"
    detail = p4_client.get(f"/api/v1/action-proposals/{proposal_id}")
    assert detail.json()["proposal"]["execution"] is None


def test_only_strict_confirmed_result_can_create_fixed_proposal() -> None:
    """0.70 线索和被篡改的 Recommendation 都不能反向生成 Proposal。"""
    investigation = next(
        item
        for item in DemoOrdersInvestigationExecutor.from_settings(
            DemoOrdersEvidenceSettings(mode=EvidenceMode.MOCK)
        ).stream("订单服务变慢，帮我排查慢查询")
        if hasattr(item, "evidence_investigation")
    )
    from src.application.contracts import DiagnosisExecutionResult
    from src.domain.records import DiagnosisRunData

    assert isinstance(investigation, DiagnosisExecutionResult)
    result = DemoOrdersEvidenceResultAssembler().assemble(
        DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4()), investigation
    )
    assert build_orders_index_repair_proposal(result, "mock") is not None
    weak_result = result.model_copy(update={"confidence": 0.70})
    assert build_orders_index_repair_proposal(weak_result, "mock") is None
    forged_recommendation = weak_result.model_copy(
        update={
            "recommendations": result.recommendations,
            "requires_approval": True,
        }
    )
    assert build_orders_index_repair_proposal(forged_recommendation, "mock") is None


def test_target_precondition_block_stops_before_connection_or_ddl(monkeypatch: pytest.MonkeyPatch) -> None:
    """target 前置条件失败时执行器必须在 DDL 连接前返回 blocked。"""
    proposal_id, _ = _build_target_proposal()
    executor = PostgresOrdersIndexRepairExecutor(
        DemoOrdersEvidenceSettings(
            mode=EvidenceMode.TARGET,
            database_user="target_user",
            database_password="target_password",
        )
    )

    def blocked() -> None:
        raise ActionPreconditionBlockedError()

    def forbidden_connection():
        raise AssertionError("前置条件失败后不得建立 DDL 连接")

    monkeypatch.setattr(executor, "_assert_preconditions", blocked)
    monkeypatch.setattr(executor, "_connection", forbidden_connection)
    with pytest.raises(ActionPreconditionBlockedError):
        executor.execute(proposal_id)
    tampered = proposal_id.model_copy(update={"action_digest": "0" * 64})
    with pytest.raises(ActionPreconditionBlockedError):
        executor.execute(tampered)


def test_target_verify_exactly_three_fixed_probes_without_persisting_request_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """独立 Verify 恰好请求三次固定探测，且公开 outcome 只保留聚合标量。"""
    proposal, _ = _build_target_proposal()
    executor = PostgresOrdersIndexRepairExecutor(
        DemoOrdersEvidenceSettings(
            mode=EvidenceMode.TARGET,
            database_user="target_user",
            database_password="target_password",
        )
    )
    probe_calls: list[int] = []

    def probe() -> ProbeResult:
        probe_calls.append(1)
        return ProbeResult(request_id=f"internal-{len(probe_calls)}", slow_query=False, timeout=False)

    monkeypatch.setattr(executor, "_read_post_repair_database_facts", lambda: (True, True))
    monkeypatch.setattr(executor, "_request_probe", probe)
    monkeypatch.setattr(
        "src.infrastructure.diagnosis.demo_orders.action_executor._matching_log_facts",
        lambda _path, _limit, request_ids: {
            "matched_log_count": len(request_ids),
            "matched_log_slow_query_count": 0,
            "matched_log_timeout_count": 0,
        },
    )
    outcome = executor.verify(proposal)
    assert len(probe_calls) == 3
    assert outcome.facts["probe_count"] == 3
    assert "internal-1" not in str(outcome)


def test_expired_approval_is_persisted_as_terminal_before_execution(p4_client: TestClient) -> None:
    """执行声明时才判定 15 分钟过期，并且不会创建 execution 记录。"""
    proposal_id, _ = _create_confirmed_proposal(p4_client)
    approved = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/approval",
        headers={"Idempotency-Key": str(uuid4())},
        json={"decision": "approve"},
    )
    assert approved.status_code == 200
    from src import app as api_module

    session = api_module.app.state.v1_services.session_factory()
    try:
        proposal = SqlAlchemyActionProposalRepository(session).get_by_id(UUID(proposal_id))
        assert proposal is not None and proposal.approved_at is not None
        proposal_record = session.get(ActionProposalRecord, proposal.id)
        assert proposal_record is not None
        proposal_record.expires_at = proposal.approved_at - timedelta(seconds=1)
        session.commit()
    finally:
        session.close()
    execution = p4_client.post(
        f"/api/v1/action-proposals/{proposal_id}/executions",
        headers={"Idempotency-Key": str(uuid4())},
        json={},
    )
    assert execution.status_code == 409
    assert execution.json()["error"]["code"] == "ACTION_PROPOSAL_EXPIRED"
    detail = p4_client.get(f"/api/v1/action-proposals/{proposal_id}").json()["proposal"]
    assert detail["status"] == "expired"
    assert detail["execution"] is None


def _build_target_proposal():
    """构造满足严格 P4.1 事实的 target Proposal，完全不连接靶场。"""
    from src.application.contracts import DiagnosisExecutionResult
    from src.domain.records import DiagnosisRunData

    investigation = next(
        item
        for item in DemoOrdersInvestigationExecutor.from_settings(
            DemoOrdersEvidenceSettings(mode=EvidenceMode.MOCK)
        ).stream("订单服务变慢，帮我排查慢查询")
        if isinstance(item, DiagnosisExecutionResult)
    )
    result = DemoOrdersEvidenceResultAssembler().assemble(
        DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4()), investigation
    )
    proposal = build_orders_index_repair_proposal(result, "target")
    assert proposal is not None
    return proposal, result
