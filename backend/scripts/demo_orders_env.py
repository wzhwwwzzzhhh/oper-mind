"""本地隧道 PostgreSQL 订单慢 SQL 靶场的受控操作命令。"""

from __future__ import annotations

import argparse
import json
import math
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

import psycopg
from psycopg.rows import dict_row

try:
    from scripts._bootstrap import PROJECT_ROOT
except ModuleNotFoundError:  # 允许直接通过文件路径执行脚本。
    from _bootstrap import PROJECT_ROOT


DEMO_ROOT = PROJECT_ROOT / "demo" / "orders-slow-query"
RUNTIME_DIR = DEMO_ROOT / "runtime"
LOG_FILE = RUNTIME_DIR / "logs" / "order-service.jsonl"
PROCESS_LOG_FILE = RUNTIME_DIR / "logs" / "order-service-process.log"
STATE_DIR = RUNTIME_DIR / "state"
PROCESS_STATE_FILE = STATE_DIR / "order-service.json"
SERVICE_FILE = DEMO_ROOT / "order-service" / "app" / "main.py"
SERVICE_URL = "http://127.0.0.1:18080"
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 5433
TARGET_DATABASE = "opermind_demo"
TARGET_SCHEMA = "opermind_demo"
TARGET_TABLE = "orders"
TARGET_INDEX = "idx_orders_user_created"
TARGET_USER_ID = 42
TARGET_START_AT = "2025-01-01 00:00:00"
TARGET_END_AT = "2026-01-01 00:00:00"
BASELINE_PHASE = "baseline"
DEGRADED_PHASE = "degraded"
RECOVERED_PHASE = "recovered"
DEGRADATION_RATIO = 1.25
RECOVERY_RATIO = 1.8
MIN_DEGRADATION_DELTA_MS = 15.0


class DemoEnvironmentError(RuntimeError):
    """受控 PostgreSQL 靶场未满足安全或运行条件时抛出。"""


@dataclass(frozen=True)
class DatabaseSettings:
    """只允许访问一条本地隧道和一个专用数据库的连接配置。"""

    host: str
    port: int
    database: str
    user: str
    password: str
    order_count: int


@dataclass(frozen=True)
class ProbeMeasurement:
    """单个受控探测窗口的可复核聚合结果。"""

    phase: str
    observed_at: str
    sample_count: int
    request_ids: list[str]
    durations_ms: list[float]
    p50_ms: float
    p95_ms: float
    min_ms: float
    max_ms: float
    slow_query_count: int
    timeout_count: int
    slow_query_threshold_ms: float


@dataclass(frozen=True)
class VerificationReport:
    """故障或恢复阶段的确定性验证结果。"""

    phase: str
    passed: bool
    index_exists: bool
    plan_node_types: list[str]
    plan_index_names: list[str]
    index_used: bool
    sequential_scan_risk: bool
    p95_ms: float
    baseline_p95_ms: float
    p50_ms: float
    baseline_p50_ms: float
    latency_ratio: float
    latency_delta_ms: float
    matching_log_count: int
    slow_query_log_count: int
    timeout_log_count: int
    checks: dict[str, bool]


def utc_now() -> str:
    """返回 UTC ISO 时间，便于跨端审计。"""
    return datetime.now(timezone.utc).isoformat()


def database_settings_from_environment() -> DatabaseSettings:
    """读取并收紧靶场数据库配置，拒绝访问其他主机或数据库。"""
    host = os.environ.get("OPERMIND_DEMO_PG_HOST", TARGET_HOST)
    port = int(os.environ.get("OPERMIND_DEMO_PG_PORT", str(TARGET_PORT)))
    database = os.environ.get("OPERMIND_DEMO_PG_DATABASE", TARGET_DATABASE)
    user = os.environ.get("OPERMIND_DEMO_PG_USER", "").strip()
    password = os.environ.get("OPERMIND_DEMO_PG_PASSWORD", "")
    order_count = int(os.environ.get("OPERMIND_DEMO_ORDER_COUNT", "300000"))

    if host != TARGET_HOST or port != TARGET_PORT or database != TARGET_DATABASE:
        raise DemoEnvironmentError(
            "靶场仅允许访问 127.0.0.1:5433 上的 opermind_demo 数据库。"
        )
    if not user or not password:
        raise DemoEnvironmentError("缺少 OPERMIND_DEMO_PG_USER 或 OPERMIND_DEMO_PG_PASSWORD。")
    if not 100_000 <= order_count <= 1_000_000:
        raise DemoEnvironmentError("OPERMIND_DEMO_ORDER_COUNT 必须位于 100000 到 1000000。")
    return DatabaseSettings(host, port, database, user, password, order_count)


