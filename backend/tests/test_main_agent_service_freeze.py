"""V2-2 WP1：受理期冻结服务引用。

覆盖：两级校验、快照冻结、条件序列化、指纹兼容、重跑保留、公开资源投影。
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.run_execution import (
    main_agent_create_fingerprint,
    main_agent_rerun_fingerprint,
)
from src.application.services import RunApplicationService, SessionApplicationService
from src.application.session_export import SessionExportApplicationService
from src.capabilities import CapabilityRegistry
from src.capabilities.playbook import READONLY_PLAYBOOK_CAPABILITY
from src.capabilities.text_compare import TEXT_COMPARE_CAPABILITY
from src.core.llm import LLMClient
from src.core.main_agent_model import MainMockScenario
from src.domain.main_agent import MainInputSnapshotV1, MainInputV1
from src.domain.services import (
    SERVICE_HEALTH_PRESSURE_INTENT_ID,
    BindingOrigin,
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceDatabaseStateData,
    ServiceDefinitionData,
    ServiceInvestigationData,
    ServiceMode,
    ServiceRegistry,
    ServiceServerMetricsData,
    ServiceSnapshotData,
    ServiceSourceStatus,
)
from src.infrastructure.agent_runtime.run_executor import MainAgentRunExecutor
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import SqlAlchemySessionExportStore

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

SERVICE_ID = "pg.readonly.test"
SERVICE_TITLE = "只读测试库"
MATERIAL_A = "alpha\nbeta"
MATERIAL_B = "alpha\ngamma"


def _snapshot() -> ServiceSnapshotData:
    return ServiceSnapshotData(
        observed_at=datetime.now(UTC),
        mode=ServiceMode.MOCK,
        availability=ServiceAvailability.HEALTHY,
        performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
        server_metrics=ServiceServerMetricsData(source_status=ServiceSourceStatus.AVAILABLE),
        database=ServiceDatabaseStateData(
            source_status=ServiceSourceStatus.AVAILABLE,
            signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
        ),
    )


class _FakePostgresCapability:
    """只读 capability 替身：kind 可切换；任何真实连接调用都直接失败。"""

    def __init__(self, kind: str = "postgres") -> None:
        self._kind = kind

    def capability_kind(self) -> str:
        return self._kind

    def agent_health_snapshot(self) -> ServiceSnapshotData:
        return _snapshot()

    def explain_select(self, sql: str) -> str:
        raise AssertionError("受理期不得执行 SQL")

    def show_indexes(self, table: str) -> str:
        raise AssertionError(table)

    def show_create_table(self, table: str) -> str:
        raise AssertionError(table)

    def check_locks(self) -> str:
        raise AssertionError("受理期不得打开连接")


class _FakePostgresConnector:
    """已注册服务替身；has_dsn/kind 可切换以覆盖拒绝分支。"""

    def __init__(self, *, has_dsn: bool = True, kind: str = "postgres") -> None:
        self._has_dsn = has_dsn
        self._kind = kind
        self._capability = _FakePostgresCapability(kind)

    def definition(self) -> ServiceDefinitionData:
        investigations = [
            ServiceInvestigationData(
                id=SERVICE_HEALTH_PRESSURE_INTENT_ID,
                title="健康调查",
                description="固定健康调查",
                default_query="检查健康状态",
            )
        ]
        if self._kind == "postgres":
            investigations.append(
                ServiceInvestigationData(
                    id="postgres_slow_query.v1",
                    title="慢查询",
                    description="固定只读调查",
                    default_query="检查慢查询",
                )
            )
        return ServiceDefinitionData(
            id=SERVICE_ID,
            title=SERVICE_TITLE,
            kind=self._kind,
            supported_investigations=tuple(investigations),
            action_boundary="只读",
            session_title="健康调查",
            has_dsn=self._has_dsn,
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        return _snapshot()

    def agent_capability(self) -> object:
        return self._capability

    def binding_origin(self) -> BindingOrigin:
        return BindingOrigin.from_reference(f"registry:{SERVICE_ID}")


class _NeverExecutor:
    """legacy 诊断执行器替身：本文件不跑 legacy 链路。"""

    def stream(self, query: str, service_id: str | None = None) -> Iterator[object]:
        raise AssertionError("不应执行 legacy 诊断")


class _Harness:
    def __init__(self, client: TestClient, session_id: str, database_path: Path) -> None:
        self.client = client
        self.session_id = session_id
        self.database_path = database_path


def _headers() -> dict[str, str]:
    return {"Idempotency-Key": str(uuid4())}


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "runtime_kind": "main_agent",
        "query": "比较这两份配置的差异",
        "text_a": MATERIAL_A,
        "text_b": MATERIAL_B,
    }
    payload.update(overrides)
    return payload


def _upgrade(database_path: Path) -> None:
    env = dict(os.environ)
    env["OPERMIND_APP_DATABASE_URL"] = f"sqlite:///{database_path.as_posix()}"
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=BACKEND_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


@pytest.fixture()
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Callable[..., _Harness]]:
    """按需装配带 registry 的 v1 API；registry 可缺省以覆盖 fail-closed 分支。"""

    runtimes: list[PersistenceRuntime] = []

    def build(*, registry: ServiceRegistry | None = None) -> _Harness:
        database_path = tmp_path / f"v2-freeze-{uuid4().hex}.sqlite3"
        _upgrade(database_path)
        runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
        runtimes.append(runtime)
        capabilities = CapabilityRegistry([TEXT_COMPARE_CAPABILITY, READONLY_PLAYBOOK_CAPABILITY])

        def mock_client(_timeout: float) -> LLMClient:
            return LLMClient(
                api_key="mock",
                base_url="http://mock",
                model="mock",
                request_timeout=30.0,
                max_retries=0,
            )

        session_factory = runtime.session_factory
        services = V1Services(
            session_factory=session_factory,
            session_service=SessionApplicationService(session_factory),
            run_service=RunApplicationService(
                session_factory,
                _NeverExecutor(),
                ConservativeResultAssembler(),
                registry=registry,
                capability_ids=capabilities.capability_ids(),
                capabilities=capabilities,
                run_executor=MainAgentRunExecutor(
                    client_factory=mock_client,
                    capabilities=capabilities,
                    mock_scenario=MainMockScenario.ANSWER,
                ),
            ),
            session_export_service=SessionExportApplicationService(
                lambda: SqlAlchemySessionExportStore(session_factory())
            ),
        )
        monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")
        monkeypatch.setenv("OPERMIND_API_KEY", "mock")
        monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
        monkeypatch.setenv("OPERMIND_MODEL", "mock")

        from src import app as api_module

        monkeypatch.setattr(api_module.app.state, "v1_services", services)
        client = TestClient(api_module.app, raise_server_exceptions=False)
        session_id = client.post("/api/v1/sessions", json={"title": "V2 冻结会话"}).json()["session"]["id"]
        return _Harness(client, session_id, database_path)

    yield build
    for runtime in runtimes:
        runtime.engine.dispose()


def _run_input_payload(database_path: Path) -> dict[str, Any]:
    with sqlite3.connect(database_path) as connection:
        rows = connection.execute("SELECT payload FROM run_inputs").fetchall()
    assert len(rows) == 1
    return json.loads(rows[0][0])


def test_service_is_frozen_into_snapshot_and_run(harness) -> None:
    """选了已注册服务：快照与 run.service_id 同时冻结，公开资源可读。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(),)))
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id=SERVICE_ID),
        headers=_headers(),
    )
    assert response.status_code == 202
    run_id = response.json()["run"]["id"]

    detail = env.client.get(f"/api/v1/runs/{run_id}").json()["run"]
    assert detail["service_id"] == SERVICE_ID
    assert detail["input_snapshot"]["service"] == {
        "service_id": SERVICE_ID,
        "kind": "postgres",
        "title": SERVICE_TITLE,
    }


