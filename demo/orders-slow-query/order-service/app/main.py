"""本地 PostgreSQL 订单慢 SQL 靶场服务。"""

from __future__ import annotations

import json
import logging
import os
import statistics
import time
import uuid
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import psycopg
from fastapi import FastAPI, HTTPException
from psycopg.rows import dict_row
from pydantic import BaseModel, Field


LOGGER = logging.getLogger(__name__)
TARGET_HOST = "127.0.0.1"
TARGET_PORT = 5433
TARGET_DATABASE = "opermind_demo"
TARGET_SCHEMA = "opermind_demo"
TARGET_TABLE = "orders"
DEMO_ROOT = Path(__file__).resolve().parents[2]
ALLOWED_LOG_DIRECTORY = (DEMO_ROOT / "runtime" / "logs").resolve()


@dataclass(frozen=True)
class ServiceSettings:
    """订单靶场服务固定使用的 PostgreSQL 隧道配置。"""

    host: str
    port: int
    database: str
    user: str
    password: str
    probe_user_id: int
    probe_start_at: str
    probe_end_at: str
    timeout_threshold_ms: float
    log_path: Path
    instance_id: str

    @classmethod
    def from_environment(cls) -> "ServiceSettings":
        """读取并严格校验本地靶场配置。"""
        host = os.environ.get("OPERMIND_DEMO_PG_HOST", TARGET_HOST)
        port = int(os.environ.get("OPERMIND_DEMO_PG_PORT", str(TARGET_PORT)))
        database = os.environ.get("OPERMIND_DEMO_PG_DATABASE", TARGET_DATABASE)
        if host != TARGET_HOST or port != TARGET_PORT or database != TARGET_DATABASE:
            raise RuntimeError(
                "订单靶场只允许访问 127.0.0.1:5433 上的 opermind_demo 数据库。"
            )

        password = os.environ.get("OPERMIND_DEMO_PG_PASSWORD")
        user = os.environ.get("OPERMIND_DEMO_PG_USER")
        if not password or not user:
            raise RuntimeError("缺少本地靶场 PostgreSQL 用户名或密码环境变量。")

        return cls(
            host=host,
            port=port,
            database=database,
            user=user,
            password=password,
            probe_user_id=int(os.environ.get("OPERMIND_DEMO_PROBE_USER_ID", "42")),
            probe_start_at=os.environ.get(
                "OPERMIND_DEMO_PROBE_START_AT", "2025-01-01 00:00:00"
            ),
            probe_end_at=os.environ.get(
                "OPERMIND_DEMO_PROBE_END_AT", "2026-01-01 00:00:00"
            ),
            timeout_threshold_ms=float(
                os.environ.get("OPERMIND_DEMO_TIMEOUT_THRESHOLD_MS", "120")
            ),
            log_path=cls._validated_log_path(),
            instance_id=os.environ.get("OPERMIND_DEMO_INSTANCE_ID", "unmanaged"),
        )

    @staticmethod
    def _validated_log_path() -> Path:
        """只允许订单服务将本地日志写入自己的靶场 runtime 目录。"""
        configured = os.environ.get(
            "OPERMIND_DEMO_ORDER_LOG_PATH",
            str(ALLOWED_LOG_DIRECTORY / "order-service.jsonl"),
        )
        log_path = Path(configured).resolve()
        if log_path.parent != ALLOWED_LOG_DIRECTORY:
            raise RuntimeError("订单靶场日志只能写入 demo/orders-slow-query/runtime/logs。")
        return log_path

class ProbeRecord(BaseModel):
    """固定订单查询的一条真实测量记录。"""

    request_id: str
    observed_at: str
    query_duration_ms: float
    result_count: int
    slow_query: bool
    timeout: bool


class CalibrationRequest(BaseModel):
    """控制脚本写入的故障窗口慢查询阈值。"""

    slow_query_threshold_ms: float = Field(gt=0, le=60_000)


SETTINGS = ServiceSettings.from_environment()
METRIC_LOCK = Lock()
LOG_LOCK = Lock()
THRESHOLD_LOCK = Lock()
RECENT_PROBES: deque[ProbeRecord] = deque(maxlen=200)
SLOW_QUERY_THRESHOLD_MS = float(
    os.environ.get("OPERMIND_DEMO_SLOW_QUERY_THRESHOLD_MS", "60000")
)

app = FastAPI(title="OperMind PostgreSQL Orders Slow Query Target", version="1.0.0")


def utc_now() -> str:
    """返回可审计的 UTC 时间。"""
    return datetime.now(timezone.utc).isoformat()


def create_connection() -> psycopg.Connection[dict[str, Any]]:
    """建立只访问独立靶场数据库的短连接。"""
    return psycopg.connect(
        host=SETTINGS.host,
        port=SETTINGS.port,
        dbname=SETTINGS.database,
        user=SETTINGS.user,
        password=SETTINGS.password,
        connect_timeout=3,
        options="-c statement_timeout=10000",
        row_factory=dict_row,
    )


def current_slow_query_threshold_ms() -> float:
    """读取可由控制脚本校准的慢查询阈值。"""
    with THRESHOLD_LOCK:
        return SLOW_QUERY_THRESHOLD_MS


