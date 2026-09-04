"""P12 独立人工 Runner；不得从 pytest/CI 或非交互环境启动。"""

from __future__ import annotations

import hmac
import json
import os
import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from scripts.check_p12_real_readonly_preflight import PreflightSafeStop, check_preflight
from src.domain.services import BindingOrigin


class DeterministicLocalDriver:
    """只按注入 Tool 菜单选择首个无参数 Tool，不调用模型 Provider。"""

    def __init__(self, expected_tool_name: str | None = None) -> None:
        self.client = SimpleNamespace(api_key="mock")
        self._tool_called = False
        self._expected_tool_name = expected_tool_name

    def chat(self, messages, tools=None, **kwargs):
        del kwargs
        if tools and not self._tool_called:
            names = [item["function"]["name"] for item in tools]
            name = self._expected_tool_name or names[0]
            if name not in names:
                raise PreflightSafeStop("P12_EXPECTED_TOOL_UNAVAILABLE")
            self._tool_called = True
            return {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "p12-local-tool-call",
                        "type": "function",
                        "function": {"name": name, "arguments": "{}"},
                    }
                ],
            }
        tool_messages = [item for item in messages if item.get("role") == "tool"]
        if not self._tool_called or len(tool_messages) != 1:
            raise PreflightSafeStop("P12_TOOL_FACT_MISSING")
        try:
            fact = json.loads(tool_messages[0].get("content", ""))
        except (TypeError, json.JSONDecodeError) as error:
            raise PreflightSafeStop("P12_TOOL_FACT_MALFORMED") from error
        if not isinstance(fact, dict) or self._expected_tool_name is None:
            raise PreflightSafeStop("P12_TOOL_FACT_MALFORMED")
        allowed_fields = {
            "check_connection_pool": {
                "availability",
                "total_connections",
                "active_connections",
                "idle_connections",
                "waiting_connections",
                "max_connections",
                "utilization",
                "health",
                "observed_at",
                "source_status",
            },
            "redis_health_overview": {
                "availability",
                "memory_bytes",
                "client_connections",
                "slowlog_count",
                "observed_at",
                "source_status",
            },
            "mysql_health_overview": {
                "availability",
                "uptime_seconds",
                "current_connections",
                "running_connections",
                "max_connections",
                "slow_query_count",
                "observed_at",
                "source_status",
            },
        }[self._expected_tool_name]
        if set(fact) != allowed_fields or fact.get("availability") != "healthy":
            raise PreflightSafeStop("P12_TOOL_FACT_MALFORMED")
        safe_summary = json.dumps(fact, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return {"role": "assistant", "content": f"只读健康事实：{safe_summary}"}


def run_acceptance(environment=os.environ, *, stdin=sys.stdin, input_fn=input) -> dict[str, str]:
    """执行单目标验收；返回值和输出均不含指标、异常、目标或 credential ref。"""
    preflight = check_preflight(environment)
    if not stdin.isatty():
        raise PreflightSafeStop("P12_TTY_REQUIRED")
    confirmed = input_fn("输入本次只读验收的 service_id 以确认目标：").strip()
    if not hmac.compare_digest(confirmed, preflight.service_id):
        raise PreflightSafeStop("P12_USER_CONFIRMATION_MISMATCH")

    # 延迟导入：软件 preflight 和安全 import 都不会装载数据库/Redis/模型 client。
    from src.api.v1.dependencies import build_v1_services_for_runtime
    from src.application.contracts import CreateRunCommand
    from src.application.service_center import CreateServiceSessionCommand
    from src.config import load_persistence_settings
    from src.core.bootstrap import build_coordinator
    from src.domain.diagnosis import RunEventType, RunStatus
    from src.infrastructure.persistence.database import create_persistence_runtime
    from src.infrastructure.persistence.repositories import (
        SqlAlchemyDiagnosisResultRepository,
        SqlAlchemyRunEventRepository,
    )
    from src.infrastructure.services.service_connector_factory import load_registered_services

    runtime = create_persistence_runtime(load_persistence_settings().database_url)

    expected_tool = {
        "postgres": "check_connection_pool",
        "redis": "redis_health_overview",
        "mysql": "mysql_health_overview",
    }[preflight.kind]

    def coordinator_factory(service_id, binding):
        return build_coordinator(
            DeterministicLocalDriver(expected_tool),
            service_id=service_id,
            binding=binding,
        )

    services = build_v1_services_for_runtime(
        runtime,
        coordinator_factory,
        registry_loader=lambda: load_registered_services(runtime.session_factory),
    )
    registry = services.service_registry
    registration = services.service_registration
    center = services.service_center
    if registry is None or registration is None or center is None:
        raise PreflightSafeStop("P12_RUNTIME_UNAVAILABLE")
    binding = registry.resolve_binding(preflight.service_id, expected_kind=preflight.kind)
    expected = BindingOrigin.from_reference(preflight.credential_ref).source_fingerprint
    if not hmac.compare_digest(binding.origin.source_fingerprint, expected):
        raise PreflightSafeStop("P12_BINDING_ORIGIN_MISMATCH")

    connection = registration.test_connection(preflight.service_id)
    if connection.availability.value != "healthy":
        raise PreflightSafeStop("P12_CONNECTION_TEST_FAILED")
    session = center.create_service_session(CreateServiceSessionCommand(service_id=preflight.service_id))
    accepted = services.run_service.accept_run(
        CreateRunCommand(
            session_id=session.id,
            query="数据库连接压力指标",
            idempotency_key=uuid4(),
            service_id=preflight.service_id,
        )
    )
    completed = services.run_service.execute_run(accepted.run.id)
    verification_session = runtime.session_factory()
    try:
        events = SqlAlchemyRunEventRepository(verification_session).list_by_run(
            completed.id,
            cursor=None,
            limit=100,
        ).items
        result = SqlAlchemyDiagnosisResultRepository(verification_session).get_by_run_id(completed.id)
    finally:
        verification_session.close()
    terminal_events = [
        event
        for event in events
        if event.type in {RunEventType.RUN_SUCCEEDED, RunEventType.RUN_FAILED, RunEventType.RUN_CANCELLED}
    ]
    tool_events = [event for event in events if event.type is RunEventType.TOOL_INVOKED]
    result_text = "" if result is None else (result.report_markdown or result.summary or "")
    if (
        completed.status is not RunStatus.SUCCEEDED
        or [event.type for event in terminal_events] != [RunEventType.RUN_SUCCEEDED]
        or len(tool_events) != 1
        or tool_events[0].data.get("status") != "ok"
        or tool_events[0].data.get("service_id") != preflight.service_id
        or result is None
        or "只读健康事实：" not in result_text
        or any(
            forbidden in result_text.lower()
            for forbidden in ("dsn", "password", "username", "nonce", "secret", "processlist")
        )
    ):
        raise PreflightSafeStop("P12_ACCEPTANCE_EVIDENCE_INVALID")
    return {
        "observed_at": datetime.now(UTC).isoformat(),
        "service_id": preflight.service_id,
        "kind": preflight.kind,
        "run_id": str(completed.id),
        "terminal_status": completed.status.value,
        "model_source": "deterministic_local_driver",
        "service_fact_source": "registry_binding",
    }


def main() -> int:
    """人工入口输出脱敏步骤状态；任何安全停止只打印固定 code。"""
    try:
        result = run_acceptance()
    except PreflightSafeStop as error:
        print(f"P12 acceptance stopped: {error.code}")
        return 2
    except Exception:
        print("P12 acceptance stopped: P12_RUNTIME_FAILED")
        return 3
    print(
        "P12 acceptance finished: "
        f"time={result['observed_at']} service_id={result['service_id']} "
        f"kind={result['kind']} run_id={result['run_id']} status={result['terminal_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