def test_unknown_service_is_rejected_with_409(harness) -> None:
    """未注册服务：409，且不回显服务标识。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(),)))
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id="pg.not.registered"),
        headers=_headers(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MAIN_AGENT_SERVICE_UNAVAILABLE"
    assert "pg.not.registered" not in json.dumps(response.json())


def test_service_without_dsn_is_rejected_with_409(harness) -> None:
    """已注册但无凭据：409。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(has_dsn=False),)))
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id=SERVICE_ID),
        headers=_headers(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MAIN_AGENT_SERVICE_UNAVAILABLE"


def test_non_postgres_service_is_rejected_with_409(harness) -> None:
    """类型不是 postgres：409。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(kind="redis"),)))
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id=SERVICE_ID),
        headers=_headers(),
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "MAIN_AGENT_SERVICE_UNAVAILABLE"


def test_malformed_service_id_is_rejected_with_422(harness) -> None:
    """非法格式：422，与「服务不可用」分开。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(),)))
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id="Bad Service ID!"),
        headers=_headers(),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_registry_absent_fails_closed(harness) -> None:
    """registry 未注入：带 service_id 一律拒绝，不带则行为不变。"""
    env = harness(registry=None)
    rejected = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id=SERVICE_ID),
        headers=_headers(),
    )
    assert rejected.status_code == 409
    accepted = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(),
        headers=_headers(),
    )
    assert accepted.status_code == 202


