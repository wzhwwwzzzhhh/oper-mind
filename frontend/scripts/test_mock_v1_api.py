"""P3.2c.1 mock FastAPI 的只读 v1 契约测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from mock_v1_api import REQUEST_LOG, RUN_ID, SESSION_ID, app, clear_request_log


def _headers() -> dict[str, str]:
    """提供 P2 前端 client 使用的关联请求头。"""
    return {"X-Request-Id": "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", "Accept": "application/json"}


def test_session_page回显关联ID与opaque_cursor() -> None:
    """列表响应必须回显 request ID，并保留服务端定义的下一页 cursor。"""
    clear_request_log()
    with TestClient(app) as client:
        response = client.get("/api/v1/sessions", headers=_headers(), params={"limit": 20})

    payload = response.json()
    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == _headers()["X-Request-Id"]
    assert payload["meta"]["request_id"] == _headers()["X-Request-Id"]
    assert payload["page"] == {"next_cursor": "session-page-2", "has_more": True}
    assert payload["items"][0]["id"] == SESSION_ID
    with TestClient(app) as client:
        second_page = client.get(
            "/api/v1/sessions",
            headers=_headers(),
            params={"cursor": "session-page-2", "limit": 20, "status": "active"},
        )

    assert second_page.json()["items"][0]["status"] == "active"


def test_run深链读取保持P2_json_envelope与顺序记录() -> None:
    """模拟浏览器深链的四个只读资源，并验证 mock 可观察到相同顺序。"""
    clear_request_log()
    with TestClient(app) as client:
        assert client.get(f"/api/v1/sessions/{SESSION_ID}", headers=_headers()).status_code == 200
        assert client.get(f"/api/v1/sessions/{SESSION_ID}/runs", headers=_headers()).status_code == 200
        assert client.get(f"/api/v1/sessions/{SESSION_ID}/messages", headers=_headers()).status_code == 200
        run_response = client.get(f"/api/v1/runs/{RUN_ID}", headers=_headers())

    assert run_response.status_code == 200
    assert run_response.json()["run"]["result"]["summary"] == "Nginx 上游连接池已耗尽。"
    assert [item["path"] for item in REQUEST_LOG] == [
        "/api/v1/sessions/11111111-1111-4111-8111-111111111111",
        "/api/v1/sessions/11111111-1111-4111-8111-111111111111/runs",
        "/api/v1/sessions/11111111-1111-4111-8111-111111111111/messages",
        "/api/v1/runs/33333333-3333-4333-8333-333333333333",
    ]


def test_internal_error保持安全错误资源(monkeypatch) -> None:
    """显式 mock 错误模式仍返回 P2 安全 JSON envelope。"""
    clear_request_log()
    monkeypatch.setenv("OPERMIND_MOCK_API_MODE", "internal_error")
    with TestClient(app) as client:
        response = client.get("/api/v1/sessions", headers=_headers())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["meta"]["request_id"] == _headers()["X-Request-Id"]


def test_不存在的资源返回安全错误且不泄露连接信息() -> None:
    """不存在的 Run 必须返回 P2 安全错误和关联元数据。"""
    clear_request_log()
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/not-found", headers=_headers())

    payload = response.json()
    assert response.status_code == 404
    assert payload["error"] == {"code": "RUN_NOT_FOUND", "message": "诊断运行不存在", "details": None}
    assert payload["meta"]["request_id"] == _headers()["X-Request-Id"]
    assert "sqlite" not in response.text.lower()
    assert "postgres" not in response.text.lower()
