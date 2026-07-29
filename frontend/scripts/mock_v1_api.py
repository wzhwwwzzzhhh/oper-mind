"""P3.4c 本地 mock FastAPI：以进程内确定性状态验收 P2 Run 与 SSE 契约。"""

from __future__ import annotations

import json
import os
from collections.abc import Iterator, Mapping
from typing import Any
from uuid import UUID, uuid5

import uvicorn
from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse

APP_NAME = "OperMind P3.4c Mock API"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8100
TRACE_ID = "55555555-5555-4555-8555-555555555555"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
ARCHIVED_SESSION_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"
ARCHIVED_RUN_ID = "44444444-4444-4444-8444-444444444443"
FAILED_RUN_ID = "55555555-5555-4555-8555-555555555554"
CANCELLED_RUN_ID = "66666666-6666-4666-8666-666666666665"
EMPTY_RESULT_RUN_ID = "77777777-7777-4777-8777-777777777771"
PROTOCOL_ERROR_RUN_ID = "88888888-8888-4888-8888-888888888885"
P3_4C_NAMESPACE = UUID("f0000000-0000-4000-8000-000000000001")
MISMATCH_RUN_ID = "44444444-4444-4444-8444-444444444444"

ACTIVE_SESSION: dict[str, object] = {
    "id": SESSION_ID,
    "title": "Nginx 5xx 排查",
    "status": "active",
    "environment_id": None,
    "incident_id": None,
    "created_at": "2026-07-27T01:00:00.000Z",
    "updated_at": "2026-07-27T01:02:00.000Z",
    "archived_at": None,
}
ARCHIVED_SESSION: dict[str, object] = {
    **ACTIVE_SESSION,
    "id": ARCHIVED_SESSION_ID,
    "title": "已归档的历史会话",
    "status": "archived",
    "archived_at": "2026-07-27T01:03:00.000Z",
}
PAGED_ACTIVE_SESSION: dict[str, object] = {
    **ACTIVE_SESSION,
    "id": "99999999-9999-4999-8999-999999999999",
    "title": "第二页的活跃会话",
    "updated_at": "2026-07-27T01:01:00.000Z",
}
def _structured_result(run_id: str, created_at: str, summary: str = "Nginx 上游连接池已耗尽。") -> dict[str, object]:
    """构造完整 P2 DiagnosisResult 夹具；仅用于离线确定性契约验收。"""
    return {
        "id": str(uuid5(P3_4C_NAMESPACE, f"result:{run_id}")),
        "run_id": run_id,
        "summary": summary,
        "severity": "high",
        "confidence": 0.92,
        "root_causes": [
            {
                "id": str(uuid5(P3_4C_NAMESPACE, f"root-cause:{run_id}")),
                "title": "上游连接池不足",
                "summary": "连接池长期耗尽，导致 Nginx 无法建立新的上游连接。",
                "confidence": 0.88,
                "evidence_ids": [str(uuid5(P3_4C_NAMESPACE, f"evidence:{run_id}"))],
            }
        ],
        "evidence": [
            {
                "id": str(uuid5(P3_4C_NAMESPACE, f"evidence:{run_id}")),
                "source_type": "log",
                "source_name": "nginx-access",
                "title": "Nginx 错误日志",
                "summary": "上游连接池耗尽。",
                "locator": "nginx/upstream",
                "observed_at": created_at,
                "attributes": {"active_connections": 120, "saturation": 0.98, "healthy": False, "note": None},
            }
        ],
        "impact": {
            "summary": "支付入口请求出现 5xx。",
            "affected_services": ["gateway", "payment-api"],
            "affected_scope": "支付入口",
        },
        "recommendations": [
            {
                "id": str(uuid5(P3_4C_NAMESPACE, f"recommendation:{run_id}")),
                "title": "分批扩容上游连接池",
                "description": "在受控窗口内逐步提高连接池上限，并观察错误率。",
                "priority": "p1",
                "risk_level": "medium",
                "requires_approval": True,
                "evidence_ids": [str(uuid5(P3_4C_NAMESPACE, f"evidence:{run_id}"))],
            }
        ],
        "risks": [
            {
                "id": str(uuid5(P3_4C_NAMESPACE, f"risk:{run_id}")),
                "level": "medium",
                "summary": "连接池上限调整可能增加后端连接压力。",
                "mitigation": "分批调整并回滚异常实例。",
            }
        ],
        "requires_approval": True,
        "agent_summary": [
            {
                "agent": "server",
                "status": "completed",
                "summary": "已完成服务侧连接池诊断。",
                "duration_ms": 120,
            }
        ],
        "report_markdown": "# Mock 结果补充\n\n该字段仅用于契约覆盖，P3 不渲染。",
        "created_at": created_at,
    }