def test_snapshot_without_service_omits_key(harness) -> None:
    """条件序列化：无服务快照写入后 payload 不含 service 键。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(),)))
    env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(),
        headers=_headers(),
    )
    payload = _run_input_payload(env.database_path)
    assert "service" not in payload


def test_snapshot_with_service_persists_key(harness) -> None:
    """条件序列化：带服务快照写入后 payload 含 service 键。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(),)))
    env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id=SERVICE_ID),
        headers=_headers(),
    )
    payload = _run_input_payload(env.database_path)
    assert payload["service"]["service_id"] == SERVICE_ID


def test_create_fingerprint_unchanged_without_service() -> None:
    """无服务请求的创建指纹必须与 V2-1 逐字节一致（不新增键）。"""
    legacy_payload = {
        "tag": "main-agent-create@1",
        "runtime_kind": "main_agent",
        "schema_version": 1,
        "query": "比较这两份配置的差异",
        "text_a": MATERIAL_A,
        "text_b": MATERIAL_B,
    }
    serialized = json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected = sha256(serialized.encode("utf-8")).hexdigest()
    value = MainInputV1(query="比较这两份配置的差异", text_a=MATERIAL_A, text_b=MATERIAL_B)
    assert main_agent_create_fingerprint(value) == expected


def test_rerun_fingerprint_unchanged_without_service() -> None:
    """无服务快照的重跑指纹不含 service_id 键。"""
    snapshot = MainInputSnapshotV1(
        schema_version=1,
        query="比较这两份配置的差异",
        rule_version="literal-lines@1",
    )
    source_id = uuid4()
    legacy_payload = {
        "tag": "main-agent-rerun@1",
        "runtime_kind": "main_agent",
        "source_run_id": str(source_id),
        "schema_version": 1,
        "rule_version": "literal-lines@1",
        "query": "比较这两份配置的差异",
        "text_a": None,
        "text_b": None,
        "context": [],
    }
    serialized = json.dumps(legacy_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    expected = sha256(serialized.encode("utf-8")).hexdigest()
    assert main_agent_rerun_fingerprint(source_id, snapshot) == expected


def test_rerun_keeps_service_and_legacy_rerun_stays_none(harness) -> None:
    """重跑保留 service_id；无服务的 Run 重跑仍为 None（不 500）。"""
    env = harness(registry=ServiceRegistry((_FakePostgresConnector(),)))
    with_service = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(service_id=SERVICE_ID),
        headers=_headers(),
    ).json()["run"]["id"]
    rerun = env.client.post(f"/api/v1/runs/{with_service}/rerun", headers=_headers())
    assert rerun.status_code == 202
    assert rerun.json()["run"]["service_id"] == SERVICE_ID

    without_service = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    legacy_rerun = env.client.post(f"/api/v1/runs/{without_service}/rerun", headers=_headers())
    assert legacy_rerun.status_code == 202
    assert legacy_rerun.json()["run"]["service_id"] is None
