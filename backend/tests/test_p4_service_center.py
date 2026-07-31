"""P4.3 服务中心、静态会话入口与受控快照回归测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import build_v1_services_for_runtime
from src.domain.services import (
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceMode,
    ServiceSourceStatus,
)
from src.infrastructure.diagnosis.demo_orders.models import DatabaseEvidenceSnapshot, ServerEvidenceSnapshot
from src.infrastructure.diagnosis.demo_orders import service_connector
from src.infrastructure.diagnosis.demo_orders.service_connector import (
    PostgresOrdersSlowQueryConnector,
    _target_snapshot,
)
from src.infrastructure.diagnosis.demo_orders.settings import DemoOrdersEvidenceSettings, EvidenceMode
from src.infrastructure.persistence.database import create_persistence_runtime

from test_p4_action_proposals import _upgrade_temporary_database


@pytest.fixture
def p43_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """使用独立应用元数据与确定性 mock 靶场装配完整 P4.3 API。"""
    database_path = tmp_path / "p4-service-center.sqlite3"
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


def _create_service_run(client: TestClient) -> tuple[str, str]:
    """仅经服务入口创建会话，并由用户动作创建已有 P4.1 Run。"""
    created = client.post("/api/v1/services/order-service/sessions")
    assert created.status_code == 201
    session_id = created.json()["session"]["id"]
    accepted = client.post(
        f"/api/v1/sessions/{session_id}/runs",
        headers={"Idempotency-Key": str(uuid4())},
        json={"query": "订单服务变慢，帮我排查慢查询"},
    )
    assert accepted.status_code == 202
    return session_id, accepted.json()["run"]["id"]


def test_services_returns_only_safe_static_mock_snapshot(p43_client: TestClient) -> None:
    """服务列表和详情仅返回唯一静态服务及脱敏 mock 当前快照。"""
    listed = p43_client.get("/api/v1/services")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["items"]) == 1
    service = body["items"][0]
    assert service["id"] == "order-service"
    assert service["kind"] == "postgres_orders_demo"
    assert service["snapshot"]["mode"] == "mock"
    assert service["snapshot"]["availability"] == "healthy"
    assert service["snapshot"]["performance_signal"] == "slow_query_detected"
    assert service["snapshot"]["database"]["signal"] == "missing_index_seq_scan_detected"
    assert "127.0.0.1" not in str(service)
    assert "opermind_demo" not in str(service)
    assert "gongkar" not in str(service)
    assert "SELECT" not in str(service)

    detail = p43_client.get("/api/v1/services/order-service")
    assert detail.status_code == 200
    detail_service = detail.json()["service"]
    assert detail_service["id"] == service["id"]
    assert detail_service["snapshot"]["mode"] == service["snapshot"]["mode"]
    assert detail_service["snapshot"]["performance_signal"] == service["snapshot"]["performance_signal"]


def test_service_session_only_creates_bound_session_without_investigation(p43_client: TestClient) -> None:
    """服务入口只创建绑定 Session，尚未创建消息、Run、Proposal 或外部调查。"""
    response = p43_client.post("/api/v1/services/order-service/sessions")
    assert response.status_code == 201
    session = response.json()["session"]
    assert session["status"] == "active"
    assert session["service_id"] == "order-service"

    messages = p43_client.get(f"/api/v1/sessions/{session['id']}/messages")
    runs = p43_client.get(f"/api/v1/sessions/{session['id']}/runs")
    activities = p43_client.get("/api/v1/services/order-service/activities")
    assert messages.status_code == 200 and messages.json()["items"] == []
    assert runs.status_code == 200 and runs.json()["items"] == []
    assert activities.status_code == 200 and activities.json()["items"] == []

    forged = p43_client.post("/api/v1/sessions", json={"title": "伪造服务", "service_id": "order-service"})
    assert forged.status_code == 422
    assert forged.json()["error"]["code"] == "VALIDATION_ERROR"


def test_service_activity_reads_p41_p42_history_without_sensitive_payload(p43_client: TestClient) -> None:
    """活动摘要只关联 service_id 会话，展示 Run/Proposal/Verify 状态而不透传证据。"""
    unbound_session = p43_client.post("/api/v1/sessions", json={"title": "不应进入服务活动的历史会话"})
    assert unbound_session.status_code == 201
    unbound_run = p43_client.post(
        f"/api/v1/sessions/{unbound_session.json()['session']['id']}/runs",
        headers={"Idempotency-Key": str(uuid4())},
        json={"query": "订单服务变慢，帮我排查慢查询"},
    )
    assert unbound_run.status_code == 202

    session_id, run_id = _create_service_run(p43_client)
    proposal_response = p43_client.get(f"/api/v1/runs/{run_id}/action-proposal")
    assert proposal_response.status_code == 200
    proposal_id = proposal_response.json()["proposal"]["id"]

    approved = p43_client.post(
        f"/api/v1/action-proposals/{proposal_id}/approval",
        headers={"Idempotency-Key": str(uuid4())},
        json={"decision": "approve"},
    )
    assert approved.status_code == 200
    executed = p43_client.post(
        f"/api/v1/action-proposals/{proposal_id}/executions",
        headers={"Idempotency-Key": str(uuid4())},
        json={},
    )
    assert executed.status_code == 202

    activities = p43_client.get("/api/v1/services/order-service/activities")
    assert activities.status_code == 200
    body = activities.json()
    assert body["page"]["has_more"] is False
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["session_id"] == session_id
    assert item["run_id"] == run_id
    assert item["run_status"] == "succeeded"
    assert item["proposal_status"] == "verified"
    assert item["verification_status"] == "verified"
    assert "evidence" not in item
    assert "request_id" not in item
    assert "CREATE INDEX" not in str(item)


def test_unknown_service_is_rejected_without_dynamic_registration(p43_client: TestClient) -> None:
    """未知服务不创建会话、不读取活动，也不接受运行时连接配置。"""
    for path in (
        "/api/v1/services/not-registered",
        "/api/v1/services/not-registered/activities",
        "/api/v1/services/not-registered/sessions",
    ):
        response = p43_client.post(path) if path.endswith("/sessions") else p43_client.get(path)
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "SERVICE_NOT_FOUND"


def test_disabled_and_mock_snapshots_never_touch_target_readers(monkeypatch: pytest.MonkeyPatch) -> None:
    """disabled 与 mock 快照不执行任何 target 固定读取。"""

    def unexpected_reader(*_args: object) -> object:
        raise AssertionError("不应调用 target 读取器。")

    monkeypatch.setattr(service_connector, "_read_server_snapshot", unexpected_reader)
    monkeypatch.setattr(service_connector, "_read_database_snapshot", unexpected_reader)

    disabled = PostgresOrdersSlowQueryConnector(ServiceMode.DISABLED).health_snapshot()
    mock = PostgresOrdersSlowQueryConnector(ServiceMode.MOCK).health_snapshot()

    assert disabled.mode is ServiceMode.DISABLED
    assert disabled.availability is ServiceAvailability.NOT_CONFIGURED
    assert mock.mode is ServiceMode.MOCK
    assert mock.database.signal is DatabaseSignal.MISSING_INDEX_SEQ_SCAN_DETECTED


def test_target_reader_failure_stays_target_unavailable_without_mock_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """target 两来源不可用时只返回安全 unavailable，不回退为 mock。"""
    target_settings = DemoOrdersEvidenceSettings.model_construct(mode=EvidenceMode.TARGET)
    monkeypatch.setattr(service_connector, "_read_server_snapshot", lambda _settings: None)
    monkeypatch.setattr(service_connector, "_read_database_snapshot", lambda _settings: None)

    snapshot = PostgresOrdersSlowQueryConnector(ServiceMode.TARGET, target_settings).health_snapshot()

    assert snapshot.mode is ServiceMode.TARGET
    assert snapshot.availability is ServiceAvailability.UNAVAILABLE
    assert snapshot.performance_signal is PerformanceSignal.UNAVAILABLE
    assert snapshot.database.signal is DatabaseSignal.UNAVAILABLE


def test_target_snapshot_combines_only_current_fixed_facts() -> None:
    """target 信号组合遵守缺索引/顺序扫描与有限指标的固定规则。"""
    observed_at = datetime.now(timezone.utc)
    slow = _target_snapshot(
        ServerEvidenceSnapshot(
            observed_at=observed_at,
            service_healthy=True,
            window_size=5,
            p50_ms=20.0,
            p95_ms=220.0,
            slow_query_count=1,
            timeout_count=0,
        ),
        DatabaseEvidenceSnapshot(
            observed_at=observed_at,
            target_database_confirmed=True,
            target_index_exists=False,
            plan_uses_seq_scan=True,
            plan_uses_target_index=False,
        ),
    )
    assert slow.mode is ServiceMode.TARGET
    assert slow.availability is ServiceAvailability.HEALTHY
    assert slow.database.signal is DatabaseSignal.MISSING_INDEX_SEQ_SCAN_DETECTED
    assert slow.performance_signal is PerformanceSignal.SLOW_QUERY_DETECTED

    fixed = _target_snapshot(
        ServerEvidenceSnapshot(
            observed_at=observed_at,
            service_healthy=True,
            window_size=5,
            p50_ms=4.0,
            p95_ms=8.0,
            slow_query_count=0,
            timeout_count=0,
        ),
        DatabaseEvidenceSnapshot(
            observed_at=observed_at,
            target_database_confirmed=True,
            target_index_exists=True,
            plan_uses_seq_scan=False,
            plan_uses_target_index=True,
        ),
    )
    assert fixed.database.signal is DatabaseSignal.INDEX_AND_PLAN_CONFIRMED
    assert fixed.performance_signal is PerformanceSignal.NO_SLOW_QUERY_DETECTED

    unavailable = _target_snapshot(None, None)
    assert unavailable.server_metrics.source_status is ServiceSourceStatus.UNAVAILABLE
    assert unavailable.database.source_status is ServiceSourceStatus.UNAVAILABLE
    assert unavailable.availability is ServiceAvailability.UNAVAILABLE
    assert unavailable.performance_signal is PerformanceSignal.UNAVAILABLE
