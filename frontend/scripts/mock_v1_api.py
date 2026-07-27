"""P3.2c.1 本地 mock FastAPI：仅模拟 P2 已批准的五个只读 v1 资源。"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

APP_NAME = "OperMind P3.2c Mock API"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8100
TRACE_ID = "55555555-5555-4555-8555-555555555555"
SESSION_ID = "11111111-1111-4111-8111-111111111111"
ARCHIVED_SESSION_ID = "22222222-2222-4222-8222-222222222222"
RUN_ID = "33333333-3333-4333-8333-333333333333"
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
RUN: dict[str, object] = {
    "id": RUN_ID,
    "session_id": SESSION_ID,
    "trace_id": TRACE_ID,
    "input_message_id": "66666666-6666-4666-8666-666666666666",
    "status": "succeeded",
    "result": {
        "id": "77777777-7777-4777-8777-777777777777",
        "run_id": RUN_ID,
        "summary": "Nginx 上游连接池已耗尽。",
        "severity": "high",
        "confidence": 0.92,
        "root_causes": [],
        "evidence": [],
        "impact": None,
        "recommendations": [],
        "risks": [],
        "requires_approval": False,
        "agent_summary": [],
        "report_markdown": None,
    },
    "error": None,
    "created_at": "2026-07-27T01:00:30.000Z",
    "started_at": "2026-07-27T01:00:31.000Z",
    "finished_at": "2026-07-27T01:00:33.000Z",
}

REQUEST_LOG: list[dict[str, str]] = []
app = FastAPI(title=APP_NAME, docs_url=None, redoc_url=None, openapi_url=None)


def clear_request_log() -> None:
    """清空进程内验收日志，仅供本地测试调用。"""
    REQUEST_LOG.clear()


def _response_mode() -> str:
    """读取本地验收模式；默认永远返回成功资源。"""
    return os.getenv("OPERMIND_MOCK_API_MODE", "success")


def _request_id(request: Request) -> str:
    """回显前端传入的关联 ID；缺失时保留明显的测试标识。"""
    return request.headers.get("X-Request-Id", "missing-client-request-id")


def _record(request: Request) -> None:
    """记录 mock 收到的 v1 GET，供人工验收核对请求顺序。"""
    REQUEST_LOG.append(
        {
            "method": request.method,
            "path": request.url.path,
            "query": request.url.query,
            "request_id": _request_id(request),
        }
    )


def _response(request: Request, body: Mapping[str, object], status_code: int = 200) -> JSONResponse:
    """返回 P2 JSON envelope 以及与 meta 一致的关联响应头。"""
    _record(request)
    request_id = _request_id(request)
    return JSONResponse(
        content={**body, "meta": {"request_id": request_id, "trace_id": TRACE_ID}},
        status_code=status_code,
        headers={"X-Request-Id": request_id, "X-Trace-Id": TRACE_ID},
    )


def _error(request: Request, code: str, message: str, status_code: int) -> JSONResponse:
    """返回与 P2 一致的安全错误资源，不泄露实现或连接信息。"""
    return _response(
        request,
        {"error": {"code": code, "message": message, "details": None}},
        status_code,
    )


@app.get("/health")
def health() -> dict[str, str]:
    """暴露 mock 进程自身的最小健康检查。"""
    return {"status": "ok", "service": "p3.2c-mock-api"}


@app.get("/api/v1/sessions")
def list_sessions(request: Request, cursor: str | None = None, limit: int = 20) -> JSONResponse:
    """模拟 active Session 列表与不透明 cursor；不提供任何写入能力。"""
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
        return _response(request, {"items": [], "page": {"next_cursor": None, "has_more": False}})
    if session_id != SESSION_ID:
        return _error(request, "SESSION_NOT_FOUND", "会话不存在", 404)
    if cursor == "run-page-2":
        return _response(request, {"items": [], "page": {"next_cursor": None, "has_more": False}})
    return _response(request, {"items": [RUN], "page": {"next_cursor": "run-page-2", "has_more": True}})


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


@app.get("/api/v1/runs/{run_id}")
def get_run(request: Request, run_id: str) -> JSONResponse:
    """读取 Run，额外提供跨 Session 响应夹具以验证前端保护。"""
    if run_id == RUN_ID:
        return _response(request, {"run": RUN})
    if run_id == MISMATCH_RUN_ID:
        mismatch_run: dict[str, Any] = {**RUN, "id": MISMATCH_RUN_ID, "session_id": ARCHIVED_SESSION_ID}
        return _response(request, {"run": mismatch_run})
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