RUN: dict[str, object] = {
    "id": RUN_ID,
    "session_id": SESSION_ID,
    "trace_id": TRACE_ID,
    "input_message_id": "66666666-6666-4666-8666-666666666666",
    "status": "succeeded",
    "result": _structured_result(RUN_ID, "2026-07-27T01:00:33.000Z"),
    "error": None,
    "created_at": "2026-07-27T01:00:30.000Z",
    "started_at": "2026-07-27T01:00:31.000Z",
    "finished_at": "2026-07-27T01:00:33.000Z",
}
ARCHIVED_RUN: dict[str, object] = {
    **RUN,
    "id": ARCHIVED_RUN_ID,
    "session_id": ARCHIVED_SESSION_ID,
    "trace_id": "44444444-4444-4444-8444-444444444442",
    "result": _structured_result(ARCHIVED_RUN_ID, "2026-07-27T01:03:00.000Z", "已归档会话的历史诊断结果。"),
}
FAILED_RUN: dict[str, object] = {
    **RUN,
    "id": FAILED_RUN_ID,
    "status": "failed",
    "result": None,
    "error": {"code": "TOOL_TIMEOUT", "message": "上游日志查询超时。"},
    "created_at": "2026-07-27T01:01:00.000Z",
    "started_at": "2026-07-27T01:01:01.000Z",
    "finished_at": "2026-07-27T01:01:02.000Z",
}
CANCELLED_RUN: dict[str, object] = {
    **RUN,
    "id": CANCELLED_RUN_ID,
    "status": "cancelled",
    "result": None,
    "error": None,
    "created_at": "2026-07-27T01:02:00.000Z",
    "started_at": "2026-07-27T01:02:01.000Z",
    "finished_at": "2026-07-27T01:02:02.000Z",
}
EMPTY_RESULT_RUN: dict[str, object] = {
    **RUN,
    "id": EMPTY_RESULT_RUN_ID,
    "result": {
        **_structured_result(EMPTY_RESULT_RUN_ID, "2026-07-27T01:03:03.000Z", "服务返回了完整但为空的结构化结果。"),
        "root_causes": [],
        "evidence": [],
        "impact": None,
        "recommendations": [],
        "risks": [],
        "requires_approval": False,
        "agent_summary": [],
        "report_markdown": None,
    },
    "created_at": "2026-07-27T01:03:00.000Z",
    "started_at": "2026-07-27T01:03:01.000Z",
    "finished_at": "2026-07-27T01:03:03.000Z",
}
PROTOCOL_ERROR_RUN: dict[str, object] = {
    **RUN,
    "id": PROTOCOL_ERROR_RUN_ID,
    "result": {
        key: value
        for key, value in _structured_result(PROTOCOL_ERROR_RUN_ID, "2026-07-27T01:04:03.000Z").items()
        if key != "created_at"
    },
    "created_at": "2026-07-27T01:04:00.000Z",
    "started_at": "2026-07-27T01:04:01.000Z",
    "finished_at": "2026-07-27T01:04:03.000Z",
}
STATIC_RUN_EVENTS: tuple[dict[str, object], ...] = (
    {
        "id": "10000000-0000-4000-8000-000000000001",
        "run_id": RUN_ID,
        "sequence": 1,
        "type": "run_queued",
        "occurred_at": "2026-07-27T01:00:30.000Z",
        "data": {"summary": "诊断请求已持久化并进入队列。"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000002",
        "run_id": RUN_ID,
        "sequence": 2,
        "type": "run_started",
        "occurred_at": "2026-07-27T01:00:31.000Z",
        "data": {"summary": "诊断任务已开始执行。"},
    },
    {
        "id": "10000000-0000-4000-8000-000000000003",
        "run_id": RUN_ID,
        "sequence": 3,
        "type": "run_succeeded",
        "occurred_at": "2026-07-27T01:00:33.000Z",
        "data": {"summary": "诊断任务已完成。"},
    },
)

REQUEST_LOG: list[dict[str, str]] = []
ACCEPTED_RUNS: dict[str, dict[str, object]] = {}
IDEMPOTENCY_RECORDS: dict[str, dict[str, str]] = {}
ACCEPTED_EVENT_COUNTS: dict[str, int] = {}
app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)