def create_connection(settings: DatabaseSettings) -> psycopg.Connection[dict[str, Any]]:
    """创建指向独立靶场库的 PostgreSQL 连接。"""
    return psycopg.connect(
        host=settings.host,
        port=settings.port,
        dbname=settings.database,
        user=settings.user,
        password=settings.password,
        connect_timeout=5,
        options="-c statement_timeout=30000",
        row_factory=dict_row,
    )


def assert_target_database(connection: psycopg.Connection[dict[str, Any]]) -> None:
    """再次从服务端确认连接库，防止环境变量或隧道误指向其他库。"""
    with connection.cursor() as cursor:
        cursor.execute("SELECT current_database() AS database_name")
        row = cursor.fetchone()
    if not row or row["database_name"] != TARGET_DATABASE:
        raise DemoEnvironmentError("连接目标不是 opermind_demo，拒绝继续执行。")


def percentile(values: Sequence[float], percentile_value: float) -> float:
    """以线性插值计算小样本百分位数。"""
    if not values:
        raise ValueError("百分位数计算至少需要一个数据点。")
    if not 0 <= percentile_value <= 1:
        raise ValueError("百分位数必须位于 0 到 1。")
    ordered = sorted(values)
    if len(ordered) == 1:
        return round(ordered[0], 3)
    position = percentile_value * (len(ordered) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return round(ordered[lower], 3)
    fraction = position - lower
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * fraction, 3)