def write_log(event: dict[str, Any]) -> None:
    """向本地 runtime 目录追加不含凭证的 JSONL 事件。"""
    SETTINGS.log_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    with LOG_LOCK:
        with SETTINGS.log_path.open("a", encoding="utf-8") as log_file:
            log_file.write(f"{serialized}\n")


def percentile_95(values: list[float]) -> float | None:
    """计算小样本线性插值 P95。"""
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 3)
    ordered = sorted(values)
    position = 0.95 * (len(ordered) - 1)
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return round(ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower), 3)


def probe_orders() -> ProbeRecord:
    """执行唯一允许的真实订单查询，不接收外部 SQL 或表名。"""
    request_id = str(uuid.uuid4())
    try:
        with create_connection() as connection:
            with connection.cursor() as cursor:
                started = time.perf_counter()
                cursor.execute(
                    """
                    SELECT id, order_no, status, total_amount, created_at
                    FROM opermind_demo.orders
                    WHERE user_id = %s
                      AND created_at >= %s
                      AND created_at < %s
                    ORDER BY created_at DESC
                    LIMIT 100
                    """,
                    (
                        SETTINGS.probe_user_id,
                        SETTINGS.probe_start_at,
                        SETTINGS.probe_end_at,
                    ),
                )
                rows = cursor.fetchall()
                duration_ms = round((time.perf_counter() - started) * 1000, 3)
    except psycopg.Error as error:
        write_log(
            {
                "timestamp": utc_now(),
                "event": "order_query_failed",
                "request_id": request_id,
                "route": "/orders/diagnostic-probe",
                "error_type": type(error).__name__,
            }
        )
        raise HTTPException(status_code=503, detail="订单靶场数据库不可用") from error

    threshold = current_slow_query_threshold_ms()
    record = ProbeRecord(
        request_id=request_id,
        observed_at=utc_now(),
        query_duration_ms=duration_ms,
        result_count=len(rows),
        slow_query=duration_ms >= threshold,
        timeout=duration_ms >= SETTINGS.timeout_threshold_ms,
    )
    with METRIC_LOCK:
        RECENT_PROBES.append(record)
    write_log(
        {
            "timestamp": record.observed_at,
            "event": "order_query",
            "request_id": record.request_id,
            "route": "/orders/diagnostic-probe",
            "status_code": 200,
            "query_duration_ms": record.query_duration_ms,
            "result_count": record.result_count,
            "slow_query": record.slow_query,
            "timeout": record.timeout,
            "slow_query_threshold_ms": threshold,
        }
    )
    return record


@app.get("/health")
def health() -> dict[str, str]:
    """确认服务只连到了目标数据库且目标表可读。"""
    try:
        with create_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT current_database() AS database_name,
                           to_regclass('opermind_demo.orders') IS NOT NULL AS orders_exists
                    """
                )
                row = cursor.fetchone()
    except psycopg.Error as error:
        raise HTTPException(status_code=503, detail="订单靶场数据库不可用") from error

    if not row or row["database_name"] != TARGET_DATABASE or not row["orders_exists"]:
        raise HTTPException(status_code=503, detail="订单靶场目标未初始化")
    return {
        "status": "ok",
        "service": "order-service",
        "database": TARGET_DATABASE,
        "instance_id": SETTINGS.instance_id,
    }


@app.get("/orders/diagnostic-probe", response_model=ProbeRecord)
def diagnostic_probe() -> ProbeRecord:
    """执行固定订单查询。"""
    return probe_orders()


@app.get("/internal/diagnostic/metrics")
def diagnostic_metrics() -> dict[str, Any]:
    """返回当前进程内的只读探测窗口。"""
    with METRIC_LOCK:
        records = list(RECENT_PROBES)
    durations = [record.query_duration_ms for record in records]
    return {
        "window_size": len(records),
        "p50_ms": round(statistics.median(durations), 3) if durations else None,
        "p95_ms": percentile_95(durations),
        "slow_query_count": sum(record.slow_query for record in records),
        "timeout_count": sum(record.timeout for record in records),
        "latest_request_id": records[-1].request_id if records else None,
        "slow_query_threshold_ms": current_slow_query_threshold_ms(),
    }


@app.post("/internal/diagnostic/reset")
def reset_diagnostic_metrics() -> dict[str, int]:
    """清空当前靶场测量窗口。"""
    with METRIC_LOCK:
        RECENT_PROBES.clear()
    return {"window_size": 0}


@app.post("/internal/diagnostic/calibrate")
def calibrate_slow_query_threshold(payload: CalibrationRequest) -> dict[str, float]:
    """由本地控制脚本在正常基线后校准故障判定阈值。"""
    global SLOW_QUERY_THRESHOLD_MS
    with THRESHOLD_LOCK:
        SLOW_QUERY_THRESHOLD_MS = round(payload.slow_query_threshold_ms, 3)
    LOGGER.info("订单靶场慢查询阈值已校准为 %s ms", SLOW_QUERY_THRESHOLD_MS)
    return {"slow_query_threshold_ms": SLOW_QUERY_THRESHOLD_MS}


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    uvicorn.run(app, host="127.0.0.1", port=18080, log_level="warning")
