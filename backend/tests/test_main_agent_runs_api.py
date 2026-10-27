"""V2 主 Agent 的公开 API 契约测试：请求／资源联合、交付投影与安全边界。"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from collections.abc import Callable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from src.api.v1.dependencies import V1Services
from src.api.v1.schemas import DiagnosisRunResource, MainAnswerDeliveryResource
from src.application.contracts import DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.application.services import RunApplicationService, SessionApplicationService
from src.application.session_export import SessionExportApplicationService
from src.capabilities import (
    CapabilityRegistry,
    SkillUnavailableError,
    SkillUnavailableReason,
)
from src.capabilities.playbook import (
    READONLY_PLAYBOOK_CAPABILITY,
    READONLY_PLAYBOOK_CAPABILITY_ID,
    READONLY_PLAYBOOK_SKILL_ID,
    READONLY_PLAYBOOK_SKILL_VERSION,
)
from src.capabilities.text_compare import TEXT_COMPARE_CAPABILITY
from src.core.llm import LLMClient
from src.core.main_agent_model import MainMockScenario
from src.domain.diagnosis import RunEventType
from src.infrastructure.agent_runtime.run_executor import MainAgentRunExecutor
from src.infrastructure.diagnosis.result_assembler import ConservativeResultAssembler
from src.infrastructure.persistence.database import PersistenceRuntime, create_persistence_runtime
from src.infrastructure.persistence.repositories import (
    SqlAlchemySessionExportStore,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"

MATERIAL_A = "alpha\nbeta"
MATERIAL_B = "alpha\ngamma"
SENTINEL = "不应回显的原文"
CREDENTIAL_TEXT = "密钥 " + "sk-" + "abcdefghijklmnopqrstuvwxyz0123456789"
_UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


class _DeterministicExecutor:
    """legacy 诊断执行器替身：只输出一条安全事件与固定结果。"""

    def stream(self, _query: str) -> Iterator[DiagnosisExecutionEvent | DiagnosisExecutionResult]:
        yield DiagnosisExecutionEvent(
            type=RunEventType.ROUTE_DECIDED,
            node="route",
            occurred_at=datetime.now(UTC),
        )
        yield DiagnosisExecutionResult(strategy="direct")


class _ScriptedClient:
    """真实决策路径替身：从提示词取回本 Run 材料 ID，返回固定 typed JSON。"""

    is_mock = False

    def __init__(self, kind: str) -> None:
        self.kind = kind
        self.calls = 0

    def chat(self, messages: list[dict[str, str]], tools: Any = None, **_kwargs: Any) -> dict[str, object]:
        self.calls += 1
        if self.kind == "answer":
            return {"content": json.dumps({"kind": "answer", "text": "这是一条普通回答，未执行文本比较。"})}
        if self.kind == "invalid":
            return {"content": "不是 JSON 的模型输出"}
        goal_prompt = messages[-1]["content"]
        material_ids = _UUID_PATTERN.findall(goal_prompt)
        if self.kind == "needs_input":
            slots = [
                slot
                for slot in ("text_a", "text_b")
                if f"- {slot}：未提供" in goal_prompt
            ]
            return {"content": json.dumps({"kind": "needs_input", "slots": slots})}
        if self.kind == "knowledge":
            if self.calls == 1:
                return {
                    "content": json.dumps(
                        {
                            "kind": "load_skill",
                            "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                            "capability_version": 1,
                        }
                    )
                }
            return {"content": json.dumps({"kind": "answer", "text": "按内置手册给出只读排查步骤。"})}
        if self.kind == "budget":
            return {
                "content": json.dumps(
                    {
                        "kind": "load_skill",
                        "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                        "capability_version": 1,
                    }
                )
            }
        if self.kind == "wrong_version":
            return {
                "content": json.dumps(
                    {
                        "kind": "load_skill",
                        "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                        "capability_version": 99,
                    }
                )
            }
        if len(material_ids) < 2:
            return {"content": json.dumps({"kind": "needs_input", "slots": ["text_b"]})}
        return {
            "content": json.dumps(
                {
                    "kind": "invoke_capability",
                    "capability_id": "text.literal_compare",
                    "capability_version": 1,
                    "inputs": {
                        "text_a": material_ids[0],
                        "text_b": material_ids[1],
                    },
                }
            )
        }


class _UnavailableSkillSource:
    """确定性降级来源：只返回封闭原因，不泄露路径或内容。"""

    def load(self, _declaration: object) -> object:
        raise SkillUnavailableError(SkillUnavailableReason.MISSING)


class _Harness:
    """一次装配的 API 客户端、会话身份与临时库位置。"""

    def __init__(
        self,
        client: TestClient,
        session_id: str,
        database_path: Path,
        runtime: PersistenceRuntime,
    ) -> None:
        self.client = client
        self.session_id = session_id
        self.database_path = database_path
        self.runtime = runtime


def _upgrade_temporary_database(database_path: Path) -> None:
    """只用 Alembic 在临时 SQLite 建立当前 schema。"""
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
        encoding="utf-8",
        errors="replace",
    )
    assert completed.returncode == 0, completed.stderr


def _headers() -> dict[str, str]:
    """每个请求使用独立 UUID 幂等键。"""
    return {"Idempotency-Key": str(uuid4())}


def _main_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "runtime_kind": "main_agent",
        "query": "比较这两份配置的差异",
        "text_a": MATERIAL_A,
        "text_b": MATERIAL_B,
    }
    payload.update(overrides)
    return payload


def _row_counts(database_path: Path) -> tuple[int, int]:
    """读取临时库 Run／消息计数，用于断言拒绝发生在任何写入之前。"""
    connection = sqlite3.connect(database_path)
    try:
        runs = connection.execute("SELECT COUNT(*) FROM diagnosis_runs").fetchone()[0]
        messages = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        return int(runs), int(messages)
    finally:
        connection.close()


@pytest.fixture
def harness(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[Callable[..., _Harness]]:
    """按场景装配 v1 API：mock 场景走封闭替身，scripted 走真实 JSON 决策路径。"""
    runtimes: list[PersistenceRuntime] = []

    def build(
        *,
        scenario: MainMockScenario | None = MainMockScenario.ANSWER,
        scripted: str | None = None,
        skill_source: object | None = None,
    ) -> _Harness:
        database_path = tmp_path / f"v2-api-{uuid4().hex}.sqlite3"
        _upgrade_temporary_database(database_path)
        runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
        runtimes.append(runtime)
        capabilities = CapabilityRegistry([TEXT_COMPARE_CAPABILITY, READONLY_PLAYBOOK_CAPABILITY])
        if scripted is not None:
            scripted_client = _ScriptedClient(scripted)

            def scripted_factory(_timeout: float) -> object:
                return scripted_client

            client_factory: Callable[[float], object] = scripted_factory
            executor_scenario: MainMockScenario | None = None
        else:

            def mock_client(_timeout: float) -> LLMClient:
                return LLMClient(
                    api_key="mock",
                    base_url="http://mock",
                    model="mock",
                    request_timeout=30.0,
                    max_retries=0,
                )

            client_factory = mock_client
            executor_scenario = scenario
        session_factory = runtime.session_factory
        executor_kwargs: dict[str, Any] = {}
        if skill_source is not None:
            executor_kwargs["skill_source"] = skill_source
        services = V1Services(
            session_factory=session_factory,
            session_service=SessionApplicationService(session_factory),
            run_service=RunApplicationService(
                session_factory,
                _DeterministicExecutor(),
                ConservativeResultAssembler(),
                capability_ids=capabilities.capability_ids(),
                capabilities=capabilities,
                run_executor=MainAgentRunExecutor(
                    client_factory=client_factory,
                    capabilities=capabilities,
                    mock_scenario=executor_scenario,
                    **executor_kwargs,
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
        session_id = client.post("/api/v1/sessions", json={"title": "V2 会话"}).json()["session"]["id"]
        return _Harness(client, session_id, database_path, runtime)

    yield build
    for runtime in runtimes:
        runtime.engine.dispose()


def test_legacy_request_keeps_diagnosis_kind_and_result(harness) -> None:
    """未提供 runtime_kind 时仍是诊断链路：kind=diagnosis，有结果、无交付。"""
    env = harness(scenario=None, scripted="answer")
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json={"query": "整体看一下服务状态"},
        headers=_headers(),
    )
    assert response.status_code == 202, response.text
    run_id = response.json()["run"]["id"]
    detail = env.client.get(f"/api/v1/runs/{run_id}").json()["run"]
    assert detail["runtime_kind"] == "diagnosis"
    assert detail["status"] == "succeeded"
    assert detail["result"] is not None
    assert detail["delivery"] is None
    assert detail["input_snapshot"] is None


def test_main_agent_answer_request_delivers_plain_answer(harness) -> None:
    """显式 main_agent 请求走 typed JSON 决策，交付普通回答且不产生诊断结果。"""
    env = harness(scripted="answer")
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(query="这两份配置有什么不同"),
        headers=_headers(),
    )
    assert response.status_code == 202
    run = env.client.get(f"/api/v1/runs/{response.json()['run']['id']}").json()["run"]
    assert run["runtime_kind"] == "main_agent"
    assert run["service_id"] is None
    assert run["result"] is None
    assert run["delivery"]["kind"] == "answer"
    assert run["delivery"]["text"] == "这是一条普通回答，未执行文本比较。"


def test_main_agent_comparison_delivery_uses_real_deterministic_tool(harness) -> None:
    """mock 模型 + 真实确定性 Tool：交付含精确行号与逐字引文。"""
    env = harness(scenario=MainMockScenario.COMPARE)
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    )
    run_id = response.json()["run"]["id"]
    run = env.client.get(f"/api/v1/runs/{run_id}").json()["run"]
    delivery = run["delivery"]
    assert delivery["kind"] == "comparison"
    assert delivery["status"] == "has_difference"
    assert delivery["capability_id"] == "text.literal_compare"
    assert delivery["rule_version"] == "literal-lines@1"
    assert [block["kind"] for block in delivery["blocks"]] == ["modified"]
    block = delivery["blocks"][0]
    assert (block["a_start"], block["a_end"], block["a_quote"]) == (2, 2, "beta")
    assert (block["b_start"], block["b_end"], block["b_quote"]) == (2, 2, "gamma")
    snapshot = run["input_snapshot"]
    assert snapshot["text_a"]["original_text"] == MATERIAL_A
    assert snapshot["text_b"]["original_text"] == MATERIAL_B
    assert snapshot["text_a"]["content_sha256"]
    assert delivery["a_material_id"] == snapshot["text_a"]["material_id"]
    assert delivery["b_material_id"] == snapshot["text_b"]["material_id"]


def test_main_agent_explicit_empty_materials_report_no_difference(harness) -> None:
    """AC5 公开链：双方显式为空是「提供了空文本」，应得无差异交付而非不可用或空结果。"""
    env = harness(scenario=MainMockScenario.COMPARE)
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(text_a="", text_b=""),
        headers=_headers(),
    )
    run = env.client.get(f"/api/v1/runs/{response.json()['run']['id']}").json()["run"]
    assert run["status"] == "succeeded"
    delivery = run["delivery"]
    assert delivery["kind"] == "comparison"
    assert delivery["status"] == "no_difference"
    assert delivery["blocks"] == []
    snapshot = run["input_snapshot"]
    assert (snapshot["text_a"]["original_text"], snapshot["text_b"]["original_text"]) == ("", "")
    assert snapshot["text_a"]["material_id"] != snapshot["text_b"]["material_id"]
    assert delivery["a_material_id"] == snapshot["text_a"]["material_id"]
    assert delivery["b_material_id"] == snapshot["text_b"]["material_id"]


def test_main_agent_missing_material_asks_for_input(harness) -> None:
    """只给 A 时追问缺失侧，不制造比较结果。"""
    env = harness(scenario=MainMockScenario.NEEDS_INPUT)
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(text_b=None),
        headers=_headers(),
    )
    run = env.client.get(f"/api/v1/runs/{response.json()['run']['id']}").json()["run"]
    assert run["status"] == "succeeded"
    assert run["delivery"]["kind"] == "needs_input"
    assert run["delivery"]["missing"] == ["text_b"]
    assert run["delivery"]["prompt"]
    assert run["input_snapshot"]["text_b"] is None


def test_main_agent_request_rejects_service_id_and_unknown_field(harness) -> None:
    """V2 请求不接受 service_id，未知字段失败关闭。"""
    env = harness(scenario=MainMockScenario.ANSWER)
    for extra in ({"service_id": "postgres-production"}, {"unexpected": 1}):
        response = env.client.post(
            f"/api/v1/sessions/{env.session_id}/runs",
            json={**_main_payload(), **extra},
            headers=_headers(),
        )
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_limit_error_does_not_echo_material_text(harness) -> None:
    """超限请求返回固定字段错误，响应体不含原文。"""
    env = harness(scenario=MainMockScenario.ANSWER)
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(query=SENTINEL + "x" * 400),
        headers=_headers(),
    )
    assert response.status_code == 422
    assert SENTINEL not in response.text
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"

    over_material = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(text_a=SENTINEL + "y" * 3000),
        headers=_headers(),
    )
    assert over_material.status_code == 422
    assert SENTINEL not in over_material.text
    # 材料上限在请求 schema 就拒绝：越限 body 不进入受理，零 Run／零消息写入。
    assert _row_counts(env.database_path) == (0, 0)


def test_sensitive_input_is_rejected_before_any_write(harness) -> None:
    """凭据形态输入在落库前拒绝，且零 Run／零消息写入。"""
    env = harness(scenario=MainMockScenario.ANSWER)
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(text_a=CREDENTIAL_TEXT),
        headers=_headers(),
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "MAIN_AGENT_INPUT_REJECTED"
    assert CREDENTIAL_TEXT not in response.text
    assert _row_counts(env.database_path) == (0, 0)


def test_events_sse_and_lists_do_not_carry_material_text(harness) -> None:
    """事件、SSE 与列表只含安全摘要，不回显材料正文或引文。"""
    env = harness(scenario=MainMockScenario.COMPARE)
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(query=SENTINEL),
        headers=_headers(),
    )
    run_id = response.json()["run"]["id"]
    events = env.client.get(f"/api/v1/runs/{run_id}/events").json()["items"]
    assert [event["type"] for event in events] == [
        "run_queued",
        "run_started",
        "agent_start",
        "route_decided",
        "tool_invoked",
        "agent_done",
        "run_succeeded",
    ]
    lifecycle = {"run_queued", "run_started", "run_succeeded"}
    assert all(event["data"].get("mode") == "mock" for event in events if event["type"] not in lifecycle)
    stream = env.client.get(f"/api/v1/runs/{run_id}/stream")
    assert stream.status_code == 200
    # 详情接口按契约返回本 Run 冻结输入；事件与 SSE 流不得回显问题或材料正文。
    for body in (stream.text, json.dumps(events, ensure_ascii=False)):
        assert SENTINEL not in body
        assert "beta" not in body and "gamma" not in body
    detail = env.client.get(f"/api/v1/runs/{run_id}").json()["run"]
    assert detail["input_snapshot"]["query"] == SENTINEL
    assert detail["delivery"]["kind"] == "comparison"
    # 会话摘要列表携带交付以恢复"本次结果"，但不携带冻结输入：Design §2.8 规定摘要
    # 列表不回显 A/B 原文，输入回看由前端按需读取 Run 详情（AC19 的恢复路径）。
    session_list_response = env.client.get(f"/api/v1/sessions/{env.session_id}/runs")
    assert SENTINEL not in session_list_response.text
    # 材料第 1 行只存在于冻结输入的 original_text；交付差异块只引 differing 行。
    assert "alpha" not in session_list_response.text
    session_list = session_list_response.json()["items"]
    assert all(item["input_snapshot"] is None for item in session_list)
    assert session_list[0]["delivery"]["kind"] == "comparison"
    assert "gamma" not in env.client.get("/api/v1/runs").text


def test_model_failure_is_reported_as_safe_unavailable(harness) -> None:
    """未声明 mock 场景时模型不可用，Run 收敛为固定安全失败且无交付。"""
    env = harness(scenario=None)
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    )
    run = env.client.get(f"/api/v1/runs/{response.json()['run']['id']}").json()["run"]
    assert run["status"] == "failed"
    assert run["error"]["code"] == "MAIN_AGENT_MODEL_UNAVAILABLE"
    assert run["delivery"] is None


def test_invalid_model_decision_is_reported_with_specific_code(harness) -> None:
    """模型返回非 JSON 决策时，公开失败码区分“决策无效”而不是笼统执行失败。"""
    env = harness(scripted="invalid")
    response = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    )
    run = env.client.get(f"/api/v1/runs/{response.json()['run']['id']}").json()["run"]
    assert run["status"] == "failed"
    assert run["error"]["code"] == "MAIN_AGENT_DECISION_INVALID"
    assert run["delivery"] is None


def test_corrupted_delivery_row_projects_safe_unavailable(harness) -> None:
    """损坏的交付行只把该 Run 标记为 unavailable，不让会话列表整体 500。"""
    env = harness(scenario=MainMockScenario.COMPARE)
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    assert env.client.get(f"/api/v1/runs/{run_id}").json()["run"]["status"] == "succeeded"

    connection = sqlite3.connect(env.database_path)
    try:
        connection.execute("UPDATE run_deliveries SET schema_version = 99")
        connection.commit()
    finally:
        connection.close()

    detail = env.client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()["run"]
    assert body["delivery"] is None
    assert body["main_delivery_status"] == "unavailable"

    listing = env.client.get(f"/api/v1/sessions/{env.session_id}/runs")
    assert listing.status_code == 200
    item = next(item for item in listing.json()["items"] if item["id"] == run_id)
    assert item["delivery"] is None
    assert item["main_delivery_status"] == "unavailable"


def test_corrupted_input_row_projects_safe_unavailable(harness) -> None:
    """损坏的冻结输入行只在详情标记 unavailable，不回显原文也不 500。"""
    env = harness(scenario=MainMockScenario.ANSWER)
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]

    connection = sqlite3.connect(env.database_path)
    try:
        connection.execute("UPDATE run_inputs SET schema_version = 99")
        connection.commit()
    finally:
        connection.close()

    detail = env.client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()["run"]
    assert body["input_snapshot"] is None
    assert body["main_input_status"] == "unavailable"

    listing = env.client.get(f"/api/v1/sessions/{env.session_id}/runs")
    assert listing.status_code == 200
    assert all(item["input_snapshot"] is None for item in listing.json()["items"])


def test_rerun_main_agent_run_copies_frozen_input(harness) -> None:
    """重跑沿用 main kind 与冻结输入，同键重放返回同一新 Run。"""
    env = harness(scenario=MainMockScenario.ANSWER)
    source_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    key = _headers()
    rerun = env.client.post(f"/api/v1/runs/{source_id}/rerun", headers=key)
    assert rerun.status_code == 202
    rerun_run = rerun.json()["run"]
    assert rerun_run["runtime_kind"] == "main_agent"
    assert rerun_run["rerun_of_run_id"] == source_id
    replay = env.client.post(f"/api/v1/runs/{source_id}/rerun", headers=key)
    assert replay.status_code == 202
    assert replay.json()["run"]["id"] == rerun_run["id"]
    detail = env.client.get(f"/api/v1/runs/{rerun_run['id']}").json()["run"]
    assert detail["input_snapshot"]["text_a"]["original_text"] == MATERIAL_A


def test_cancel_terminated_main_agent_run_returns_409(harness) -> None:
    """终态 V2 Run 的取消沿用既有 409 语义。"""
    env = harness(scenario=MainMockScenario.ANSWER)
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    assert env.client.get(f"/api/v1/runs/{run_id}").json()["run"]["status"] == "succeeded"
    assert env.client.post(f"/api/v1/runs/{run_id}/cancel").status_code == 409


def test_session_export_uses_neutral_main_run_summary(harness) -> None:
    """会话导出对 V2 Run 只给中性摘要，不含材料正文、差异引文或诊断字段。"""
    env = harness(scenario=MainMockScenario.COMPARE)
    env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(query="比较两份配置"),
        headers=_headers(),
    )
    export = env.client.get(f"/api/v1/sessions/{env.session_id}/export")
    assert export.status_code == 200, export.text
    body = export.text
    assert "主 Agent 对话" in body
    assert "比较两份配置" in body
    for leaked in ("alpha", "beta", "gamma", "严重度", "置信度", "结论"):
        assert leaked not in body


def test_session_export_uses_main_agent_safe_error_for_failed_run(harness) -> None:
    """导出错误行走白名单：V2 失败 Run 只输出主 Agent 安全文案，不得串成诊断文案或透传原始错误。"""
    env = harness(scenario=None)
    env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(query="比较两份配置"),
        headers=_headers(),
    )
    body = env.client.get(f"/api/v1/sessions/{env.session_id}/export").text
    assert "主 Agent 模型暂不可用，请稍后重试" in body
    assert "诊断执行失败" not in body


def test_run_resource_rejects_inconsistent_projection() -> None:
    """资源投影按 Design §2.8 拒绝不一致数据：非成功不得带结果／交付，非终态不得带安全错误。"""
    base: dict[str, Any] = {
        "created_at": datetime.now(UTC),
        "id": uuid4(),
        "input_message_id": uuid4(),
        "session_id": uuid4(),
        "trace_id": uuid4(),
    }
    result: dict[str, Any] = {
        "agent_summary": [],
        "confidence": 0.6,
        "created_at": datetime.now(UTC),
        "evidence": [],
        "id": uuid4(),
        "recommendations": [],
        "requires_approval": False,
        "risks": [],
        "root_causes": [],
        "run_id": uuid4(),
        "severity": "medium",
        "summary": "样例结果",
    }
    delivery: dict[str, Any] = {"kind": "answer", "text": "样例交付"}
    error: dict[str, Any] = {"code": "MAIN_AGENT_FAILED", "message": "主 Agent 执行失败，请稍后重试"}

    def run_payload(**overrides: Any) -> dict[str, Any]:
        return {**base, "delivery": None, "error": None, "result": None, "status": "succeeded", **overrides}

    # 非成功状态不得携带结果或交付（两种运行时一致）。
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(run_payload(runtime_kind="diagnosis", status="failed", result=result))
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(run_payload(runtime_kind="main_agent", status="failed", delivery=delivery))
    # 非终态不得携带安全错误（历史契约）。
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(run_payload(runtime_kind="main_agent", status="running", error=error))
    # Design §2.6：能力归属只属于终态，且明细必须与读取状态成对出现。
    capabilities: dict[str, Any] = {"used": [], "degraded": [], "steps": None}
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(
            run_payload(
                runtime_kind="main_agent",
                status="running",
                main_capabilities=capabilities,
                main_capabilities_status="available",
            )
        )
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(
            run_payload(runtime_kind="main_agent", delivery=delivery, main_capabilities=capabilities)
        )
    # 成功必须有对应运行时的事实，且两种结果互斥。
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(run_payload(runtime_kind="diagnosis"))
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(run_payload(runtime_kind="main_agent", result=result, delivery=delivery))
    # 诊断 Run 不得携带交付或冻结输入。
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate(
            run_payload(runtime_kind="diagnosis", delivery=delivery, result={**result, "run_id": base["id"]})
        )

    accepted = DiagnosisRunResource.model_validate(
        run_payload(
            runtime_kind="main_agent",
            delivery=delivery,
            input_snapshot={"query": "样例", "rule_version": "literal-lines@1"},
        )
    )
    assert accepted.delivery is not None and accepted.delivery.kind == "answer"


def test_main_agent_projects_capability_usage_and_steps(harness) -> None:
    """公开投影：能力归属与步数来自交付和事件，普通回答不冒充使用能力。"""
    compare_env = harness(scenario=MainMockScenario.COMPARE)
    compare_id = compare_env.client.post(
        f"/api/v1/sessions/{compare_env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    compare_run = compare_env.client.get(f"/api/v1/runs/{compare_id}").json()["run"]
    assert compare_run["main_capabilities_status"] == "available"
    assert compare_run["main_capabilities"] == {
        "used": [
            {
                "capability_id": "text.literal_compare",
                "capability_version": 1,
                "kind": "execution",
                "status": "ok",
            }
        ],
        "degraded": [],
        "steps": 1,
    }
    assert compare_run["main_knowledge"] is None
    assert compare_run["delivery"].get("knowledge_grounding") is None

    plain_env = harness(scripted="answer")
    plain_id = plain_env.client.post(
        f"/api/v1/sessions/{plain_env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    plain_run = plain_env.client.get(f"/api/v1/runs/{plain_id}").json()["run"]
    assert plain_run["main_capabilities_status"] == "absent"
    assert plain_run["main_capabilities"] is None
    assert plain_run["main_knowledge"] is None


def test_main_agent_knowledge_answer_projects_grounding_and_message_prefix(harness) -> None:
    """知识辅助回答只声明装入内置 Skill；助手消息带固定前缀，交付正文不伪装实时事实。"""
    env = harness(scripted="knowledge")
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    run = env.client.get(f"/api/v1/runs/{run_id}").json()["run"]
    assert run["status"] == "succeeded"
    assert run["delivery"]["kind"] == "answer"
    assert run["delivery"]["text"] == "按内置手册给出只读排查步骤。"
    expected_grounding = {
        "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
        "capability_version": 1,
        "skill_id": READONLY_PLAYBOOK_SKILL_ID,
        "skill_version": READONLY_PLAYBOOK_SKILL_VERSION,
        "data_access": "none",
        "note": "知识辅助回答 · 未读取实时数据",
    }
    assert run["delivery"]["knowledge_grounding"] == expected_grounding
    assert run["main_knowledge"] == expected_grounding
    assert run["main_capabilities_status"] == "available"
    assert run["main_capabilities"] == {
        "used": [
            {
                "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                "capability_version": 1,
                "kind": "knowledge",
                "status": "loaded",
            }
        ],
        "degraded": [],
        "steps": 2,
    }
    messages = env.client.get(f"/api/v1/sessions/{env.session_id}/messages").json()["items"]
    assistant = next(message for message in messages if message["role"] == "assistant")
    assert assistant["content"] == "知识辅助回答 · 未读取实时数据\n\n按内置手册给出只读排查步骤。"


def test_main_agent_degraded_knowledge_projects_unavailable_without_grounding(harness) -> None:
    """Skill 不可用时如实降级：Run 仍可回答，但不附加知识接地或知识前缀。"""
    env = harness(scripted="knowledge", skill_source=_UnavailableSkillSource())
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    run = env.client.get(f"/api/v1/runs/{run_id}").json()["run"]
    assert run["status"] == "succeeded"
    assert run["delivery"]["kind"] == "answer"
    assert run["delivery"]["knowledge_grounding"] is None
    assert run["main_knowledge"] is None
    assert run["main_capabilities_status"] == "available"
    assert run["main_capabilities"] == {
        "used": [],
        "degraded": [
            {
                "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
                "capability_version": 1,
                "kind": "knowledge",
                "status": "unavailable",
            }
        ],
        "steps": 2,
    }
    messages = env.client.get(f"/api/v1/sessions/{env.session_id}/messages").json()["items"]
    assistant = next(message for message in messages if message["role"] == "assistant")
    assert assistant["content"] == "按内置手册给出只读排查步骤。"


def test_main_agent_budget_exhaustion_is_safe_terminal_failure(harness) -> None:
    """预算耗尽使用专用安全失败码，不产交付，也不回显内部预算细节。"""
    env = harness(scenario=MainMockScenario.BUDGET_EXHAUSTED)
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    run = env.client.get(f"/api/v1/runs/{run_id}").json()["run"]
    assert run["status"] == "failed"
    assert run["error"] == {
        "code": "MAIN_AGENT_BUDGET_EXHAUSTED",
        "message": "本次主 Agent 运行预算已用尽，请拆分后再试",
    }
    assert run["delivery"] is None
    assert run["main_delivery_status"] == "absent"
    assert run["main_capabilities_status"] == "available"
    assert run["main_capabilities"]["steps"] is not None
    assert all(item["status"] in {"loaded", "ok"} for item in run["main_capabilities"]["used"])


def test_corrupted_capability_event_projects_safe_unavailable(harness) -> None:
    """损坏的决策事件只让能力归属不可用，不拖垮详情与列表。"""
    env = harness(scenario=MainMockScenario.COMPARE)
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]
    assert env.client.get(f"/api/v1/runs/{run_id}").json()["run"]["main_capabilities_status"] == "available"

    connection = sqlite3.connect(env.database_path)
    try:
        connection.execute(
            "UPDATE run_events SET data = ? WHERE type = 'route_decided'",
            (json.dumps({"node": "decide", "step": 99}),),
        )
        connection.commit()
    finally:
        connection.close()

    detail = env.client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    body = detail.json()["run"]
    assert body["main_capabilities_status"] == "unavailable"
    assert body["main_capabilities"] == {"used": [], "degraded": [], "steps": None}
    assert body["delivery"]["kind"] == "comparison"

    listing = env.client.get(f"/api/v1/sessions/{env.session_id}/runs")
    assert listing.status_code == 200
    item = next(item for item in listing.json()["items"] if item["id"] == run_id)
    assert item["main_capabilities_status"] == "unavailable"
    assert item["main_capabilities"] == {"used": [], "degraded": [], "steps": None}


@pytest.mark.parametrize(
    ("event_type", "payload"),
    [
        ("route_decided", {"decision": [], "step": 1}),
        ("route_decided", {"decision": "answer", "step": 1, "status": []}),
        (
            "route_decided",
            {
                "decision": "invoke_capability",
                "step": 1,
                "capability_id": "text.literal_compare",
                "capability_version": 1,
                "capability_kind": [],
                "status": "ok",
            },
        ),
        ("agent_done", {"steps": 1, "outcome": []}),
        ("agent_done", {"steps": 1, "outcome": {}}),
    ],
)
def test_non_scalar_capability_event_fields_fail_closed(harness, event_type: str, payload: dict[str, Any]) -> None:
    """事件 JSON 里的 list/dict 不得让能力投影抛 TypeError 变成 500。"""
    env = harness(scenario=MainMockScenario.COMPARE)
    run_id = env.client.post(
        f"/api/v1/sessions/{env.session_id}/runs",
        json=_main_payload(),
        headers=_headers(),
    ).json()["run"]["id"]

    connection = sqlite3.connect(env.database_path)
    try:
        connection.execute(
            "UPDATE run_events SET data = ? WHERE type = ?",
            (json.dumps(payload), event_type),
        )
        connection.commit()
    finally:
        connection.close()

    detail = env.client.get(f"/api/v1/runs/{run_id}")
    assert detail.status_code == 200
    assert detail.json()["run"]["main_capabilities_status"] == "unavailable"
    assert detail.json()["run"]["main_capabilities"] == {"used": [], "degraded": [], "steps": None}

    listing = env.client.get(f"/api/v1/sessions/{env.session_id}/runs")
    assert listing.status_code == 200
    item = next(item for item in listing.json()["items"] if item["id"] == run_id)
    assert item["main_capabilities_status"] == "unavailable"

    global_listing = env.client.get("/api/v1/runs")
    assert global_listing.status_code == 200
    global_item = next(item for item in global_listing.json()["items"] if item["id"] == run_id)
    assert global_item["main_capabilities_status"] == "unavailable"


def test_capability_projection_uses_one_batch_query_per_list_page(harness) -> None:
    """列表页能力归属按页批量读取：两个主 Agent Run 只发一条 run_events 查询。"""
    from sqlalchemy import event as sqlalchemy_event

    env = harness(scenario=MainMockScenario.COMPARE)
    for _ in range(2):
        response = env.client.post(
            f"/api/v1/sessions/{env.session_id}/runs",
            json=_main_payload(),
            headers=_headers(),
        )
        assert response.status_code == 202

    statements: list[str] = []

    def capture(_conn: object, _cursor: object, statement: str, *_args: object) -> None:
        statements.append(statement)

    sqlalchemy_event.listen(env.runtime.engine, "before_cursor_execute", capture)
    try:
        listing = env.client.get(f"/api/v1/sessions/{env.session_id}/runs")
    finally:
        sqlalchemy_event.remove(env.runtime.engine, "before_cursor_execute", capture)

    assert listing.status_code == 200
    assert len(listing.json()["items"]) == 2
    capability_queries = [statement for statement in statements if "FROM run_events" in statement]
    assert len(capability_queries) == 1


def test_openapi_exposes_capability_projection_without_catalog(harness) -> None:
    """公开字段只增能力归属与知识接地；不暴露能力目录或实现句柄。"""
    env = harness(scenario=MainMockScenario.ANSWER)
    schemas = env.client.get("/openapi.json").json()["components"]["schemas"]
    assert schemas["MainCapabilitiesResource"]["properties"].keys() == {"used", "degraded", "steps"}
    run_properties = schemas["DiagnosisRunResource"]["properties"]
    for name in ("main_capabilities", "main_capabilities_status", "main_knowledge"):
        assert name in run_properties
    assert "MainCapabilityCatalogResource" not in schemas
    assert "catalog" not in schemas["DiagnosisRunResource"]["properties"]


def test_run_resource_requires_knowledge_to_match_delivery() -> None:
    """公开资源拒绝「交付没有接地但字段声称有」或反向的不一致投影。"""
    grounding = {
        "capability_id": READONLY_PLAYBOOK_CAPABILITY_ID,
        "capability_version": 1,
        "skill_id": READONLY_PLAYBOOK_SKILL_ID,
        "skill_version": READONLY_PLAYBOOK_SKILL_VERSION,
        "data_access": "none",
        "note": "知识辅助回答 · 未读取实时数据",
    }
    base: dict[str, Any] = {
        "created_at": datetime.now(UTC),
        "id": uuid4(),
        "input_message_id": uuid4(),
        "session_id": uuid4(),
        "trace_id": uuid4(),
        "runtime_kind": "main_agent",
        "status": "succeeded",
        "result": None,
        "error": None,
    }
    grounded_delivery = {"kind": "answer", "text": "知识辅助回答", "knowledge_grounding": grounding}
    plain_delivery = {"kind": "answer", "text": "普通回答"}

    accepted = DiagnosisRunResource.model_validate(
        {**base, "delivery": grounded_delivery, "main_knowledge": grounding}
    )
    assert isinstance(accepted.delivery, MainAnswerDeliveryResource)
    assert accepted.main_knowledge is not None

    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate({**base, "delivery": grounded_delivery, "main_knowledge": None})
    with pytest.raises(ValidationError):
        DiagnosisRunResource.model_validate({**base, "delivery": plain_delivery, "main_knowledge": grounding})


def test_openapi_exposes_runtime_kind_and_delivery_components(harness) -> None:
    """公开 schema 暴露请求判别字段与交付资源组件，供前端类型生成使用。

    仓库既有 `ApiV1Model` 的 `field_serializer("*")` 返回 `object`，会让响应模型的
    字段类型在 OpenAPI 里退化为无类型（历史 `generated.ts` 里普遍是 `unknown`）。
    因此这里只断言判别字段与组件名存在，字段级类型仍由前端 reader 运行时收敛。
    """
    env = harness(scenario=MainMockScenario.ANSWER)
    spec = env.client.get("/openapi.json").json()
    schemas = spec["components"]["schemas"]
    main_request = schemas["CreateMainAgentRunRequest"]["properties"]
    assert main_request["runtime_kind"] == {"const": "main_agent", "title": "Runtime Kind", "type": "string"}
    assert schemas["CreateRunRequest"]["properties"]["runtime_kind"]["const"] == "diagnosis"
    for component in (
        "MainAnswerDeliveryResource",
        "MainNeedsInputDeliveryResource",
        "MainComparisonDeliveryResource",
        "MainInputSnapshotResource",
    ):
        assert component in schemas