def ensure_runtime_directory() -> None:
    """创建靶场唯一的本地运行态目录。"""
    for directory in (RUNTIME_DIR, LOG_FILE.parent, STATE_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def resolved_runtime_path(path: Path, *, allow_root: bool = False) -> Path:
    """确保运行态文件仍位于靶场 runtime 目录内。"""
    runtime_root = RUNTIME_DIR.resolve()
    resolved_path = path.resolve()
    if resolved_path == runtime_root:
        if allow_root:
            return resolved_path
        raise DemoEnvironmentError("拒绝直接访问靶场 runtime 根目录。")
    if runtime_root not in resolved_path.parents:
        raise DemoEnvironmentError("拒绝访问靶场 runtime 目录之外的路径。")
    return resolved_path


def measurement_path(phase: str) -> Path:
    """返回指定测量阶段唯一的持久化路径。"""
    if phase not in {BASELINE_PHASE, DEGRADED_PHASE, RECOVERED_PHASE}:
        raise ValueError(f"不支持的测量阶段：{phase}")
    return resolved_runtime_path(STATE_DIR / f"{phase}.json")


def write_measurement(measurement: ProbeMeasurement) -> None:
    """写入本地、被 Git 忽略的测量结果。"""
    ensure_runtime_directory()
    measurement_path(measurement.phase).write_text(
        json.dumps(asdict(measurement), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def read_measurement(phase: str) -> ProbeMeasurement:
    """读取此前完成的测量阶段。"""
    path = measurement_path(phase)
    if not path.is_file():
        raise DemoEnvironmentError(f"缺少 {phase} 测量结果，请先执行对应阶段。")
    try:
        return ProbeMeasurement(**json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise DemoEnvironmentError(f"测量结果格式无效：{path}") from error


def target_order_rows(order_count: int) -> Iterable[tuple[str, int, str, str, datetime]]:
    """生成固定分布的订单数据；不读取任何已有业务库数据。"""
    statuses = ("paid", "completed", "refunded", "cancelled")
    started_at = datetime(2025, 1, 1, 0, 0, 0)
    for sequence in range(1, order_count + 1):
        yield (
            f"DEMO{sequence:09d}",
            ((sequence - 1) % 128) + 1,
            statuses[sequence % len(statuses)],
            f"{(sequence % 90000) / 100 + 10:.2f}",
            started_at + timedelta(minutes=sequence * 2),
        )


def initialize_database(settings: DatabaseSettings) -> int:
    """在专用库中创建 schema/table、写入确定性种子并确保正常索引存在。"""
    with create_connection(settings) as connection:
        assert_target_database(connection)
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE SCHEMA IF NOT EXISTS {TARGET_SCHEMA}")
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TARGET_SCHEMA}.{TARGET_TABLE} (
                    id BIGSERIAL PRIMARY KEY,
                    order_no VARCHAR(32) NOT NULL UNIQUE,
                    user_id BIGINT NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    total_amount NUMERIC(12, 2) NOT NULL,
                    created_at TIMESTAMP NOT NULL
                )
                """
            )
            cursor.execute(f"SELECT COUNT(*) AS count FROM {TARGET_SCHEMA}.{TARGET_TABLE}")
            existing_count = int(cursor.fetchone()["count"])

        if existing_count:
            if existing_count != settings.order_count:
                raise DemoEnvironmentError(
                    "靶场数据量与当前配置不一致；请先执行 clean 后再 start。"
                )
        else:
            with connection.cursor() as cursor:
                with cursor.copy(
                    f"""
                    COPY {TARGET_SCHEMA}.{TARGET_TABLE}
                    (order_no, user_id, status, total_amount, created_at)
                    FROM STDIN
                    """
                ) as copy:
                    for row in target_order_rows(settings.order_count):
                        copy.write_row(row)

        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {TARGET_INDEX}
                ON {TARGET_SCHEMA}.{TARGET_TABLE} (user_id, created_at)
                """
            )
            cursor.execute(f"ANALYZE {TARGET_SCHEMA}.{TARGET_TABLE}")
        connection.commit()
    return settings.order_count


def index_exists(settings: DatabaseSettings) -> bool:
    """只读取靶场目标索引状态。"""
    with create_connection(settings) as connection:
        assert_target_database(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_indexes
                    WHERE schemaname = %s
                      AND tablename = %s
                      AND indexname = %s
                ) AS exists
                """,
                (TARGET_SCHEMA, TARGET_TABLE, TARGET_INDEX),
            )
            row = cursor.fetchone()
    return bool(row and row["exists"])


def explain_orders_query(settings: DatabaseSettings) -> dict[str, Any]:
    """读取唯一固定订单查询的 JSON 执行计划。"""
    with create_connection(settings) as connection:
        assert_target_database(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                EXPLAIN (FORMAT JSON)
                SELECT id, order_no, status, total_amount, created_at
                FROM {TARGET_SCHEMA}.{TARGET_TABLE}
                WHERE user_id = %s
                  AND created_at >= %s
                  AND created_at < %s
                ORDER BY created_at DESC
                LIMIT 100
                """,
                (TARGET_USER_ID, TARGET_START_AT, TARGET_END_AT),
            )
            row = cursor.fetchone()
    if not row:
        raise DemoEnvironmentError("未获得订单查询执行计划。")
    plan_data = row["QUERY PLAN"]
    if isinstance(plan_data, str):
        plan_data = json.loads(plan_data)
    if not isinstance(plan_data, list) or not plan_data or not isinstance(plan_data[0], dict):
        raise DemoEnvironmentError("订单查询执行计划格式无效。")
    plan = plan_data[0].get("Plan")
    if not isinstance(plan, dict):
        raise DemoEnvironmentError("订单查询执行计划缺少 Plan 节点。")
    return plan


def walk_plan_nodes(plan: dict[str, Any]) -> Iterable[dict[str, Any]]:
    """深度遍历 PostgreSQL JSON 执行计划节点。"""
    yield plan
    children = plan.get("Plans", [])
    if not isinstance(children, list):
        return
    for child in children:
        if isinstance(child, dict):
            yield from walk_plan_nodes(child)


def inspect_plan(settings: DatabaseSettings) -> tuple[list[str], list[str], bool, bool]:
    """将固定计划归纳为节点、索引使用和顺序扫描风险。"""
    plan = explain_orders_query(settings)
    nodes = list(walk_plan_nodes(plan))
    node_types = [str(node.get("Node Type", "unknown")) for node in nodes]
    index_names = [str(node["Index Name"]) for node in nodes if node.get("Index Name")]
    index_used = TARGET_INDEX in index_names
    sequential_scan_risk = any(
        node.get("Node Type") == "Seq Scan" and node.get("Relation Name") == TARGET_TABLE
        for node in nodes
    )
    return node_types, index_names, index_used, sequential_scan_risk


def inject_missing_index(settings: DatabaseSettings) -> None:
    """注入唯一故障：删除专用靶场内固定联合索引。"""
    if not index_exists(settings):
        raise DemoEnvironmentError("目标索引已缺失，拒绝重复注入。")
    with create_connection(settings) as connection:
        assert_target_database(connection)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP INDEX {TARGET_SCHEMA}.{TARGET_INDEX}")
        connection.commit()
    if index_exists(settings):
        raise DemoEnvironmentError("故障注入后目标索引仍存在。")


def repair_index(settings: DatabaseSettings) -> None:
    """恢复唯一允许的修复：重建靶场联合索引。"""
    if index_exists(settings):
        return
    with create_connection(settings) as connection:
        assert_target_database(connection)
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                CREATE INDEX {TARGET_INDEX}
                ON {TARGET_SCHEMA}.{TARGET_TABLE} (user_id, created_at)
                """
            )
        connection.commit()
    if not index_exists(settings):
        raise DemoEnvironmentError("索引恢复后仍未找到目标索引。")


def request_json(
    method: str,
    path: str,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 15,
) -> dict[str, Any]:
    """请求固定订单服务端点并读取 JSON。"""
    encoded_payload = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        f"{SERVICE_URL}{path}",
        data=encoded_payload,
        method=method,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
    except (urllib.error.URLError, TimeoutError) as error:
        raise DemoEnvironmentError(f"本地订单服务不可达：{path}") from error
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as error:
        raise DemoEnvironmentError(f"订单服务返回了非 JSON 内容：{path}") from error
    if not isinstance(result, dict):
        raise DemoEnvironmentError(f"订单服务返回了非对象内容：{path}")
    return result


def port_is_available(port: int) -> bool:
    """检查固定 loopback 端口是否可绑定。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe_socket:
        probe_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe_socket.bind((TARGET_HOST, port))
        except OSError:
            return False
    return True


def read_process_state() -> dict[str, Any] | None:
    """读取此前由本控制脚本创建的本地服务状态。"""
    if not PROCESS_STATE_FILE.is_file():
        return None
    try:
        payload = json.loads(PROCESS_STATE_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise DemoEnvironmentError("订单服务状态文件格式无效。") from error
    if not isinstance(payload, dict):
        raise DemoEnvironmentError("订单服务状态文件不是 JSON 对象。")
    return payload


def service_is_our_instance(state: dict[str, Any]) -> bool:
    """通过实例标识确认响应端确为本控制脚本启动的服务。"""
    try:
        health = request_json("GET", "/health", timeout_seconds=2)
    except DemoEnvironmentError:
        return False
    return health.get("instance_id") == state.get("instance_id")


def start_order_service(settings: DatabaseSettings) -> None:
    """启动仅监听 loopback 的本地订单服务；拒绝抢占未知服务端口。"""
    ensure_runtime_directory()
    state = read_process_state()
    if state and service_is_our_instance(state):
        return
    if state and PROCESS_STATE_FILE.exists():
        PROCESS_STATE_FILE.unlink()
    if not port_is_available(18080):
        raise DemoEnvironmentError("127.0.0.1:18080 已被未知进程占用，拒绝启动靶场服务。")

    instance_id = str(uuid.uuid4())
    environment = os.environ.copy()
    environment.update(
        {
            "OPERMIND_DEMO_PG_HOST": settings.host,
            "OPERMIND_DEMO_PG_PORT": str(settings.port),
            "OPERMIND_DEMO_PG_DATABASE": settings.database,
            "OPERMIND_DEMO_PG_USER": settings.user,
            "OPERMIND_DEMO_PG_PASSWORD": settings.password,
            "OPERMIND_DEMO_ORDER_LOG_PATH": str(LOG_FILE.resolve()),
            "OPERMIND_DEMO_INSTANCE_ID": instance_id,
        }
    )
    creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    with PROCESS_LOG_FILE.open("a", encoding="utf-8") as process_log:
        process = subprocess.Popen(
            [sys.executable, str(SERVICE_FILE)],
            cwd=PROJECT_ROOT,
            env=environment,
            stdout=process_log,
            stderr=subprocess.STDOUT,
            creationflags=creation_flags,
        )
    PROCESS_STATE_FILE.write_text(
        json.dumps({"pid": process.pid, "instance_id": instance_id}, ensure_ascii=False),
        encoding="utf-8",
    )


def wait_for_order_service(timeout_seconds: int = 30) -> None:
    """等待订单服务和靶场表均真正可用。"""
    state = read_process_state()
    if not state:
        raise DemoEnvironmentError("未找到订单服务状态文件。")
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if service_is_our_instance(state):
            return
        time.sleep(0.5)
    raise DemoEnvironmentError("等待订单服务健康检查超时。")


def stop_order_service() -> None:
    """只停止状态文件标记且命令行匹配靶场脚本的本地进程。"""
    state = read_process_state()
    if not state:
        return
    try:
        import psutil

        process = psutil.Process(int(state["pid"]))
        command_line = " ".join(process.cmdline())
        if str(SERVICE_FILE) not in command_line:
            raise DemoEnvironmentError("状态文件 PID 不属于订单靶场服务，拒绝终止。")
        process.terminate()
        try:
            process.wait(timeout=5)
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
    except psutil.NoSuchProcess:
        pass
    finally:
        if PROCESS_STATE_FILE.exists():
            PROCESS_STATE_FILE.unlink()


def reset_metrics() -> None:
    """清空本次阶段的服务测量窗口。"""
    payload = request_json("POST", "/internal/diagnostic/reset")
    if payload.get("window_size") != 0:
        raise DemoEnvironmentError("订单服务未能清空诊断测量窗口。")


def calibrate_slow_threshold(threshold_ms: float) -> float:
    """将慢查询阈值校准到正常基线之上且低于故障判定线。"""
    payload = request_json(
        "POST",
        "/internal/diagnostic/calibrate",
        {"slow_query_threshold_ms": threshold_ms},
    )
    value = payload.get("slow_query_threshold_ms")
    if not isinstance(value, (int, float)):
        raise DemoEnvironmentError("订单服务未返回有效慢查询阈值。")
    return float(value)


def collect_probes(phase: str, sample_count: int) -> ProbeMeasurement:
    """运行固定次数的真实查询探测，并保存 request id 窗口。"""
    if sample_count < 3:
        raise ValueError("探测样本数至少为 3。")
    if phase not in {BASELINE_PHASE, DEGRADED_PHASE, RECOVERED_PHASE}:
        raise ValueError(f"不支持的探测阶段：{phase}")
    reset_metrics()
    records: list[dict[str, Any]] = []
    for _ in range(sample_count):
        payload = request_json("GET", "/orders/diagnostic-probe", timeout_seconds=30)
        required = {"request_id", "query_duration_ms", "slow_query", "timeout"}
        if not required <= payload.keys():
            raise DemoEnvironmentError("订单服务探测响应缺少受控字段。")
        records.append(payload)

    durations = [float(record["query_duration_ms"]) for record in records]
    threshold = float(request_json("GET", "/internal/diagnostic/metrics")["slow_query_threshold_ms"])
    measurement = ProbeMeasurement(
        phase=phase,
        observed_at=utc_now(),
        sample_count=sample_count,
        request_ids=[str(record["request_id"]) for record in records],
        durations_ms=durations,
        p50_ms=percentile(durations, 0.5),
        p95_ms=percentile(durations, 0.95),
        min_ms=round(min(durations), 3),
        max_ms=round(max(durations), 3),
        slow_query_count=sum(bool(record["slow_query"]) for record in records),
        timeout_count=sum(bool(record["timeout"]) for record in records),
        slow_query_threshold_ms=threshold,
    )
    write_measurement(measurement)
    return measurement


def read_matching_logs(request_ids: Iterable[str]) -> list[dict[str, Any]]:
    """仅返回当前 request window 对应的本地 JSONL 日志。"""
    if not LOG_FILE.is_file():
        raise DemoEnvironmentError("订单服务 JSONL 日志不存在。")
    expected_ids = set(request_ids)
    results: list[dict[str, Any]] = []
    for number, line in enumerate(LOG_FILE.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as error:
            raise DemoEnvironmentError(f"订单服务日志第 {number} 行不是合法 JSON。") from error
        if event.get("request_id") in expected_ids:
            results.append(event)
    return results


def evaluate_verification(settings: DatabaseSettings, phase: str) -> VerificationReport:
    """根据数据库计划、服务测量和匹配日志确定故障/恢复是否成立。"""
    if phase not in {DEGRADED_PHASE, RECOVERED_PHASE}:
        raise ValueError("verify 仅支持 degraded 或 recovered 阶段。")
    baseline = read_measurement(BASELINE_PHASE)
    current = read_measurement(phase)
    exists = index_exists(settings)
    node_types, index_names, used, sequential_risk = inspect_plan(settings)
    # 隧道环境的小样本 P95 会受单个网络抖动放大；性能门使用 P50，
    # 并仍要求索引、执行计划和当前请求窗口日志三类独立证据同时成立。
    baseline_p50 = max(baseline.p50_ms, 0.001)
    latency_ratio = round(current.p50_ms / baseline_p50, 3)
    latency_delta = round(current.p50_ms - baseline.p50_ms, 3)
    logs = read_matching_logs(current.request_ids)
    slow_log_count = sum(bool(item.get("slow_query")) for item in logs)
    timeout_log_count = sum(bool(item.get("timeout")) for item in logs)

    if phase == DEGRADED_PHASE:
        checks = {
            "target_index_missing": not exists,
            "plan_not_using_target_index": not used,
            "sequential_scan_risk": sequential_risk,
            "latency_degraded": (
                latency_ratio >= DEGRADATION_RATIO
                and latency_delta >= MIN_DEGRADATION_DELTA_MS
            ),
            "slow_or_timeout_log_present": slow_log_count > 0 or timeout_log_count > 0,
        }
    else:
        checks = {
            "target_index_exists": exists,
            "plan_uses_target_index": used,
            "latency_recovered": latency_ratio <= RECOVERY_RATIO,
            "no_slow_or_timeout_log": slow_log_count == 0 and timeout_log_count == 0,
        }

    return VerificationReport(
        phase=phase,
        passed=all(checks.values()),
        index_exists=exists,
        plan_node_types=node_types,
        plan_index_names=index_names,
        index_used=used,
        sequential_scan_risk=sequential_risk,
        p95_ms=current.p95_ms,
        baseline_p95_ms=baseline.p95_ms,
        p50_ms=current.p50_ms,
        baseline_p50_ms=baseline.p50_ms,
        latency_ratio=latency_ratio,
        latency_delta_ms=latency_delta,
        matching_log_count=len(logs),
        slow_query_log_count=slow_log_count,
        timeout_log_count=timeout_log_count,
        checks=checks,
    )


def clean_target_database(settings: DatabaseSettings) -> None:
    """只删除 opermind_demo 库中的 opermind_demo schema，不影响其他数据库。"""
    with create_connection(settings) as connection:
        assert_target_database(connection)
        with connection.cursor() as cursor:
            cursor.execute(f"DROP SCHEMA IF EXISTS {TARGET_SCHEMA} CASCADE")
        connection.commit()


def print_json(payload: Any) -> None:
    """输出稳定 JSON，供人工演示和 smoke 使用。"""
    if hasattr(payload, "__dataclass_fields__"):
        payload = asdict(payload)
    sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def start_environment(args: argparse.Namespace) -> int:
    """初始化独立数据库、启动订单服务并保存正常基线。"""
    settings = database_settings_from_environment()
    ensure_runtime_directory()
    seeded = initialize_database(settings)
    start_order_service(settings)
    wait_for_order_service(args.startup_timeout_seconds)
    exists = index_exists(settings)
    _, index_names, used, _ = inspect_plan(settings)
    if not exists or not used:
        raise DemoEnvironmentError(
            f"正常基线不成立：index_exists={exists}, plan_indexes={index_names}"
        )
    baseline = collect_probes(BASELINE_PHASE, args.samples)
    slow_threshold = max(baseline.max_ms + 1.0, baseline.p95_ms * 1.1)
    calibrated = calibrate_slow_threshold(round(slow_threshold, 3))
    baseline = collect_probes(BASELINE_PHASE, args.samples)
    print_json(
        {
            "status": "started",
            "database": TARGET_DATABASE,
            "schema": TARGET_SCHEMA,
            "seeded_order_count": seeded,
            "normal_index_exists": exists,
            "normal_plan_indexes": index_names,
            "calibrated_slow_query_threshold_ms": calibrated,
            "baseline": asdict(baseline),
        }
    )
    return 0


def probe_environment(args: argparse.Namespace) -> int:
    """对已启动靶场记录一个固定探测窗口。"""
    measurement = collect_probes(args.phase, args.samples)
    print_json(measurement)
    return 0


def inject_environment(args: argparse.Namespace) -> int:
    """删除唯一目标索引并记录故障窗口。"""
    settings = database_settings_from_environment()
    inject_missing_index(settings)
    measurement = collect_probes(DEGRADED_PHASE, args.samples)
    print_json({"status": "injected", "degraded": asdict(measurement)})
    return 0


def repair_environment(args: argparse.Namespace) -> int:
    """重建唯一目标索引并记录恢复窗口。"""
    settings = database_settings_from_environment()
    repair_index(settings)
    measurement = collect_probes(RECOVERED_PHASE, args.samples)
    print_json({"status": "repaired", "recovered": asdict(measurement)})
    return 0


def verify_environment(args: argparse.Namespace) -> int:
    """按固定证据规则验证故障或恢复阶段。"""
    settings = database_settings_from_environment()
    report = evaluate_verification(settings, args.phase)
    print_json(report)
    return 0 if report.passed else 2


def clean_environment(_args: argparse.Namespace) -> int:
    """停止靶场服务并删除目标 schema 与本地运行态。"""
    settings = database_settings_from_environment()
    stop_order_service()
    clean_target_database(settings)
    if RUNTIME_DIR.exists():
        resolved_runtime = resolved_runtime_path(RUNTIME_DIR, allow_root=True)
        for child in resolved_runtime.iterdir():
            if child.is_dir():
                import shutil

                shutil.rmtree(child)
            else:
                child.unlink()
        resolved_runtime.rmdir()
    print_json({"status": "cleaned", "database": TARGET_DATABASE, "schema": TARGET_SCHEMA})
    return 0


def build_parser() -> argparse.ArgumentParser:
    """构造固定的 Work 1 控制命令。"""
    parser = argparse.ArgumentParser(description="OperMind PostgreSQL 订单慢 SQL 受控靶场")
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="初始化靶场、启动服务并写入正常基线")
    start.add_argument("--samples", type=int, default=12, help="每阶段的探测次数，至少为 3")
    start.add_argument("--startup-timeout-seconds", type=int, default=30)
    start.set_defaults(handler=start_environment)

    probe = subparsers.add_parser("probe", help="记录已启动靶场的固定探测窗口")
    probe.add_argument("--phase", choices=(BASELINE_PHASE, DEGRADED_PHASE, RECOVERED_PHASE), required=True)
    probe.add_argument("--samples", type=int, default=12)
    probe.set_defaults(handler=probe_environment)

    inject = subparsers.add_parser("inject", help="删除固定联合索引并记录故障窗口")
    inject.add_argument("--samples", type=int, default=12)
    inject.set_defaults(handler=inject_environment)

    repair = subparsers.add_parser("repair", help="重建固定联合索引并记录恢复窗口")
    repair.add_argument("--samples", type=int, default=12)
    repair.set_defaults(handler=repair_environment)

    verify = subparsers.add_parser("verify", help="验证故障或恢复证据")
    verify.add_argument("--phase", choices=(DEGRADED_PHASE, RECOVERED_PHASE), required=True)
    verify.set_defaults(handler=verify_environment)

    clean = subparsers.add_parser("clean", help="停止服务并删除靶场 schema")
    clean.set_defaults(handler=clean_environment)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """运行控制命令并以稳定退出码表达结果。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (DemoEnvironmentError, ValueError, psycopg.Error) as error:
        sys.stderr.write(f"ERROR: {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