def clear_request_log() -> None:
    """清空进程内验收日志，仅供本地测试调用。"""
    REQUEST_LOG.clear()


def reset_mock_state() -> None:
    """重置 P3.4c Run 受理和 SSE 进度，避免测试相互污染。"""
    clear_request_log()
    ACCEPTED_RUNS.clear()
    IDEMPOTENCY_RECORDS.clear()
    ACCEPTED_EVENT_COUNTS.clear()


def _response_mode() -> str:
    """读取本地验收模式；默认返回确定性资源。"""
    return os.getenv("OPERMIND_MOCK_API_MODE", "success")


def _request_id(request: Request) -> str:
    """回显前端传入的关联 ID；缺失时保留明显的测试标识。"""
    return request.headers.get("X-Request-Id", "missing-client-request-id")


def _record(request: Request) -> None:
    """记录 mock 收到的 v1 请求，供测试与人工验收核对。"""
    REQUEST_LOG.append(
        {
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "request_id": _request_id(request),
        }
    )


def _response(
    request: Request,
    body: Mapping[str, object],
    status_code: int = 200,
    trace_id: str = TRACE_ID,
) -> JSONResponse:
    """返回 P2 JSON envelope 以及与 meta 一致的关联响应头。"""
    _record(request)
    request_id = _request_id(request)
    return JSONResponse(
        content={**body, "meta": {"request_id": request_id, "trace_id": trace_id}},
        status_code=status_code,
        headers={"X-Request-Id": request_id, "X-Trace-Id": trace_id},
    )


def _run_response(request: Request, run: Mapping[str, object], status_code: int = 200) -> JSONResponse:
    """返回包含 Run trace_id 的 P2 Run envelope。"""
    _record(request)
    request_id = _request_id(request)
    trace_id = str(run["trace_id"])
    return JSONResponse(
        content={"run": run, "meta": {"request_id": request_id, "trace_id": trace_id}},
        status_code=status_code,
        headers={"X-Request-Id": request_id, "X-Trace-Id": trace_id},
    )


