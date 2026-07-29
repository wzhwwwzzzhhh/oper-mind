"""P3.3c mock FastAPI 的 P2 Run 受理、持久化事件和 SSE 契约测试。"""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from mock_v1_api import (
    REQUEST_LOG,
    ARCHIVED_RUN_ID,
    ARCHIVED_SESSION_ID,
    CANCELLED_RUN_ID,
    EMPTY_RESULT_RUN_ID,
    FAILED_RUN_ID,
    PROTOCOL_ERROR_RUN_ID,
    RUN_ID,
    SESSION_ID,
    app,
    clear_request_log,
    reset_mock_state,
)

IDEMPOTENCY_KEY = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
REQUEST_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"


def _headers(*, idempotency_key: str | None = None, last_event_id: str | None = None) -> dict[str, str]:
    """提供 P3 前端 client 与 SSE 续传使用的关联请求头。"""
    headers = {"X-Request-Id": REQUEST_ID, "Accept": "application/json"}
    if idempotency_key is not None:
        headers["Idempotency-Key"] = idempotency_key
    if last_event_id is not None:
        headers["Last-Event-ID"] = last_event_id
    return headers


def _accept_run(
    client: TestClient,
    *,
    query: str = "请检查 Nginx 5xx。",
    idempotency_key: str = IDEMPOTENCY_KEY,
):
    """使用指定 UUID 幂等键受理一个确定性 mock Run。"""
    return client.post(
        f"/api/v1/sessions/{SESSION_ID}/runs",
        headers=_headers(idempotency_key=idempotency_key),
        json={"query": query},
    )


def _sse_event_sequences(body: str) -> list[int]:
    """从有限 SSE 响应中读取每条 run_event 的 sequence。"""
    sequences: list[int] = []
    for frame in body.strip().split("\n\n"):
        lines = frame.splitlines()
        event_line = next(line for line in lines if line.startswith("event: "))
        data_line = next(line for line in lines if line.startswith("data: "))
        assert event_line == "event: run_event"
        envelope = json.loads(data_line.removeprefix("data: "))
        sequence = int(next(line for line in lines if line.startswith("id: ")).removeprefix("id: "))
        assert envelope["event"]["sequence"] == sequence
        sequences.append(sequence)
    return sequences


def test_session_page回显关联ID与opaque_cursor() -> None:
    """列表响应必须回显 request ID，并保留服务端定义的下一页 cursor。"""
    reset_mock_state()
    with TestClient(app) as client:
        response = client.get("/api/v1/sessions", headers=_headers(), params={"limit": 20})
        second_page = client.get(
            "/api/v1/sessions",
            headers=_headers(),
            params={"cursor": "session-page-2", "limit": 20, "status": "active"},
        )

    payload = response.json()
    assert response.status_code == 200
    assert response.headers["X-Request-Id"] == REQUEST_ID
    assert payload["meta"]["request_id"] == REQUEST_ID
    assert payload["page"] == {"next_cursor": "session-page-2", "has_more": True}
    assert payload["items"][0]["id"] == SESSION_ID
    assert second_page.json()["items"][0]["status"] == "active"


def test_run深链读取保持P2_json_envelope与顺序记录() -> None:
    """模拟 P3.3b 浏览器深链的五个只读资源，并验证请求顺序。"""
    reset_mock_state()
    with TestClient(app) as client:
        assert client.get(f"/api/v1/sessions/{SESSION_ID}", headers=_headers()).status_code == 200
        assert client.get(f"/api/v1/sessions/{SESSION_ID}/runs", headers=_headers()).status_code == 200
        assert client.get(f"/api/v1/sessions/{SESSION_ID}/messages", headers=_headers()).status_code == 200
        run_response = client.get(f"/api/v1/runs/{RUN_ID}", headers=_headers())
        events_response = client.get(f"/api/v1/runs/{RUN_ID}/events", headers=_headers())

    assert run_response.status_code == 200
    assert run_response.json()["run"]["result"]["summary"] == "Nginx 上游连接池已耗尽。"
    assert events_response.json()["items"][0]["sequence"] == 1
    assert [item["path"] for item in REQUEST_LOG] == [
        f"/api/v1/sessions/{SESSION_ID}",
        f"/api/v1/sessions/{SESSION_ID}/runs",
        f"/api/v1/sessions/{SESSION_ID}/messages",
        f"/api/v1/runs/{RUN_ID}",
        f"/api/v1/runs/{RUN_ID}/events",
    ]


