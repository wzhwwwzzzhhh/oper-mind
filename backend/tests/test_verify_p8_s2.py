"""Issue #100 S2 真实链路复核器的离线安全测试。"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest

from scripts import verify_p8_s2 as verifier


def test_复核器只接受授权的本地端口与非空目标身份() -> None:
    verifier.validate_boundary("postgresql://demo-user@localhost:5433/demo-db")
    verifier.validate_boundary("postgresql+psycopg://demo-user@127.0.0.1:5433/demo-db")

    invalid = {
        "postgresql://demo-user@example.com:5433/demo-db": "TARGET_HOST_MISMATCH",
        "postgresql://demo-user@localhost:5432/demo-db": "TARGET_PORT_MISMATCH",
        "postgresql://localhost:5433/demo-db": "TARGET_USERNAME_MISSING",
        "postgresql://demo-user@localhost:5433": "TARGET_DATABASE_MISSING",
        "postgresql://demo-user@localhost:5433/one/two": "TARGET_DATABASE_PATH_INVALID",
        "postgresql://demo-user@localhost:5433/demo-db/": "TARGET_DATABASE_PATH_INVALID",
        "postgresql://demo-user@localhost:5433//demo-db": "TARGET_DATABASE_MISSING",
        "postgresql://demo-user@localhost:5433/demo%2Fdb": "TARGET_DATABASE_PATH_INVALID",
        "postgresql://demo-user@localhost:5433/gongkar": "TARGET_DATABASE_FORBIDDEN",
        "postgresql://demo-user@localhost:5433/GONGKAR": "TARGET_DATABASE_FORBIDDEN",
        "postgresql://demo-user@localhost:5433/demo-db?host=example.com": "TARGET_DSN_OPTIONS_NOT_ALLOWED",
        "mysql://demo-user@localhost:5433/demo-db": "TARGET_SCHEME_MISMATCH",
        "postgresql://demo-user@localhost:notaport/demo-db": "TARGET_PORT_INVALID",
    }
    for dsn, expected_code in invalid.items():
        with pytest.raises(verifier.SafeStop, match=f"^{expected_code}$"):
            verifier.validate_boundary(dsn)


def test_结构化解析_explain_节点与目标索引() -> None:
    plan = [{"Plan": {"Node Type": "Index Scan", "Index Name": verifier.TARGET_INDEX}}]

    assert verifier.plan_node_types(plan) == {"Index Scan"}
    assert verifier.plan_index_names(plan) == {verifier.TARGET_INDEX}
    assert verifier.plan_index_names(json.dumps(plan)) == {verifier.TARGET_INDEX}
    assert verifier.plan_index_names("not-json") == set()
    assert verifier.plan_uses_target_index_scan(plan) is True
    assert verifier.plan_uses_target_index_scan(
        [
            {"Plan": {"Node Type": "Index Scan", "Index Name": "other_index"}},
            {"Metadata": {"Index Name": verifier.TARGET_INDEX}},
        ]
    ) is False


def test_目标读取异常转换为无细节命名停止() -> None:
    with (
        patch(
            "src.infrastructure.services.postgres_engine.create_read_only_postgres_engine",
            side_effect=RuntimeError("不得出现在输出中的原始连接异常"),
        ),
        pytest.raises(verifier.SafeStop, match=r"^TARGET_READ_UNAVAILABLE$"),
    ):
        verifier.read_target_facts("postgresql://demo-user@localhost:5433/demo-db")


def test_http_失败保留写入是否可能开始的语义() -> None:
    class Response:
        status_code = 503

        @staticmethod
        def json() -> dict[str, object]:
            return {}

    with pytest.raises(verifier.ChainFailure) as before_write:
        verifier.safe_json(Response(), 200)
    assert before_write.value.code == "HTTP_503_EXPECTED_200"
    assert before_write.value.target_write_may_have_started is False

    with pytest.raises(verifier.ChainFailure) as after_write:
        verifier.safe_json(Response(), 200, target_write_may_have_started=True)
    assert after_write.value.code == "HTTP_503_EXPECTED_200"
    assert after_write.value.target_write_may_have_started is True


def test_人工闸门未配置目录时安全停止(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(verifier.HUMAN_GATE_DIR_ENV, raising=False)

    with pytest.raises(verifier.SafeStop, match=r"^HUMAN_GATE_DIR_NOT_IN_PROCESS_ENV$"):
        verifier.require_human_confirmation("approval", {"proposal_id": "redacted"})


def test_人工闸门只接受挑战创建后的匹配响应(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(verifier.HUMAN_GATE_DIR_ENV, str(tmp_path))
    challenge_path = tmp_path / "p8-s2-approval-challenge.json"
    response_path = tmp_path / "p8-s2-approval-response.json"
    response_path.write_text(
        json.dumps({"stage": "approval", "challenge_id": "stale", "decision": "approve"}),
        encoding="utf-8",
    )
    observed: dict[str, object] = {}

    def respond_to_fresh_challenge(_seconds: float) -> None:
        challenge = json.loads(challenge_path.read_text(encoding="utf-8"))
        observed.update(challenge)
        response_path.write_text(
            json.dumps(
                {
                    "stage": challenge["stage"],
                    "challenge_id": challenge["challenge_id"],
                    "decision": challenge["required_decision"],
                }
            ),
            encoding="utf-8",
        )

    with patch.object(verifier.time, "sleep", side_effect=respond_to_fresh_challenge):
        verifier.require_human_confirmation("approval", {"proposal_id": "proposal-safe-id"})

    assert observed["challenge_id"] != "stale"
    assert observed["summary"] == {"proposal_id": "proposal-safe-id"}
    assert not challenge_path.exists()
    assert not response_path.exists()


def test_人工闸门拒绝不匹配挑战响应(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(verifier.HUMAN_GATE_DIR_ENV, str(tmp_path))
    challenge_path = tmp_path / "p8-s2-execution-challenge.json"
    response_path = tmp_path / "p8-s2-execution-response.json"

    def write_mismatched_response(_seconds: float) -> None:
        assert challenge_path.exists()
        response_path.write_text(
            json.dumps({"stage": "execution", "challenge_id": "wrong", "decision": "execute"}),
            encoding="utf-8",
        )

    with (
        patch.object(verifier.time, "sleep", side_effect=write_mismatched_response),
        pytest.raises(verifier.SafeStop, match=r"^HUMAN_GATE_CHALLENGE_MISMATCH$"),
    ):
        verifier.require_human_confirmation("execution", {"proposal_id": "proposal-safe-id"})

    assert not challenge_path.exists()
    assert not response_path.exists()


SESSION_ID = "11111111-1111-4111-8111-111111111111"
RUN_ID = "22222222-2222-4222-8222-222222222222"
PROPOSAL_ID = "33333333-3333-4333-8333-333333333333"
EXECUTION_ID = "44444444-4444-4444-8444-444444444444"
VERIFICATION_ID = "55555555-5555-4555-8555-555555555555"
ACTION_DIGEST = "a" * 64
EVENT_TYPES = [
    "proposal_created",
    "approval_recorded",
    "execution_requested",
    "execution_started",
    "precondition_checked",
    "execution_completed",
    "verification_started",
    "verification_completed",
]


class _Response:
    def __init__(self, payload: dict[str, object], status_code: int) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict[str, object]:
        return deepcopy(self._payload)


def _recording_human_gate(calls: list[tuple[str, dict[str, Any]]]) -> verifier.HumanGate:
    def confirm(stage: str, summary: dict[str, Any]) -> None:
        calls.append((stage, deepcopy(summary)))

    return confirm


def _confirmed_human_gate(_stage: str, _summary: dict[str, Any]) -> None:
    """Explicit test-only confirmation; production defaults to the file handshake."""


class _ApiChainClient:
    def __init__(self) -> None:
        target = {
            "service_id": verifier.TARGET_SERVICE,
            "schema": verifier.TARGET_SCHEMA,
            "table": verifier.TARGET_TABLE,
            "columns": verifier.TARGET_COLUMNS,
            "index_name": verifier.TARGET_INDEX,
        }
        self.pending_proposal: dict[str, object] = {
            "id": PROPOSAL_ID,
            "source_run_id": RUN_ID,
            "action_id": verifier.TARGET_ACTION_ID,
            "action_digest": ACTION_DIGEST,
            "mode": "target",
            "status": "pending_approval",
            "target": target,
            "risk_summary": verifier.TARGET_RISK_SUMMARY,
            "verification_plan": verifier.TARGET_VERIFICATION_PLAN,
        }
        self.approved_proposal = {
            **self.pending_proposal,
            "status": "approved",
            "approval": {
                "actor": "local_operator",
                "decision": "approve",
                "action_digest": ACTION_DIGEST,
            },
        }
        self.final_proposal: dict[str, object] = {
            **self.approved_proposal,
            "status": "verified",
            "execution": {
                "id": EXECUTION_ID,
                "proposal_id": PROPOSAL_ID,
                "mode": "target",
                "status": "succeeded",
            },
            "verification": {
                "id": VERIFICATION_ID,
                "execution_id": EXECUTION_ID,
                "mode": "target",
                "status": "verified",
                "facts": {"index_exists": True, "index_valid": True, "plan_uses_index": True},
            },
        }
        self.events: list[dict[str, object]] = [
            {"proposal_id": PROPOSAL_ID, "sequence": sequence, "type": event_type}
            for sequence, event_type in enumerate(EVENT_TYPES, start=1)
        ]

    def post(self, path: str, **_kwargs: object) -> _Response:
        if path == "/api/v1/sessions":
            return _Response({"session": {"id": SESSION_ID, "service_id": verifier.TARGET_SERVICE}}, 201)
        if path == f"/api/v1/sessions/{SESSION_ID}/runs":
            return _Response({"run": {"id": RUN_ID, "service_id": verifier.TARGET_SERVICE}}, 202)
        if path == f"/api/v1/action-proposals/{PROPOSAL_ID}/approval":
            return _Response({"proposal": self.approved_proposal}, 200)
        if path == f"/api/v1/action-proposals/{PROPOSAL_ID}/executions":
            return _Response({"execution": self.final_proposal["execution"]}, 202)
        raise AssertionError(path)

    def get(self, path: str) -> _Response:
        if path == f"/api/v1/runs/{RUN_ID}":
            return _Response(
                {"run": {"id": RUN_ID, "service_id": verifier.TARGET_SERVICE, "status": "succeeded"}},
                200,
            )
        if path == f"/api/v1/runs/{RUN_ID}/action-proposal":
            return _Response({"proposal": self.pending_proposal}, 200)
        if path == f"/api/v1/action-proposals/{PROPOSAL_ID}":
            return _Response({"proposal": self.final_proposal}, 200)
        if path == f"/api/v1/action-proposals/{PROPOSAL_ID}/events?limit=100":
            return _Response({"items": self.events}, 200)
        raise AssertionError(path)


def test_离线_api_链验证固定边界与完整关联() -> None:
    gate_calls: list[tuple[str, dict[str, Any]]] = []
    result = verifier.run_api_chain_with_client(
        _ApiChainClient(),
        human_gate=_recording_human_gate(gate_calls),
    )

    assert [stage for stage, _summary in gate_calls] == ["approval", "execution"]
    assert gate_calls[0][1]["proposal_id"] == PROPOSAL_ID
    assert gate_calls[0][1]["action_digest"] == ACTION_DIGEST
    assert gate_calls[0][1]["target"]["index_name"] == verifier.TARGET_INDEX
    assert gate_calls[1][1]["approval_actor"] == "local_operator"
    assert result["session_id"] == SESSION_ID
    assert result["run_id"] == RUN_ID
    assert result["proposal_id"] == PROPOSAL_ID
    assert result["execution_id"] == EXECUTION_ID
    assert result["proposal_status"] == "verified"
    assert result["verification_facts"] == {
        "index_exists": True,
        "index_valid": True,
        "plan_uses_index": True,
    }
    assert result["action_event_types"] == EVENT_TYPES


def test_提案固定边界不匹配时在执行请求前停止() -> None:
    client = _ApiChainClient()
    target = client.pending_proposal["target"]
    assert isinstance(target, dict)
    target["table"] = "other"

    with pytest.raises(verifier.SafeStop, match=r"^PROPOSAL_TARGET_MISMATCH$"):
        verifier.run_api_chain_with_client(client, human_gate=_confirmed_human_gate)


def test_执行资源串线在写后标记失败() -> None:
    client = _ApiChainClient()
    execution = client.final_proposal["execution"]
    assert isinstance(execution, dict)
    execution["proposal_id"] = SESSION_ID

    with pytest.raises(verifier.ChainFailure) as caught:
        verifier.run_api_chain_with_client(client, human_gate=_confirmed_human_gate)

    assert caught.value.code == "EXECUTION_PROPOSAL_MISMATCH"
    assert caught.value.target_write_may_have_started is True


def test_关键审计事件重复在写后标记失败() -> None:
    client = _ApiChainClient()
    client.events.append({"proposal_id": PROPOSAL_ID, "sequence": 9, "type": "proposal_created"})

    with pytest.raises(verifier.ChainFailure) as caught:
        verifier.run_api_chain_with_client(client, human_gate=_confirmed_human_gate)

    assert caught.value.code == "ACTION_EVENT_CHAIN_DUPLICATED"
    assert caught.value.target_write_may_have_started is True


def test_关键审计事件语义乱序在写后标记失败() -> None:
    client = _ApiChainClient()
    client.events[0]["type"], client.events[1]["type"] = client.events[1]["type"], client.events[0]["type"]

    with pytest.raises(verifier.ChainFailure) as caught:
        verifier.run_api_chain_with_client(client, human_gate=_confirmed_human_gate)

    assert caught.value.code == "ACTION_EVENT_CHAIN_OUT_OF_ORDER"
    assert caught.value.target_write_may_have_started is True


def test_审计事件数值序列缺口在写后标记失败() -> None:
    client = _ApiChainClient()
    client.events[0]["sequence"] = 2

    with pytest.raises(verifier.ChainFailure) as caught:
        verifier.run_api_chain_with_client(client, human_gate=_confirmed_human_gate)

    assert caught.value.code == "ACTION_EVENT_SEQUENCE_OUT_OF_ORDER"
    assert caught.value.target_write_may_have_started is True


def test_无凭据时_main_安全停止且不声称发生写入(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.delenv(verifier.TARGET_ENV, raising=False)
    monkeypatch.setattr(verifier, "_HAS_RUN", False)

    assert verifier.main() == 2

    payload = json.loads(capsys.readouterr().out)
    assert payload == {
        "result": "SAFE_STOP",
        "code": "DSN_NOT_IN_PROCESS_ENV",
        "target_write_may_have_started": False,
    }


def test_同一进程二次运行被安全拒绝(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(verifier, "_HAS_RUN", True)

    assert verifier.main() == 2

    assert json.loads(capsys.readouterr().out) == {
        "result": "SAFE_STOP",
        "code": "VERIFIER_PROCESS_ALREADY_USED",
        "target_write_may_have_started": False,
    }


def test_api链完成后_lifespan退出异常保守标记写入() -> None:
    from src import app as api_module

    class _TeardownFailureClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _TeardownFailureClient:
            return self

        def __exit__(self, *_args: object) -> None:
            raise RuntimeError("不得进入输出的 lifespan teardown 异常")

    original_services = api_module.app.state.v1_services
    with (
        patch("fastapi.testclient.TestClient", _TeardownFailureClient),
        patch.object(verifier, "run_api_chain_with_client", return_value={"result": "verified"}),
        patch.object(verifier, "dispose_session_factory"),
        pytest.raises(verifier.ChainFailure) as caught,
    ):
        verifier.run_api_chain()

    assert api_module.app.state.v1_services is original_services
    assert caught.value.code == "API_CHAIN_TEARDOWN_FAILED"
    assert caught.value.target_write_may_have_started is True


def test_api链进入失败保持写前异常语义() -> None:
    from src import app as api_module

    class _EnterFailureClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _EnterFailureClient:
            raise RuntimeError("不得进入输出的 lifespan startup 异常")

        def __exit__(self, *_args: object) -> None:
            raise AssertionError("enter 失败后不得调用 exit")

    original_services = api_module.app.state.v1_services
    with (
        patch("fastapi.testclient.TestClient", _EnterFailureClient),
        patch.object(verifier, "dispose_session_factory"),
        pytest.raises(RuntimeError, match="lifespan startup") as caught,
    ):
        verifier.run_api_chain()

    assert not isinstance(caught.value, verifier.ChainFailure)
    assert api_module.app.state.v1_services is original_services


def test_api链_body写前异常不被退出异常覆盖() -> None:
    from src import app as api_module

    class _BodyAndExitFailureClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _BodyAndExitFailureClient:
            return self

        def __exit__(self, *_args: object) -> None:
            raise RuntimeError("不得覆盖 body 异常的 teardown 异常")

    original_services = api_module.app.state.v1_services
    with (
        patch("fastapi.testclient.TestClient", _BodyAndExitFailureClient),
        patch.object(verifier, "run_api_chain_with_client", side_effect=verifier.SafeStop("PREWRITE_BODY_STOP")),
        patch.object(verifier, "dispose_session_factory"),
        pytest.raises(verifier.SafeStop, match=r"^PREWRITE_BODY_STOP$") as caught,
    ):
        verifier.run_api_chain()

    assert not isinstance(caught.value, verifier.ChainFailure)
    assert api_module.app.state.v1_services is original_services


def test_api链_body写后异常即使退出也失败仍保留写入标记() -> None:
    from src import app as api_module

    class _BodyAndExitFailureClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> _BodyAndExitFailureClient:
            return self

        def __exit__(self, *_args: object) -> None:
            raise RuntimeError("不得覆盖写后 body 异常的 teardown 异常")

    def fail_after_execution(
        _client: object,
        *,
        chain_state: verifier.ChainState | None = None,
        human_gate: verifier.HumanGate = _confirmed_human_gate,
    ) -> dict[str, object]:
        del human_gate
        assert chain_state is not None
        chain_state.target_write_may_have_started = True
        raise RuntimeError("不得进入输出的写后 body 异常")

    original_services = api_module.app.state.v1_services
    with (
        patch("fastapi.testclient.TestClient", _BodyAndExitFailureClient),
        patch.object(verifier, "run_api_chain_with_client", side_effect=fail_after_execution),
        patch.object(verifier, "dispose_session_factory"),
        pytest.raises(verifier.ChainFailure) as caught,
    ):
        verifier.run_api_chain()

    assert api_module.app.state.v1_services is original_services
    assert caught.value.code == "API_CHAIN_UNEXPECTED_AFTER_EXECUTION_REQUEST"
    assert caught.value.target_write_may_have_started is True


def test_api链进入阶段未知失败在_main_中仍标记写前(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preflight = {
        "table_exists": True,
        "columns_ok": True,
        "index_exists": False,
        "index_valid": False,
        "plan_seq_scan": True,
        "plan_index_scan": False,
        "plan_uses_target_index": False,
    }
    monkeypatch.setenv(verifier.TARGET_ENV, "postgresql://demo-user@localhost:5433/demo-db")
    monkeypatch.setattr(verifier, "_HAS_RUN", False)
    with (
        patch.object(verifier, "read_target_facts", return_value=preflight),
        patch.object(verifier, "run_api_chain", side_effect=RuntimeError("不得进入输出的 startup 异常")),
    ):
        assert verifier.main() == 1

    assert json.loads(capsys.readouterr().out) == {
        "result": "FAIL",
        "code": "UNEXPECTED_SAFE_REDACTED_FAILURE",
        "target_write_may_have_started": False,
    }


def test_真实链完成后临时元数据清理异常保守标记写入(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class _CleanupFailureDirectory:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> str:
            return str(tmp_path)

        def __exit__(self, *_args: object) -> None:
            raise RuntimeError("不得进入输出的临时目录清理异常")

    preflight = {
        "table_exists": True,
        "columns_ok": True,
        "index_exists": False,
        "index_valid": False,
        "plan_seq_scan": True,
        "plan_index_scan": False,
        "plan_uses_target_index": False,
    }
    monkeypatch.setenv(verifier.TARGET_ENV, "postgresql://demo-user@localhost:5433/demo-db")
    monkeypatch.setattr(verifier, "_HAS_RUN", False)
    with (
        patch.object(verifier, "read_target_facts", return_value=preflight),
        patch.object(verifier, "run_api_chain", return_value={"result": "verified"}),
        patch.object(verifier.tempfile, "TemporaryDirectory", _CleanupFailureDirectory),
    ):
        assert verifier.main() == 1

    assert json.loads(capsys.readouterr().out) == {
        "result": "FAIL",
        "code": "TEMP_METADATA_CLEANUP_FAILED",
        "target_write_may_have_started": True,
    }


def test_写后链异常被临时目录退出异常覆盖时仍保守标记写入(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    class _CleanupFailureDirectory:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def __enter__(self) -> str:
            return str(tmp_path)

        def __exit__(self, *_args: object) -> None:
            raise RuntimeError("不得覆盖写后链异常的临时目录退出异常")

    def fail_after_execution(*, chain_state: verifier.ChainState) -> dict[str, object]:
        chain_state.target_write_may_have_started = True
        raise verifier.ChainFailure("WRITE_STAGE_FAILURE", target_write_may_have_started=True)

    preflight = {
        "table_exists": True,
        "columns_ok": True,
        "index_exists": False,
        "index_valid": False,
        "plan_seq_scan": True,
        "plan_index_scan": False,
        "plan_uses_target_index": False,
    }
    monkeypatch.setenv(verifier.TARGET_ENV, "postgresql://demo-user@localhost:5433/demo-db")
    monkeypatch.setattr(verifier, "_HAS_RUN", False)
    with (
        patch.object(verifier, "read_target_facts", return_value=preflight),
        patch.object(verifier, "run_api_chain", side_effect=fail_after_execution),
        patch.object(verifier.tempfile, "TemporaryDirectory", _CleanupFailureDirectory),
    ):
        assert verifier.main() == 1

    assert json.loads(capsys.readouterr().out) == {
        "result": "FAIL",
        "code": "TEMP_METADATA_CLEANUP_FAILED",
        "target_write_may_have_started": True,
    }


def test_真实链完成后未知异常保守标记写入(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    preflight = {
        "table_exists": True,
        "columns_ok": True,
        "index_exists": False,
        "index_valid": False,
        "plan_seq_scan": True,
        "plan_index_scan": False,
        "plan_uses_target_index": False,
    }
    monkeypatch.setenv(verifier.TARGET_ENV, "postgresql://demo-user@localhost:5433/demo-db")
    monkeypatch.setattr(verifier, "_HAS_RUN", False)
    with (
        patch.object(verifier, "read_target_facts", side_effect=[preflight, RuntimeError("不得进入输出的异常")]),
        patch.object(verifier, "run_api_chain", return_value={"result": "verified"}),
    ):
        assert verifier.main() == 1

    assert json.loads(capsys.readouterr().out) == {
        "result": "FAIL",
        "code": "UNEXPECTED_SAFE_REDACTED_FAILURE",
        "target_write_may_have_started": True,
    }
