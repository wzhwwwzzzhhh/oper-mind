"""P4.1 订单慢查询只读证据调查的单元与 API 回归测试。"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import build_v1_services_for_runtime
from src.api.v1.resources import result_resource
from src.application.contracts import DiagnosisExecutionError, DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.domain.diagnosis import DiagnosisSeverity, RunEventType
from src.domain.records import DiagnosisRunData
from src.infrastructure.diagnosis.demo_orders.collectors import CollectorOutcome, SnapshotCollector, build_evidence_investigation_result
from src.infrastructure.diagnosis.demo_orders.executor import DemoOrdersInvestigationExecutor, is_demo_orders_slow_query
from src.infrastructure.diagnosis.demo_orders.log_reader import OrderServiceLogReader
from src.infrastructure.diagnosis.demo_orders.models import DatabaseEvidenceSnapshot, LogEvidenceSnapshot, ServerEvidenceSnapshot
from src.infrastructure.diagnosis.demo_orders.postgres_reader import DemoOrdersSourceError, PostgresEvidenceReader
from src.infrastructure.diagnosis.demo_orders.result_assembler import DemoOrdersEvidenceResultAssembler
from src.infrastructure.diagnosis.demo_orders.service_reader import OrderServiceEvidenceReader
from src.infrastructure.diagnosis.demo_orders.settings import (
    DemoOrdersConfigurationError,
    DemoOrdersEvidenceSettings,
    EvidenceMode,
    load_demo_orders_evidence_settings,
)
from src.infrastructure.persistence.database import create_persistence_runtime


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"


class _FakeDatabaseClient:
    """固定返回缺失索引和顺序扫描的脱敏数据库 fake。"""

    def current_database(self) -> str:
        """返回受控靶场库名。"""
        return "opermind_demo"

    def target_index_exists(self) -> bool:
        """模拟目标索引缺失。"""
        return False

    def explain_orders_query(self) -> object:
        """模拟固定查询的顺序扫描计划。"""
        return [{"Plan": {"Node Type": "Seq Scan", "Relation Name": "orders"}}]


class _FakeServiceClient:
    """固定健康和聚合指标，不产生额外请求。"""

    def health(self) -> dict[str, object]:
        """返回订单服务健康状态。"""
        return {"status": "ok", "service": "order-service"}

    def metrics(self) -> dict[str, object]:
        """返回已聚合的受控延迟事实。"""
        return {
            "window_size": 8,
            "p50_ms": 62.0,
            "p95_ms": 180.0,
            "slow_query_count": 6,
            "timeout_count": 0,
            "slow_query_threshold_ms": 100.0,
        }


def _upgrade_temporary_database(database_path: Path) -> None:
    """仅通过 Alembic 为 API 集成测试建立独立应用元数据库。"""
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


def _snapshot_time() -> datetime:
    """提供统一 UTC 时间，保持测试快照显式。"""
    return datetime(2026, 7, 30, tzinfo=timezone.utc)


def _database_snapshot() -> DatabaseEvidenceSnapshot:
    """构造满足唯一根因规则的数据库快照。"""
    return DatabaseEvidenceSnapshot(
        observed_at=_snapshot_time(),
        target_database_confirmed=True,
        target_index_exists=False,
        plan_uses_seq_scan=True,
        plan_uses_target_index=False,
    )


def _logs_snapshot() -> LogEvidenceSnapshot:
    """构造支持慢查询异常的日志快照。"""
    return LogEvidenceSnapshot(
        observed_at=_snapshot_time(),
        matched_query_count=8,
        slow_query_count=6,
        timeout_count=0,
    )


def _server_snapshot() -> ServerEvidenceSnapshot:
    """构造支持慢查询异常的服务快照。"""
    return ServerEvidenceSnapshot(
        observed_at=_snapshot_time(),
        service_healthy=True,
        window_size=8,
        p50_ms=62.0,
        p95_ms=180.0,
        slow_query_count=6,
        timeout_count=0,
        slow_query_threshold_ms=100.0,
    )


def _outcome(role: str, snapshot: object | None) -> CollectorOutcome[object]:
    """构造零耗时角色采集终态。"""
    return CollectorOutcome(role=role, snapshot=snapshot, duration_ms=0)


def test_受控配置拒绝越界目标和应用库复用(tmp_path: Path) -> None:
    """P4.1 永远不将环境变量变成任意数据库、服务或文件读取。"""
    assert load_demo_orders_evidence_settings({}).mode is EvidenceMode.DISABLED
    assert load_demo_orders_evidence_settings({"OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": "mock"}).mode is EvidenceMode.MOCK

    for environment in (
        {"OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": "target", "OPERMIND_DEMO_PG_DATABASE": "gongkar"},
        {"OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": "target", "OPERMIND_DEMO_PG_HOST": "db.example"},
        {"OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": "target", "OPERMIND_DEMO_ORDERS_SERVICE_URL": "https://db.example"},
        {"OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": "target", "OPERMIND_DEMO_ORDERS_LOG_FILE": str(tmp_path / "other.jsonl")},
    ):
        with pytest.raises(DemoOrdersConfigurationError):
            load_demo_orders_evidence_settings(environment)

    with pytest.raises(DemoOrdersConfigurationError):
        load_demo_orders_evidence_settings(
            {
                "OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": "target",
                "OPERMIND_DEMO_PG_USER": "demo_user",
                "OPERMIND_DEMO_PG_PASSWORD": "not-logged",
            },
            app_database_url="postgresql+psycopg://demo_user:not-logged@127.0.0.1:5433/opermind_demo",
        )

    with pytest.raises(DemoOrdersConfigurationError):
        load_demo_orders_evidence_settings(
            {
                "OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": "target",
                "OPERMIND_DEMO_PG_USER": "demo_user",
                "OPERMIND_DEMO_PG_PASSWORD": "not-logged",
            },
            app_database_url="postgresql+psycopg://demo_user:not-logged@localhost:5433/opermind_demo",
        )


def test_三个reader只输出脱敏标量快照(tmp_path: Path) -> None:
    """fake 数据库/服务和临时日志均不能把原始内容带入快照。"""
    database = PostgresEvidenceReader(_FakeDatabaseClient()).collect()
    service = OrderServiceEvidenceReader(_FakeServiceClient()).collect()

    log_path = tmp_path / "order-service.jsonl"
    log_path.write_text(
        "\n".join(
            (
                '{"event":"order_query","route":"/orders/diagnostic-probe","slow_query":true,"timeout":false,"token":"must-not-leak"}',
                '{"event":"other","route":"/other","slow_query":true}',
                "not-json",
            )
        ),
        encoding="utf-8",
    )
    reader = OrderServiceLogReader(
        DemoOrdersEvidenceSettings(mode=EvidenceMode.MOCK),
        line_reader=lambda _path, _limit: log_path.read_text(encoding="utf-8").splitlines(),
    )
    logs = reader.collect()

    assert database.target_index_exists is False
    assert database.plan_uses_seq_scan is True
    assert service.p95_ms == 180.0
    assert logs.matched_query_count == 1
    assert logs.slow_query_count == 1
    assert logs.timeout_count == 0
    assert "must-not-leak" not in logs.model_dump_json()


def test_根因规则覆盖完整与部分证据() -> None:
    """只有 DB 条件满足且有支持源时才生成唯一允许的缺失索引结论。"""
    complete = build_evidence_investigation_result(
        _outcome("db", _database_snapshot()),
        _outcome("log", _logs_snapshot()),
        _outcome("server", _server_snapshot()),
    )
    assert complete.severity is DiagnosisSeverity.HIGH
    assert complete.confidence == 0.95
    assert len(complete.root_causes) == 1
    assert {fact.source_type for fact in complete.evidence} == {"database", "log", "metric"}

    partial = build_evidence_investigation_result(
        _outcome("db", _database_snapshot()),
        _outcome("log", None),
        _outcome("server", None),
    )
    assert partial.confidence == 0.70
    assert len(partial.root_causes) == 1
    assert partial.agent_summary[1].status == "failed"

    no_database_match = build_evidence_investigation_result(
        _outcome("db", _database_snapshot().model_copy(update={"target_index_exists": True})),
        _outcome("log", _logs_snapshot()),
        _outcome("server", _server_snapshot()),
    )
    assert no_database_match.root_causes == []
    assert no_database_match.confidence == 0.0

    with pytest.raises(DemoOrdersSourceError):
        build_evidence_investigation_result(_outcome("db", None), _outcome("log", None), _outcome("server", None))


def test_mock_executor事件不泄露原始读取且可通过公开结果schema() -> None:
    """mock 模式将并行角色过程和已校验结构化结果接入既有 P2 契约。"""
    executor = DemoOrdersInvestigationExecutor.from_settings(DemoOrdersEvidenceSettings(mode=EvidenceMode.MOCK))
    items = list(executor.stream("订单服务变慢，帮我排查慢查询"))
    events = [item for item in items if isinstance(item, DiagnosisExecutionEvent)]
    result = next(item for item in items if isinstance(item, DiagnosisExecutionResult))

    assert [event.type for event in events] == [
        RunEventType.ROUTE_DECIDED,
        RunEventType.AGENT_START,
        RunEventType.AGENT_START,
        RunEventType.AGENT_START,
        RunEventType.AGENT_DONE,
        RunEventType.AGENT_DONE,
        RunEventType.AGENT_DONE,
    ]
    assert all("SELECT" not in str(event.data) for event in events)
    assert result.evidence_investigation is not None
    assembled = DemoOrdersEvidenceResultAssembler().assemble(
        run=DiagnosisRunData(session_id=uuid4(), input_message_id=uuid4()),
        result=result,
    )
    resource = result_resource(assembled)
    assert resource.recommendations == []
    assert resource.requires_approval is False
    assert resource.agent_summary[0].agent == "db"


def test_意图路由不把普通问题伪装为订单调查() -> None:
    """首版严格限制到明确订单慢查询语义。"""
    assert is_demo_orders_slow_query("订单服务变慢，帮我排查慢查询") is True
    assert is_demo_orders_slow_query("订单服务有问题") is False
    assert is_demo_orders_slow_query("支付服务慢查询") is False


def test_api_mock模式产出证据结果和可重放事件(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """复用公开 API/Run/SSE 资源，不新增 endpoint 或迁移。"""
    database_path = tmp_path / "p4-api.sqlite3"
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
        session_response = client.post("/api/v1/sessions", json={"title": "P4.1 订单慢查询"})
        session_id = session_response.json()["session"]["id"]
        accepted = client.post(
            f"/api/v1/sessions/{session_id}/runs",
            headers={"Idempotency-Key": str(uuid4())},
            json={"query": "订单服务变慢，帮我排查慢查询"},
        )
        assert accepted.status_code == 202
        run_id = accepted.json()["run"]["id"]
        run_response = client.get(f"/api/v1/runs/{run_id}")
        assert run_response.status_code == 200
        run = run_response.json()["run"]
        assert run["status"] == "succeeded"
        assert run["result"]["severity"] == "high"
        assert run["result"]["confidence"] == 0.95
        assert len(run["result"]["root_causes"]) == 1
        assert {item["source_type"] for item in run["result"]["evidence"]} == {"database", "log", "metric"}
        assert run["result"]["recommendations"] == []
        assert run["result"]["requires_approval"] is False

        events_response = client.get(f"/api/v1/runs/{run_id}/events")
        event_items = events_response.json()["items"]
        assert [event["type"] for event in event_items] == [
            "run_queued", "run_started", "route_decided", "agent_start", "agent_start", "agent_start",
            "agent_done", "agent_done", "agent_done", "run_succeeded",
        ]
        assert event_items[2]["data"]["summary"] == "已识别订单慢查询场景，开始并行收集只读证据。"
        assert all("SELECT" not in str(event["data"]) for event in event_items)



def test_api_mock模式对不支持问题明确返回MVP范围(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """P4.1 开启后，非订单慢查询问题不得回退成旧 Agent 实验式回答。"""
    database_path = tmp_path / "p4-api-unsupported.sqlite3"
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
        session_id = client.post("/api/v1/sessions", json={"title": "P4.1 范围"}).json()["session"]["id"]
        accepted = client.post(
            f"/api/v1/sessions/{session_id}/runs",
            headers={"Idempotency-Key": str(uuid4())},
            json={"query": "支付服务 5xx 怎么排查？"},
        )
        run = client.get(f"/api/v1/runs/{accepted.json()['run']['id']}").json()["run"]
        assert run["status"] == "succeeded"
        assert run["result"]["severity"] == "info"
        assert run["result"]["evidence"] == []
        assert "只支持订单慢查询" in run["result"]["summary"]


def test_target配置缺失时订单调查安全失败(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """target 模式未满足严格配置时，禁止回退到其他库或伪造调查结果。"""
    database_path = tmp_path / "p4-api-invalid-target.sqlite3"
    _upgrade_temporary_database(database_path)
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("OPERMIND_DEMO_ORDERS_EVIDENCE_MODE", "target")
    monkeypatch.delenv("OPERMIND_DEMO_PG_USER", raising=False)
    monkeypatch.delenv("OPERMIND_DEMO_PG_PASSWORD", raising=False)
    services = build_v1_services_for_runtime(
        runtime,
        object(),
        app_database_url=f"sqlite:///{database_path.as_posix()}",
    )
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        session_id = client.post("/api/v1/sessions", json={"title": "P4.1 target 配置"}).json()["session"]["id"]
        accepted = client.post(
            f"/api/v1/sessions/{session_id}/runs",
            headers={"Idempotency-Key": str(uuid4())},
            json={"query": "订单服务变慢，帮我排查慢查询"},
        )
        run = client.get(f"/api/v1/runs/{accepted.json()['run']['id']}").json()["run"]
        assert run["status"] == "failed"
        assert run["error"] == {"code": "DIAGNOSIS_FAILED", "message": "诊断执行失败，请稍后重试"}