def test_静态成功Result覆盖完整P2结构化字段与归档历史() -> None:
    """默认与归档 Run 都必须提供可供 P3.4 直接读取的完整 Result。"""
    reset_mock_state()
    with TestClient(app) as client:
        current = client.get(f"/api/v1/runs/{RUN_ID}", headers=_headers())
        archived_runs = client.get(f"/api/v1/sessions/{ARCHIVED_SESSION_ID}/runs", headers=_headers())
        archived = client.get(f"/api/v1/runs/{ARCHIVED_RUN_ID}", headers=_headers())
        empty_result = client.get(f"/api/v1/runs/{EMPTY_RESULT_RUN_ID}", headers=_headers())
        protocol_error = client.get(f"/api/v1/runs/{PROTOCOL_ERROR_RUN_ID}", headers=_headers())

    result = current.json()["run"]["result"]
    assert result["run_id"] == RUN_ID
    assert result["created_at"].endswith("Z")
    assert result["root_causes"][0]["evidence_ids"] == [result["evidence"][0]["id"]]
    assert result["evidence"][0]["attributes"] == {
        "active_connections": 120,
        "saturation": 0.98,
        "healthy": False,
        "note": None,
    }
    assert result["recommendations"][0]["requires_approval"] is True
    assert result["risks"][0]["mitigation"] == "分批调整并回滚异常实例。"
    assert result["agent_summary"][0]["duration_ms"] == 120
    assert result["report_markdown"].startswith("# Mock 结果补充")
    assert archived_runs.json()["items"][0]["id"] == ARCHIVED_RUN_ID
    assert archived.json()["run"]["result"]["run_id"] == ARCHIVED_RUN_ID
    empty_payload = empty_result.json()["run"]["result"]
    assert empty_payload["created_at"].endswith("Z")
    assert empty_payload["root_causes"] == []
    assert empty_payload["evidence"] == []
    assert empty_payload["impact"] is None
    assert empty_payload["recommendations"] == []
    assert empty_payload["risks"] == []
    assert empty_payload["agent_summary"] == []
    assert empty_payload["report_markdown"] is None
    assert "created_at" not in protocol_error.json()["run"]["result"]
    with TestClient(app) as client:
        failed = client.get(f"/api/v1/runs/{FAILED_RUN_ID}", headers=_headers())
        cancelled = client.get(f"/api/v1/runs/{CANCELLED_RUN_ID}", headers=_headers())
        failed_events = client.get(f"/api/v1/runs/{FAILED_RUN_ID}/events", headers=_headers())
        cancelled_events = client.get(f"/api/v1/runs/{CANCELLED_RUN_ID}/events", headers=_headers())
    assert failed.json()["run"]["status"] == "failed"
    assert failed.json()["run"]["result"] is None
    assert failed.json()["run"]["error"] == {"code": "TOOL_TIMEOUT", "message": "上游日志查询超时。"}
    assert cancelled.json()["run"]["status"] == "cancelled"
    assert cancelled.json()["run"]["result"] is None
    assert cancelled.json()["run"]["error"] is None
    assert failed_events.json()["items"] == []
    assert cancelled_events.json()["items"] == []


