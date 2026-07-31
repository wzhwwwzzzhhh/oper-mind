"""P4.3 服务中心入口到固定修复 Verify 的 target 真实靶场 smoke。"""

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
SERVICE_ID = "order-service"


class SmokeError(RuntimeError):
    """真实靶场 smoke 的安全失败，不输出命令、凭据或原始响应。"""


def main() -> int:
    """执行 P4.3 服务入口、调查、固定修复和留痕的完整 target 路径。"""
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
        raise SmokeError("P4.3 smoke 未进入 target 模式。")

    failure: SmokeError | None = None
    for _attempt in range(TARGET_SMOKE_ATTEMPTS):
        try:
            _run_target_smoke_attempt(environment)
            print("P4.3 target smoke 通过：服务快照、服务会话、调查、审批执行、Verify 与活动留痕已验证。")
            return 0
        except SmokeError as error:
            failure = error
    raise SmokeError("P4.3 target smoke 在独立重建后仍未通过。") from failure


def _run_target_smoke_attempt(environment: dict[str, str]) -> None:
    """执行一次严格的 start → inject → 服务入口 → Verify → clean 验收。"""
    with tempfile.TemporaryDirectory(prefix="opermind-p4-service-center-smoke-") as temporary_directory:
        application_database = Path(temporary_directory) / "opermind-p4-service-center-smoke.sqlite3"
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
            _run_p4_3_api_flow(application_database)
        finally:
            for name, previous_value in previous_values.items():
                _restore_environment_variable(name, previous_value)
            _clean_target(attempt_environment)


def _restore_environment_variable(name: str, value: str | None) -> None:
    """恢复 smoke 进程的应用元数据环境变量。"""
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
        raise SmokeError("P4.3 smoke 无法准备临时应用元数据库。")


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


def _run_p4_3_api_flow(application_database: Path) -> None:
    """通过公开产品 API 验证服务页到 P4.2 闭环的真实留痕。"""
    from src import app as api_module

    application_database_url = f"sqlite:///{application_database.as_posix()}"
    runtime = create_persistence_runtime(application_database_url)
    services = build_v1_services_for_runtime(
        runtime,
        api_module.coordinator,
        app_database_url=application_database_url,
    )
    previous_services = api_module.app.state.v1_services
    api_module.app.state.v1_services = services
    try:
        with TestClient(api_module.app, raise_server_exceptions=False) as client:
            initial_snapshot = client.get(f"/api/v1/services/{SERVICE_ID}")
            _assert_initial_snapshot(initial_snapshot)

            session_response = client.post(f"/api/v1/services/{SERVICE_ID}/sessions")
            session_id = _assert_service_session(session_response)
            _assert_unstarted_session(client, session_id)

            accepted = client.post(
                f"/api/v1/sessions/{session_id}/runs",
                headers={"Idempotency-Key": str(uuid4())},
                json={"query": "订单服务变慢，帮我排查慢查询"},
            )
            if accepted.status_code != 202:
                raise SmokeError("P4.3 smoke 无法受理服务会话中的调查。")
            run_id = accepted.json().get("run", {}).get("id")
            if not isinstance(run_id, str):
                raise SmokeError("P4.3 smoke 返回的调查标识无效。")

            proposal_response = client.get(f"/api/v1/runs/{run_id}/action-proposal")
            proposal_id = _pending_proposal_id(proposal_response)
            approved = client.post(
                f"/api/v1/action-proposals/{proposal_id}/approval",
                headers={"Idempotency-Key": str(uuid4())},
                json={"decision": "approve"},
            )
            if approved.status_code != 200:
                raise SmokeError("P4.3 smoke 无法批准固定修复提案。")
            executed = client.post(
                f"/api/v1/action-proposals/{proposal_id}/executions",
                headers={"Idempotency-Key": str(uuid4())},
                json={},
            )
            if executed.status_code != 202:
                raise SmokeError("P4.3 smoke 无法声明固定修复执行。")

            final_snapshot = client.get(f"/api/v1/services/{SERVICE_ID}")
            activities = client.get(f"/api/v1/services/{SERVICE_ID}/activities")
    finally:
        api_module.app.state.v1_services = previous_services
        runtime.engine.dispose()

    _assert_recovered_snapshot(final_snapshot)
    _assert_verified_activity(activities, session_id, run_id)


