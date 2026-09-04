"""P12 Redis 固定命令与安全投影。"""

import json

import pytest
from sqlalchemy.exc import OperationalError

from src.infrastructure.services.redis_connector import RedisServiceConnector
from src.tools.service_health_tools import RedisHealthOverviewTool


class _Redis:
    def __init__(
        self,
        *,
        missing_memory: bool = False,
        cleanup_fail: bool = False,
        command_error: Exception | None = None,
    ) -> None:
        self.calls: list[tuple[str, object | None]] = []
        self.missing_memory = missing_memory
        self.cleanup_fail = cleanup_fail
        self.command_error = command_error

    def ping(self):
        self.calls.append(("PING", None))
        if self.command_error is not None:
            raise self.command_error
        return True

    def info(self, section):
        self.calls.append(("INFO", section))
        return {} if self.missing_memory else {"used_memory": 128}

    def client_list(self):
        self.calls.append(("CLIENT LIST", None))
        return [{"name": "secret-client"}, {"name": "other"}]

    def slowlog_len(self):
        self.calls.append(("SLOWLOG LEN", None))
        return 3

    def close(self):
        if self.cleanup_fail:
            raise RuntimeError("secret cleanup")


def test_redis_tool_executes_only_fixed_commands_and_projects_scalars() -> None:
    client = _Redis()
    connector = RedisServiceConnector("redis://example.invalid", client=client)

    result = RedisHealthOverviewTool(connector).execute()
    payload = json.loads(result.output)

    assert client.calls == [
        ("PING", None),
        ("INFO", "memory"),
        ("CLIENT LIST", None),
        ("SLOWLOG LEN", None),
    ]
    assert payload["memory_bytes"] == 128
    assert payload["client_connections"] == 2
    assert payload["slowlog_count"] == 3
    assert "secret-client" not in result.output
    assert RedisHealthOverviewTool(connector).parameters == {
        "type": "object",
        "properties": {},
        "additionalProperties": False,
    }


def test_redis_missing_required_scalar_fails_closed() -> None:
    result = RedisHealthOverviewTool(
        RedisServiceConnector("redis://example.invalid", client=_Redis(missing_memory=True))
    ).execute()
    assert result.status == "unavailable"
    assert json.loads(result.output)["failure_code"] == "malformed_fact"


def test_redis_cleanup_failure_is_honest_and_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = RedisServiceConnector("redis://example.invalid")
    monkeypatch.setattr(connector, "_create_readonly_client", lambda: _Redis(cleanup_fail=True))
    result = RedisHealthOverviewTool(connector).execute()
    assert result.status == "ok"
    assert json.loads(result.output)["source_status"] == "cleanup_unknown"
    assert "secret" not in result.output


def test_redis_primary_and_cleanup_failure_has_closed_code(monkeypatch: pytest.MonkeyPatch) -> None:
    connector = RedisServiceConnector("redis://example.invalid")
    monkeypatch.setattr(
        connector,
        "_create_readonly_client",
        lambda: _Redis(cleanup_fail=True, command_error=TimeoutError("secret")),
    )
    result = RedisHealthOverviewTool(connector).execute()
    assert result.status == "unavailable"
    assert json.loads(result.output)["failure_code"] == "cleanup_failed"


def test_redis_classifies_wrapped_timeout_and_authentication() -> None:
    authentication_error = type("AuthenticationError", (Exception,), {})()
    assert RedisServiceConnector._failure_code(
        OperationalError("statement", {}, TimeoutError("secret"))
    ) == "operation_timeout"
    assert RedisServiceConnector._failure_code(authentication_error) == "permission_denied"


@pytest.mark.parametrize(
    ("error", "code"),
    [(TimeoutError("secret"), "operation_timeout"), (PermissionError("secret"), "permission_denied")],
)
def test_redis_maps_external_failure_to_closed_code(error: Exception, code: str) -> None:
    client = _Redis(command_error=error)
    result = RedisHealthOverviewTool(
        RedisServiceConnector("redis://example.invalid", client=client)
    ).execute()
    assert result.status == "unavailable"
    assert json.loads(result.output)["failure_code"] == code
    assert "secret" not in result.output
