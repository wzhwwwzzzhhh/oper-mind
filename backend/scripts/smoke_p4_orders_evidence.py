"""P4.1 订单慢查询 target 模式的端到端真实靶场 smoke。"""

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


class SmokeError(RuntimeError):
    """真实靶场 smoke 的安全失败，不输出命令、凭据或原始响应。"""


def main() -> int:
    """执行 start → inject → API 调查 → repair → clean 的受控 P4.1 验收。"""
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
        raise SmokeError("P4.1 smoke 未进入 target 模式。")

    with tempfile.TemporaryDirectory(prefix="opermind-p4-smoke-") as temporary_directory:
        application_database = Path(temporary_directory) / "opermind-p4-smoke.sqlite3"
        application_database_url = f"sqlite:///{application_database.as_posix()}"
        environment["OPERMIND_APP_DATABASE_URL"] = application_database_url
        process_overrides = {
            "OPERMIND_API_KEY": environment["OPERMIND_API_KEY"],
            "OPERMIND_BASE_URL": environment["OPERMIND_BASE_URL"],
            "OPERMIND_MODEL": environment["OPERMIND_MODEL"],
            "OPERMIND_APP_DATABASE_URL": application_database_url,
            "OPERMIND_DEMO_ORDERS_EVIDENCE_MODE": EvidenceMode.TARGET.value,
        }
        previous_values = {name: os.environ.get(name) for name in process_overrides}
        os.environ.update(process_overrides)
        try:
            _upgrade_application_database(environment)
            _run_demo_command(environment, "start", "--samples", "3")
            _run_demo_command(environment, "inject", "--samples", "3")
            _run_api_investigation(application_database)
            _run_demo_command(environment, "repair", "--samples", "3")
        finally:
            for name, previous_value in previous_values.items():
                _restore_environment_variable(name, previous_value)
            _clean_target(environment)

    print("P4.1 target smoke passed: readonly evidence result, event replay and recovery cleanup verified.")
    return 0


def _restore_environment_variable(name: str, value: str | None) -> None:
    """恢复当前 smoke 进程的应用元数据环境变量。"""
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _upgrade_application_database(environment: dict[str, str]) -> None:
    """仅经 Alembic 创建临时 SQLite 应用元数据表。"""
    completed = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), "upgrade", "head"],
        cwd=PROJECT_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise SmokeError("P4.1 smoke 无法准备临时应用元数据库。")


def _run_demo_command(environment: dict[str, str], *arguments: str) -> None:
    """调用已验收的 Work 1 控制脚本；失败时不回显可能含敏感信息的输出。"""
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
    """无论调查是否成功都只回收专用 schema 与靶场运行时文件。"""
    _run_demo_command(environment, "clean")


def _run_api_investigation(application_database: Path) -> None:
    """通过既有 API 创建会话/Run，并验证 P4.1 可回放结果。"""
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
            session_response = client.post("/api/v1/sessions", json={"title": "P4.1 target smoke"})
            if session_response.status_code != 201:
                raise SmokeError("P4.1 smoke 无法创建会话。")
            session_id = session_response.json()["session"]["id"]
            accepted = client.post(
                f"/api/v1/sessions/{session_id}/runs",
                headers={"Idempotency-Key": str(uuid4())},
                json={"query": "订单服务变慢，帮我排查慢查询"},
            )
            if accepted.status_code != 202:
                raise SmokeError("P4.1 smoke 无法受理调查。")
            run_id = accepted.json()["run"]["id"]
            run_response = client.get(f"/api/v1/runs/{run_id}")
            events_response = client.get(f"/api/v1/runs/{run_id}/events")
            stream_response = client.get(f"/api/v1/runs/{run_id}/stream")
    finally:
        api_module.app.state.v1_services = previous_services
        runtime.engine.dispose()

    if (
        run_response.status_code != 200
        or events_response.status_code != 200
        or stream_response.status_code != 200
        or not stream_response.headers.get("content-type", "").startswith("text/event-stream")
    ):
        raise SmokeError("P4.1 smoke 无法读取已保存调查或 SSE 回放。")
    run = run_response.json().get("run")
    event_items = events_response.json().get("items")
    if not isinstance(run, dict) or not isinstance(event_items, list):
        raise SmokeError("P4.1 smoke 收到不符合预期的公开资源。")
    result = run.get("result")
    if run.get("status") != "succeeded" or not isinstance(result, dict):
        raise SmokeError("P4.1 smoke 未得到成功的只读调查结果。")
    evidence = result.get("evidence")
    root_causes = result.get("root_causes")
    source_types = {item.get("source_type") for item in evidence if isinstance(item, dict)} if isinstance(evidence, list) else set()
    event_types = [item.get("type") for item in event_items if isinstance(item, dict)]
    checks = {
        "severity": result.get("severity") == "high",
        "confidence": result.get("confidence") == 0.95,
        "evidence_sources": source_types == {"database", "log", "metric"},
        "single_root_cause": isinstance(root_causes, list) and len(root_causes) == 1,
        "terminal_event": event_types[-1:] == ["run_succeeded"],
        "sse_terminal_replay": '"type":"run_succeeded"' in stream_response.text.replace(" ", ""),
    }
    failed_checks = [name for name, passed in checks.items() if not passed]
    if failed_checks:
        raise SmokeError(f"P4.1 smoke 证据、根因或事件验收不通过：{', '.join(failed_checks)}。")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (SmokeError, ValueError) as error:
        print(f"P4.1 target smoke failed safely: {error}", file=sys.stderr)
        raise SystemExit(1)