def _assert_initial_snapshot(response: object) -> None:
    """确认退化信号来自 target 当前受控读取，而非 mock 回退。"""
    status_code = getattr(response, "status_code", None)
    if status_code != 200:
        raise SmokeError("P4.3 smoke 无法读取服务初始快照。")
    body = response.json()
    snapshot = body.get("service", {}).get("snapshot") if isinstance(body, dict) else None
    checks = {
        "target_mode": isinstance(snapshot, dict) and snapshot.get("mode") == "target",
        "database_available": isinstance(snapshot, dict)
        and snapshot.get("database", {}).get("source_status") == "available",
        "missing_index": isinstance(snapshot, dict)
        and snapshot.get("database", {}).get("signal") == "missing_index_seq_scan_detected",
        "slow_signal": isinstance(snapshot, dict) and snapshot.get("performance_signal") == "slow_query_detected",
    }
    _raise_failed_checks("P4.3 初始服务快照", checks)


def _assert_service_session(response: object) -> str:
    """确认服务入口只创建带静态服务键的 active Session。"""
    status_code = getattr(response, "status_code", None)
    if status_code != 201:
        raise SmokeError("P4.3 smoke 无法创建服务会话。")
    body = response.json()
    session = body.get("session") if isinstance(body, dict) else None
    if not isinstance(session, dict) or session.get("service_id") != SERVICE_ID or session.get("status") != "active":
        raise SmokeError("P4.3 smoke 服务会话未携带受限服务上下文。")
    session_id = session.get("id")
    if not isinstance(session_id, str):
        raise SmokeError("P4.3 smoke 服务会话标识无效。")
    return session_id


def _assert_unstarted_session(client: TestClient, session_id: str) -> None:
    """确认用户未点击调查前没有 Message、Run、Proposal 或外部调查。"""
    messages = client.get(f"/api/v1/sessions/{session_id}/messages")
    runs = client.get(f"/api/v1/sessions/{session_id}/runs")
    if (
        messages.status_code != 200
        or runs.status_code != 200
        or messages.json().get("items") != []
        or runs.json().get("items") != []
    ):
        raise SmokeError("P4.3 smoke 服务入口在用户确认前创建了调查记录。")


def _pending_proposal_id(response: object) -> str:
    """只接受由既有 P4.1 确认事实生成的 pending Proposal。"""
    if getattr(response, "status_code", None) != 200:
        raise SmokeError("P4.3 smoke 无法读取固定修复提案。")
    body = response.json()
    proposal = body.get("proposal") if isinstance(body, dict) else None
    if not isinstance(proposal, dict) or proposal.get("status") != "pending_approval":
        raise SmokeError("P4.3 smoke 未从服务会话调查生成待审批提案。")
    proposal_id = proposal.get("id")
    if not isinstance(proposal_id, str):
        raise SmokeError("P4.3 smoke 固定修复提案标识无效。")
    return proposal_id


def _assert_recovered_snapshot(response: object) -> None:
    """确认 Verify 后服务页反映固定索引和计划事实；不虚构瞬时性能恢复。"""
    if getattr(response, "status_code", None) != 200:
        raise SmokeError("P4.3 smoke 无法读取 Verify 后服务快照。")
    body = response.json()
    snapshot = body.get("service", {}).get("snapshot") if isinstance(body, dict) else None
    checks = {
        "target_mode": isinstance(snapshot, dict) and snapshot.get("mode") == "target",
        "database_available": isinstance(snapshot, dict)
        and snapshot.get("database", {}).get("source_status") == "available",
        "index_and_plan_confirmed": isinstance(snapshot, dict)
        and snapshot.get("database", {}).get("signal") == "index_and_plan_confirmed",
    }
    _raise_failed_checks("P4.3 Verify 后服务快照", checks)


def _assert_verified_activity(response: object, session_id: str, run_id: str) -> None:
    """确认服务页只从绑定会话读取历史 verified 留痕。"""
    if getattr(response, "status_code", None) != 200:
        raise SmokeError("P4.3 smoke 无法读取服务活动。")
    body = response.json()
    items = body.get("items") if isinstance(body, dict) else None
    item = items[0] if isinstance(items, list) and len(items) == 1 else None
    checks = {
        "single_bound_activity": isinstance(item, dict),
        "session": isinstance(item, dict) and item.get("session_id") == session_id,
        "run": isinstance(item, dict) and item.get("run_id") == run_id,
        "run_succeeded": isinstance(item, dict) and item.get("run_status") == "succeeded",
        "proposal_verified": isinstance(item, dict) and item.get("proposal_status") == "verified",
        "verification_verified": isinstance(item, dict) and item.get("verification_status") == "verified",
        "no_raw_action": isinstance(item, dict) and "CREATE INDEX" not in str(item),
    }
    _raise_failed_checks("P4.3 服务活动", checks)


def _raise_failed_checks(scope: str, checks: dict[str, bool]) -> None:
    """将多个公开验收断言收敛为不泄露响应原文的安全错误。"""
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise SmokeError(f"{scope}验收不通过：{', '.join(failed_checks)}。")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeError, ValueError) as error:
        print(f"P4.3 target smoke 安全失败：{error}", file=sys.stderr)
        raise SystemExit(1)