def test_post_run首次受理与同key重放保持同Run和trace() -> None:
    """P2 受理必须返回 202，且同 key/规范化 query 不得创建第二个 Run。"""
    reset_mock_state()
    with TestClient(app) as client:
        first = _accept_run(client, query="请检查 Nginx 5xx。")
        replay = _accept_run(client, query="  请检查   Nginx 5xx。  ")
        runs = client.get(f"/api/v1/sessions/{SESSION_ID}/runs", headers=_headers())

    first_payload = first.json()
    replay_payload = replay.json()
    assert first.status_code == 202
    assert replay.status_code == 202
    accepted_run_id = first_payload["run"]["id"]
    assert accepted_run_id == replay_payload["run"]["id"]
    assert first_payload["run"]["trace_id"] == replay_payload["run"]["trace_id"]
    assert first_payload["run"]["status"] == "queued"
    assert [item["id"] for item in runs.json()["items"]].count(accepted_run_id) == 1


def test_post_run不同key创建不同Run() -> None:
    """不同幂等键必须产生不同的确定性 Run，不可误复用旧 Run。"""
    reset_mock_state()
    with TestClient(app) as client:
        first = _accept_run(client)
        second = _accept_run(
            client,
            idempotency_key="ffffffff-ffff-4fff-8fff-ffffffffffff",
        )
        first_run = first.json()["run"]
        second_run = second.json()["run"]
        first_event = client.get(f"/api/v1/runs/{first_run['id']}/events", headers=_headers())
        second_event = client.get(f"/api/v1/runs/{second_run['id']}/events", headers=_headers())

    assert first.status_code == second.status_code == 202
    assert first_run["id"] != second_run["id"]
    assert first_run["trace_id"] != second_run["trace_id"]
    assert first_event.json()["items"][0]["id"] != second_event.json()["items"][0]["id"]


def test_post_run同key不同query返回安全409() -> None:
    """复用幂等键但改变请求语义必须安全拒绝，不能产生第二个 Run。"""
    reset_mock_state()
    with TestClient(app) as client:
        assert _accept_run(client).status_code == 202
        conflict = _accept_run(client, query="请检查 MySQL 连接数。")
        runs = client.get(f"/api/v1/sessions/{SESSION_ID}/runs", headers=_headers())

    assert conflict.status_code == 409
    assert conflict.json()["error"] == {
        "code": "IDEMPOTENCY_KEY_REUSED",
        "message": "幂等键已用于不同请求",
        "details": None,
    }
    accepted_run_id = runs.json()["items"][0]["id"]
    assert [item["id"] for item in runs.json()["items"]].count(accepted_run_id) == 1
    assert "sqlite" not in conflict.text.lower()
    assert "postgres" not in conflict.text.lower()


def test_run_event分页与有限SSE帧终态关闭() -> None:
    """事件列表先读取 queued，SSE 再按 id/run_event 重放至终态并关闭。"""
    reset_mock_state()
    with TestClient(app) as client:
        accepted = _accept_run(client)
        assert accepted.status_code == 202
        accepted_run_id = accepted.json()["run"]["id"]
        accepted_trace_id = accepted.json()["run"]["trace_id"]
        initial_events = client.get(f"/api/v1/runs/{accepted_run_id}/events", headers=_headers())
        stream = client.get(f"/api/v1/runs/{accepted_run_id}/stream", headers=_headers())
        recovered_events = client.get(f"/api/v1/runs/{accepted_run_id}/events", headers=_headers())
        recovered_event_page_2 = client.get(
            f"/api/v1/runs/{accepted_run_id}/events",
            headers=_headers(),
            params={"cursor": "event-page-2"},
        )
        terminal_run = client.get(f"/api/v1/runs/{accepted_run_id}", headers=_headers())

    assert initial_events.json()["items"][0]["type"] == "run_queued"
    assert initial_events.json()["page"] == {"next_cursor": None, "has_more": False}
    assert stream.status_code == 200
    assert stream.headers["content-type"].startswith("text/event-stream")
    assert stream.headers["X-Request-Id"] == REQUEST_ID
    assert stream.headers["X-Trace-Id"] == accepted_trace_id
    assert _sse_event_sequences(stream.text) == [1, 2, 3]
    assert stream.text.count("event: run_event") == 3
    assert "keep-alive" not in stream.text
    assert [item["sequence"] for item in recovered_events.json()["items"]] == [1]
    assert recovered_events.json()["page"] == {"next_cursor": "event-page-2", "has_more": True}
    assert [item["sequence"] for item in recovered_event_page_2.json()["items"]] == [2, 3]
    assert recovered_event_page_2.json()["page"] == {"next_cursor": None, "has_more": False}
    assert terminal_run.json()["run"]["status"] == "succeeded"
    assert terminal_run.json()["run"]["finished_at"] == "2026-07-28T06:00:02.000Z"
    terminal_result = terminal_run.json()["run"]["result"]
    assert terminal_result["run_id"] == accepted_run_id
    assert terminal_result["created_at"] == "2026-07-28T06:00:02.000Z"
    assert terminal_result["root_causes"][0]["evidence_ids"] == [terminal_result["evidence"][0]["id"]]
    assert terminal_result["recommendations"][0]["requires_approval"] is True


