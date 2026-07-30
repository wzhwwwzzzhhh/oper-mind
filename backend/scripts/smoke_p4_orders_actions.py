"""P4.2 订单慢查询 target 模式的固定审批、执行与 Verify 真实靶场 smoke。"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

try:
    from scripts._bootstrap import BACKEND_ROOT, PROJECT_ROOT
except ModuleNotFoundError:  # 允许直接按文件路径执行。
    from _bootstrap import BACKEND_ROOT, PROJECT_ROOT

from src.api.v1.dependencies import build_v1_services_for_runtime
from src.infrastructure.diagnosis.demo_orders.settings import EvidenceMode, load_demo_orders_evidence_settings
from src.infrastructure.persistence.database import create_persistence_runtime


ALEMBIC_INI = BACKEND_ROOT / "alembic.ini"
DEMO_COMMAND = BACKEND_ROOT / "scripts" / "demo_orders_env.py"
TARGET_SMOKE_ATTEMPTS = 3


class SmokeError(RuntimeError):
    """真实靶场 smoke 的安全失败，不输出命令、凭据或原始响应。"""


def main() -> int:
    """执行完整 P4.2 路径；仅在靶场性能抖动时重新准备一次独立尝试。"""
    environment = os.environ.copy()
    environment["OPERMIND_DEMO_ORDERS_EVIDENCE_MODE"] = EvidenceMode.TARGET.value
    environment.setdefault("OPERMIND_API_KEY", "mock")
    environment.setdefault("OPERMIND_BASE_URL", "http://mock")
    environment.setdefault("OPERMIND_MODEL", "mock")

    target_settings = load_demo_orders_evidence_settings(
        environment,
        app_database_url=f"sqlite:///{(PROJECT_ROOT / 'data' / 'smoke-placeholder.sqlite3').as_posix()}",
    )
    if target_settings.mode is not EvidenceMode.TARGET:
        raise SmokeError("P4.2 smoke 未进入 target 模式。")

    failure: SmokeError | None = None
    for _attempt in range(TARGET_SMOKE_ATTEMPTS):
        try:
            _run_target_smoke_attempt(environment)
            print("P4.2 target smoke passed: proposal approval, fixed executor and independent Verify cleanup verified.")
            return 0
        except SmokeError as error:
            failure = error
    raise SmokeError("P4.2 target smoke 在独立重建后仍未通过。") from failure


def _run_target_smoke_attempt(environment: dict[str, str]) -> None:
    """执行一次严格的 start → inject → Proposal → Verify → clean 真实验收。"""
    with tempfile.TemporaryDirectory(prefix="opermind-p4-actions-smoke-") as temporary_directory:
        application_database = Path(temporary_directory) / "opermind-p4-actions-smoke.sqlite3"
        application_database_url = f"sqlite:///{application_database.as_posix()}"
        attempt_environment = environment.copy()
        attempt_environment["OPERMIND_APP_DATABASE_URL"] = application_database_url
        process_overrides = {
            "OPERMIND_API_KEY": attempt_environment["OPERMIND_API_KEY"],
            "OPERMIND_BASE_URL": attempt_environment["OPERMIND_BASE_URL"],
            "OPERMIND_MODEL": attempt_environment["OPERMIND_MODEL"],
            "OPERMIND_APP_DATABASE_URL": application_database_url,
            "OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": EvidenceMode.TARGET.value,
        }
        previous_values = {name: os.environ.get(name) for name in process_overrides}
        os.environ.update(process_overrides)
        try:
            _upgrade_application_database(attempt_environment)
            _run_demo_command(attempt_environment, "start", "--samples", "3")
            _run_demo_command(attempt_environment, "inject", "--samples", "3")
            _run_p4_2_api_flow(application_database)
        finally:
            for name, previous_value in previous_values.items():
                _restore_environment_variable(name, previous_value)
            _clean_target(attempt_environment)


def _restore_environment_variable(name: str, value: str | None) -> None:
    """恢复 smoke 进程中的应用元数据环境变量。"""
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _upgrade_application_database(environment: dict[str, str]) -> None:
    """仅经 Alembic 创建临时应用元数据库。"""
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError("P4.2 smoke 无法准备临时应用元数据库。")


def _run_demo_command(environment: dict[str, str], *arguments: str) -> None:
    """仅用已验收靶场脚本准备或 finally 回收专用 target。"""
    completed = subprocess.run(
        [sys.executable, str(DEMO_COMMAND), *arguments],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError("受控订单慢查询靶场准备或回收失败。")


def _clean_target(environment: dict[str, str]) -> None:
    """无论 smoke 成败都只清理专用靶场 schema 与运行时文件。"""
    _run_demo_command(environment, "clean")


def _run_p4_2_api_flow(application_database: Path) -> None:
    """通过产品 API 走完整 P4.2 状态机，不调用 Work 1 repair 动作。"""
    from src import app as api_module

    runtime = create_persistence_runtime(f"sqlite:///{application_database.as_posix()}")
    services = build_v1_services_for_runtime(
        runtime,
        api_module.coordinator,
        app_database_url=f"sqlite:///{application_database.as_posix()}",
    )
    previous_services = api_module.app.state.v1_services
    api_module.app.state.v1_services = services
    try:
        with TestClient(api_module.app, raise_server_exceptions=False) as client:
            session_response = client.post("/api/v1/sessions", json={"title": "P4.2 target smoke"})
            if session_response.status_code != 201:
                raise SmokeError("P4.2 smoke 无法创建会话。")
            session_id = session_response.json()["session"]["id"]
            accepted = client.post(
                f"/api/v1/sessions/{session_id}/runs",
                headers={"Idempotency-Key": str(uuid4())},
                json={"query": "订单服务变慢，帮我排查慢查询"},
            )
            if accepted.status_code != 202:
                raise SmokeError("P4.2 smoke 无法受理调查。")
            run_id = accepted.json()["run"]["id"]
            proposal_response = client.get(f"/api/v1/runs/{run_id}/action-proposal")
            if proposal_response.status_code != 200:
                raise SmokeError("P4.2 smoke 无法读取固定修复提案。")
            proposal = proposal_response.json().get("proposal")
            if not isinstance(proposal, dict) or proposal.get("status") != "pending_approval":
                raise SmokeError("P4.2 smoke 未从确认调查生成 pending 提案。")
            proposal_id = proposal.get("id")
            if not isinstance(proposal_id, str):
                raise SmokeError("P4.2 smoke 提案标识无效。")
            approval_response = client.post(
                f"/api/v1/action-proposals/{proposal_id}/approval",
                headers={"Idempotency-Key": str(uuid4())},
                json={"decision": "approve"},
            )
            if approval_response.status_code != 200:
                raise SmokeError("P4.2 smoke 无法批准固定提案。")
            execution_response = client.post(
                f"/api/v1/action-proposals/{proposal_id}/executions",
                headers={"Idempotency-Key": str(uuid4())},
                json={},
            )
            if execution_response.status_code != 202:
                raise SmokeError("P4.2 smoke 无法声明固定执行。")
            final_response = client.get(f"/api/v1/action-proposals/{proposal_id}")
            events_response = client.get(f"/api/v1/action-proposals/{proposal_id}/events")
    finally:
        api_module.app.state.v1_services = previous_services
        runtime.engine.dispose()

    if final_response.status_code != 200 or events_response.status_code != 200:
        raise SmokeError("P4.2 smoke 无法读取最终 action 审计事实。")
    proposal = final_response.json().get("proposal")
    events = events_response.json().get("items")
    if not isinstance(proposal, dict) or not isinstance(events, list):
        raise SmokeError("P4.2 smoke 收到不符合预期的公开资源。")
    verification = proposal.get("verification")
    facts = verification.get("facts") if isinstance(verification, dict) else None
    event_types = [item.get("type") for item in events if isinstance(item, dict)]
    checks = {
        "target_mode": proposal.get("mode") == "target",
        "verified": proposal.get("status") == "verified",
        "execution_succeeded": isinstance(proposal.get("execution"), dict)
        and proposal["execution"].get("status") == "succeeded",
        "verification_status": isinstance(verification, dict) and verification.get("status") == "verified",
        "three_probes": isinstance(facts, dict) and facts.get("probe_count") == 3,
        "matching_logs": isinstance(facts, dict) and facts.get("matched_log_count") == 3,
        "terminal_action_event": event_types[-1:] == ["verification_completed"],
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise SmokeError(f"P4.2 smoke Proposal、执行或 Verify 验收不通过：{', '.join(failed_checks)}。")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeError, ValueError) as error:
        print(f"P4.2 target smoke failed safely: {error}", file=sys.stderr)
        raise SystemExit(1)
