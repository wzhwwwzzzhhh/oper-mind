"""诊断事件载荷断言：log 工具事件附 service_id，db 事件行为不变。

对应 Design §2.4 / §3 的 `coordinator_executor._event_data` 增量变更。
"""

from src.infrastructure.diagnosis.coordinator_executor import _event_data


def _tool_event(role: str, status: str = "ok") -> dict:
    """构造一条工具调用 trace 事件。"""
    return {
        "type": "tool_invoked",
        "node": "tool",
        "detail": "调用 search_logs 成功",
        "status": status,
        "duration_ms": 12,
        "role": role,
    }


class TestEventServiceId:
    """工具事件附 service_id 的载荷契约。"""

    def test_log_role_attaches_service_id(self) -> None:
        data = _event_data(_tool_event("log"), service_id="postgres-production")
        assert data["role"] == "log"
        assert data["service_id"] == "postgres-production"

    def test_db_role_keeps_service_id(self) -> None:
        data = _event_data(_tool_event("db"), service_id="postgres-production")
        assert data["service_id"] == "postgres-production"

    def test_server_role_does_not_attach_service_id(self) -> None:
        data = _event_data(_tool_event("server"), service_id="postgres-production")
        assert "service_id" not in data

    def test_no_service_id_no_key(self) -> None:
        data = _event_data(_tool_event("log"))
        assert "service_id" not in data

    def test_non_tool_event_keeps_empty_data(self) -> None:
        assert _event_data({"type": "agent_done"}) == {}

    def test_summary_truncated_to_280(self) -> None:
        event = _tool_event("log")
        event["detail"] = "x" * 300
        data = _event_data(event, service_id="s")
        assert len(data["summary"]) == 280