def test_last_event_id只续传未处理事件并在终态关闭() -> None:
    """浏览器续传只取得 sequence 大于 Last-Event-ID 的持久化事件。"""
    reset_mock_state()
    with TestClient(app) as client:
        accepted = _accept_run(client)
        assert accepted.status_code == 202
        accepted_run_id = accepted.json()["run"]["id"]
        accepted_trace_id = accepted.json()["run"]["trace_id"]
        resumed = client.get(
            f"/api/v1/runs/{accepted_run_id}/stream",
            headers=_headers(last_event_id="1"),
        )

    assert resumed.status_code == 200
    assert _sse_event_sequences(resumed.text) == [2, 3]
    assert "id: 1\n" not in resumed.text
    last_data_line = resumed.text.strip().split("\n\n")[-1].split("data: ", 1)[1]
    last_envelope = json.loads(last_data_line)
    assert last_envelope["event"]["sequence"] == 3
    assert last_envelope["event"]["type"] == "run_succeeded"
    assert last_envelope["meta"] == {"request_id": REQUEST_ID, "trace_id": accepted_trace_id}


def test_sse双游标冲突返回安全400() -> None:
    """Last-Event-ID 与 after_sequence 不一致必须拒绝，避免错误重放。"""
    reset_mock_state()
    with TestClient(app) as client:
        accepted = _accept_run(client)
        assert accepted.status_code == 202
        accepted_run_id = accepted.json()["run"]["id"]
        response = client.get(
            f"/api/v1/runs/{accepted_run_id}/stream",
            headers=_headers(last_event_id="1"),
            params={"after_sequence": "2"},
        )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_EVENT_CURSOR"


def test_internal_error保持安全错误资源(monkeypatch) -> None:
    """显式 mock 错误模式仍返回 P2 安全 JSON envelope。"""
    reset_mock_state()
    monkeypatch.setenv("OPERMIND_MOCK_API_MODE", "internal_error")
    with TestClient(app) as client:
        response = client.get("/api/v1/sessions", headers=_headers())

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert response.json()["meta"]["request_id"] == REQUEST_ID


def test_不存在的资源返回安全错误且不泄露连接信息() -> None:
    """不存在的 Run 必须返回 P2 安全错误和关联元数据。"""
    reset_mock_state()
    with TestClient(app) as client:
        response = client.get("/api/v1/runs/not-found", headers=_headers())

    payload = response.json()
    assert response.status_code == 404
    assert payload["error"] == {"code": "RUN_NOT_FOUND", "message": "诊断运行不存在", "details": None}
    assert payload["meta"]["request_id"] == REQUEST_ID
    assert "sqlite" not in response.text.lower()
    assert "postgres" not in response.text.lower()