def _error(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    """返回与 P2 一致的安全错误资源，不泄露实现或连接信息。"""
    return _response(
        request,
        {"error": {"code": code, "message": message, "details": None}},
        status_code,
    )


def _normalize_query(value: object) -> str | None:
    """模拟 P2 请求语义指纹使用的最小 query 规范化。"""
    if not isinstance(value, str):
        return None
    normalized = " ".join(value.split())
    return normalized or None


def _accepted_run_identity(idempotency_key: str) -> tuple[str, str, str]:
    """由幂等键稳定派生 mock Run、trace 与输入 Message 标识。"""
    return (
        str(uuid5(P3_4C_NAMESPACE, f"run:{idempotency_key}")),
        str(uuid5(P3_4C_NAMESPACE, f"trace:{idempotency_key}")),
        str(uuid5(P3_4C_NAMESPACE, f"message:{idempotency_key}")),
    )


def _accepted_events(run_id: str) -> tuple[dict[str, object], ...]:
    """为新受理 Run 生成固定 sequence 的持久化事件计划。"""
    return (
        {
            "id": str(uuid5(P3_4C_NAMESPACE, f"event:{run_id}:1")),
            "run_id": run_id,
            "sequence": 1,
            "type": "run_queued",
            "occurred_at": "2026-07-28T06:00:00.000Z",
            "data": {"summary": "诊断请求已持久化并进入队列。"},
        },
        {
            "id": str(uuid5(P3_4C_NAMESPACE, f"event:{run_id}:2")),
            "run_id": run_id,
            "sequence": 2,
            "type": "run_started",
            "occurred_at": "2026-07-28T06:00:01.000Z",
            "data": {"summary": "诊断任务已开始执行。"},
        },
        {
            "id": str(uuid5(P3_4C_NAMESPACE, f"event:{run_id}:3")),
            "run_id": run_id,
            "sequence": 3,
            "type": "run_succeeded",
            "occurred_at": "2026-07-28T06:00:02.000Z",
            "data": {"summary": "诊断任务已完成。"},
        },
    )


def _find_run(run_id: str) -> dict[str, object] | None:
    """按 ID 读取静态或本次受理的 mock Run。"""
    if run_id == RUN_ID:
        return RUN
    if run_id == ARCHIVED_RUN_ID:
        return ARCHIVED_RUN
    if run_id == FAILED_RUN_ID:
        return FAILED_RUN
    if run_id == CANCELLED_RUN_ID:
        return CANCELLED_RUN
    if run_id == EMPTY_RESULT_RUN_ID:
        return EMPTY_RESULT_RUN
    if run_id == PROTOCOL_ERROR_RUN_ID:
        return PROTOCOL_ERROR_RUN
    return ACCEPTED_RUNS.get(run_id)


def _available_events(run_id: str) -> tuple[dict[str, object], ...] | None:
    """只返回当前已持久化、可由 REST 安全读取的事件。"""
    if run_id == RUN_ID:
        return STATIC_RUN_EVENTS
    if run_id in {ARCHIVED_RUN_ID, FAILED_RUN_ID, CANCELLED_RUN_ID, EMPTY_RESULT_RUN_ID, PROTOCOL_ERROR_RUN_ID}:
        return ()
    if run_id not in ACCEPTED_RUNS:
        return None
    return _accepted_events(run_id)[: ACCEPTED_EVENT_COUNTS.get(run_id, 1)]


def _all_stream_events(run_id: str) -> tuple[dict[str, object], ...] | None:
    """返回 SSE 可按 sequence 重放的有限持久化事件计划。"""
    if run_id == RUN_ID:
        return STATIC_RUN_EVENTS
    if run_id in {ARCHIVED_RUN_ID, FAILED_RUN_ID, CANCELLED_RUN_ID, EMPTY_RESULT_RUN_ID, PROTOCOL_ERROR_RUN_ID}:
        return ()
    if run_id in ACCEPTED_RUNS:
        return _accepted_events(run_id)
    return None


def _mark_event_persisted(run_id: str, event: Mapping[str, object]) -> None:
    """在 SSE 发出前推进确定性 Run 状态，保持 REST 恢复与终态一致。"""
    if run_id not in ACCEPTED_RUNS:
        return
    sequence = int(event["sequence"])
    ACCEPTED_EVENT_COUNTS[run_id] = max(ACCEPTED_EVENT_COUNTS.get(run_id, 1), sequence)
    run = ACCEPTED_RUNS[run_id]
    if sequence == 2:
        run["status"] = "running"
        run["started_at"] = str(event["occurred_at"])
    if sequence == 3:
        run["status"] = "succeeded"
        run["finished_at"] = str(event["occurred_at"])
        run["result"] = _structured_result(
            run_id,
            str(event["occurred_at"]),
            "Mock 诊断已完成。",
        )


def _parse_event_cursor(value: str | None) -> int | None:
    """解析 Last-Event-ID 或 after_sequence，允许 0 表示最早事件。"""
    if value is None:
        return None
    if not value.isdecimal():
        raise ValueError("事件游标无效")
    return int(value)


def _sse_frame(sequence: int, event: Mapping[str, object], request_id: str, trace_id: str) -> str:
    """序列化 P2 规定的 id/run_event/data SSE 帧。"""
    payload = {
        "event": event,
        "meta": {"request_id": request_id, "trace_id": trace_id},
    }
    return f"id: {sequence}\nevent: run_event\ndata: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"


def _replay_events(run_id: str, after_sequence: int, request_id: str, trace_id: str) -> Iterator[str]:
    """重放 sequence 更大的持久化事件；终态帧发送后自然结束生成器。"""
    events = _all_stream_events(run_id)
    if events is None:
        return
    for event in events:
        sequence = int(event["sequence"])
        if sequence <= after_sequence:
            continue
        _mark_event_persisted(run_id, event)
        yield _sse_frame(sequence, event, request_id, trace_id)
        if event["type"] in {"run_succeeded", "run_failed", "run_cancelled"}:
            return


@app.get("/health")
def health() -> dict[str, str]:
    """暴露 mock 进程自身的最小健康检查。"""
    return {"status": "ok", "service": "p3.3c-mock-api"}


@app.get("/api/v1/sessions")
def list_sessions(request: Request, cursor: str | None = None, limit: int = 20) -> JSONResponse:
    """模拟 active Session 列表与不透明 cursor。"""
    del limit
    if _response_mode() == "internal_error":
        return _error(request, "INTERNAL_ERROR", "服务内部错误，请稍后重试", 500)
    if cursor == "session-page-2":
        return _response(request, {"items": [PAGED_ACTIVE_SESSION], "page": {"next_cursor": None, "has_more": False}})
    if cursor == "empty-page":
        return _response(request, {"items": [], "page": {"next_cursor": None, "has_more": False}})
    return _response(request, {"items": [ACTIVE_SESSION], "page": {"next_cursor": "session-page-2", "has_more": True}})


@app.get("/api/v1/sessions/{session_id}")
def get_session(request: Request, session_id: str) -> JSONResponse:
    """读取活跃或归档 Session；其他 ID 返回安全 404。"""
    if session_id == SESSION_ID:
        return _response(request, {"session": ACTIVE_SESSION})
    if session_id == ARCHIVED_SESSION_ID:
        return _response(request, {"session": ARCHIVED_SESSION})
    return _error(request, "SESSION_NOT_FOUND", "会话不存在", 404)


@app.get("/api/v1/sessions/{session_id}/runs")
def list_session_runs(request: Request, session_id: str, cursor: str | None = None, limit: int = 20) -> JSONResponse:
    """读取当前 Session 的 Run 历史和 cursor 页面。"""
    del limit
    if session_id == ARCHIVED_SESSION_ID:
        return _response(request, {"items": [ARCHIVED_RUN], "page": {"next_cursor": None, "has_more": False}})
    if session_id != SESSION_ID:
        return _error(request, "SESSION_NOT_FOUND", "会话不存在", 404)
    if cursor == "run-page-2":
        return _response(request, {"items": [], "page": {"next_cursor": None, "has_more": False}})
    return _response(
        request,
        {"items": [*ACCEPTED_RUNS.values(), RUN, EMPTY_RESULT_RUN, PROTOCOL_ERROR_RUN, FAILED_RUN, CANCELLED_RUN], "page": {"next_cursor": "run-page-2", "has_more": True}},
    )


@app.post("/api/v1/sessions/{session_id}/runs")
async def create_run(
    request: Request,
    session_id: str,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> JSONResponse:
    """模拟 P2 原子受理、同 key 重放和冲突保护，不启动真实 Agent。"""
    if session_id != SESSION_ID:
        if session_id == ARCHIVED_SESSION_ID:
            return _error(request, "SESSION_ARCHIVED", "会话已归档", 409)
        return _error(request, "SESSION_NOT_FOUND", "会话不存在", 404)
    if idempotency_key is None:
        return _error(request, "VALIDATION_ERROR", "请求参数不合法", 422)
    try:
        UUID(idempotency_key)
    except ValueError:
        return _error(request, "VALIDATION_ERROR", "请求参数不合法", 422)

    try:
        payload = await request.json()
    except json.JSONDecodeError:
        return _error(request, "VALIDATION_ERROR", "请求参数不合法", 422)
    query = _normalize_query(payload.get("query") if isinstance(payload, Mapping) else None)
    if query is None:
        return _error(request, "VALIDATION_ERROR", "请求参数不合法", 422)

    existing = IDEMPOTENCY_RECORDS.get(idempotency_key)
    if existing is not None:
        if existing["query"] != query:
            return _error(request, "IDEMPOTENCY_KEY_REUSED", "幂等键已用于不同请求", 409)
        return _run_response(request, ACCEPTED_RUNS[existing["run_id"]], status_code=202)

    run_id, trace_id, input_message_id = _accepted_run_identity(idempotency_key)
    run = {
        "id": run_id,
        "session_id": SESSION_ID,
        "trace_id": trace_id,
        "input_message_id": input_message_id,
        "status": "queued",
        "result": None,
        "error": None,
        "created_at": "2026-07-28T06:00:00.000Z",
        "started_at": None,
        "finished_at": None,
    }
    ACCEPTED_RUNS[run_id] = run
    IDEMPOTENCY_RECORDS[idempotency_key] = {"query": query, "run_id": run_id}
    ACCEPTED_EVENT_COUNTS[run_id] = 1
    return _run_response(request, run, status_code=202)


@app.get("/api/v1/sessions/{session_id}/messages")
def list_session_messages(request: Request, session_id: str, cursor: str | None = None, limit: int = 20) -> JSONResponse:
    """读取当前 Session 的消息历史和 cursor 页面。"""
    del limit
    if session_id == ARCHIVED_SESSION_ID:
        return _response(request, {"items": [], "page": {"next_cursor": None, "has_more": False}})
    if session_id != SESSION_ID:
        return _error(request, "SESSION_NOT_FOUND", "会话不存在", 404)
    if cursor == "message-page-2":
        return _response(
            request,
            {
                "items": [
                    {
                        "id": "88888888-8888-4888-8888-888888888888",
                        "session_id": SESSION_ID,
                        "run_id": RUN_ID,
                        "role": "assistant",
                        "content": "诊断已完成。",
                        "created_at": "2026-07-27T01:00:34.000Z",
                    }
                ],
                "page": {"next_cursor": None, "has_more": False},
            },
        )
    return _response(
        request,
        {
            "items": [
                {
                    "id": "66666666-6666-4666-8666-666666666666",
                    "session_id": SESSION_ID,
                    "run_id": None,
                    "role": "user",
                    "content": "请检查 Nginx 5xx。",
                    "created_at": "2026-07-27T01:00:00.000Z",
                }
            ],
            "page": {"next_cursor": "message-page-2", "has_more": True},
        },
    )


@app.get("/api/v1/runs/{run_id}/events")
def list_run_events(request: Request, run_id: str, cursor: str | None = None, limit: int = 20) -> JSONResponse:
    """按 sequence 正序读取已持久化 RunEvent，并使用 mock 的不透明 cursor。"""
    del limit
    run = _find_run(run_id)
    events = _available_events(run_id)
    if run is None or events is None:
        return _error(request, "RUN_NOT_FOUND", "诊断运行不存在", 404)
    if cursor not in {None, "event-page-2"}:
        return _error(request, "INVALID_CURSOR", "分页游标无效", 400)
    items = list(events[1:] if cursor == "event-page-2" else events[:1])
    has_more = cursor is None and len(events) > 1
    return _response(
        request,
        {"items": items, "page": {"next_cursor": "event-page-2" if has_more else None, "has_more": has_more}},
        trace_id=str(run["trace_id"]),
    )


@app.get("/api/v1/runs/{run_id}/stream", response_model=None)
def stream_run_events(
    request: Request,
    run_id: str,
    after_sequence: str | None = None,
    last_event_id: str | None = Header(default=None, alias="Last-Event-ID"),
) -> StreamingResponse | JSONResponse:
    """重放有限持久化事件，支持 Last-Event-ID 续传并在终态帧后关闭。"""
    run = _find_run(run_id)
    events = _all_stream_events(run_id)
    if run is None or events is None:
        return _error(request, "RUN_NOT_FOUND", "诊断运行不存在", 404)
    try:
        header_cursor = _parse_event_cursor(last_event_id)
        query_cursor = _parse_event_cursor(after_sequence)
    except ValueError:
        return _error(request, "INVALID_EVENT_CURSOR", "事件游标无效", 400)
    if header_cursor is not None and query_cursor is not None and header_cursor != query_cursor:
        return _error(request, "INVALID_EVENT_CURSOR", "事件游标无效", 400)
    cursor = header_cursor if header_cursor is not None else query_cursor
    current_sequence = cursor or 0
    max_sequence = int(events[-1]["sequence"])
    if current_sequence > max_sequence:
        return _error(request, "INVALID_EVENT_CURSOR", "事件游标无效", 400)

    _record(request)
    request_id = _request_id(request)
    trace_id = str(run["trace_id"])
    return StreamingResponse(
        _replay_events(run_id, current_sequence, request_id, trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Request-Id": request_id,
            "X-Trace-Id": trace_id,
        },
    )


@app.get("/api/v1/runs/{run_id}")
def get_run(request: Request, run_id: str) -> JSONResponse:
    """读取 Run，额外提供跨 Session 响应夹具以验证前端保护。"""
    run = _find_run(run_id)
    if run is not None:
        return _run_response(request, run)
    if run_id == MISMATCH_RUN_ID:
        mismatch_run: dict[str, Any] = {**RUN, "id": MISMATCH_RUN_ID, "session_id": ARCHIVED_SESSION_ID}
        return _run_response(request, mismatch_run)
    return _error(request, "RUN_NOT_FOUND", "诊断运行不存在", 404)


@app.get("/__mock__/requests")
def request_log() -> dict[str, list[dict[str, str]]]:
    """仅供本地验收读取请求顺序；主前端永不调用此路径。"""
    return {"items": REQUEST_LOG}


def main() -> None:
    """以独立端口启动 mock，默认不占用真实后端的 8000 端口。"""
    host = os.getenv("OPERMIND_MOCK_API_HOST", DEFAULT_HOST)
    port = int(os.getenv("OPERMIND_MOCK_API_PORT", str(DEFAULT_PORT)))
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
