"""P12 Runner 的 import、TTY 与本地 scripted driver 契约。"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from scripts import run_p12_real_readonly_acceptance as runner
from scripts.check_p12_real_readonly_preflight import (
    CREDENTIAL_REF_ENV,
    OPT_IN_ENV,
    OPT_IN_VALUE,
    SERVICE_ID_ENV,
    SERVICE_KIND_ENV,
    TARGET_CLASS_ENV,
    PreflightSafeStop,
)
from scripts.run_p12_real_readonly_acceptance import DeterministicLocalDriver, run_acceptance
from src.api.v1.dependencies import build_v1_services_for_runtime
from src.core.bootstrap import build_coordinator
from src.domain.services import (
    SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
    SERVICE_HEALTH_PRESSURE_INTENT_ID,
    BindingOrigin,
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceDatabaseStateData,
    ServiceDefinitionData,
    ServiceInvestigationData,
    ServiceMode,
    ServiceServerMetricsData,
    ServiceSnapshotData,
    ServiceSourceStatus,
)
from src.infrastructure.persistence.database import Base, create_persistence_runtime


def _environment() -> dict[str, str]:
    return {
        OPT_IN_ENV: OPT_IN_VALUE,
        SERVICE_ID_ENV: "redis.test",
        SERVICE_KIND_ENV: "redis",
        CREDENTIAL_REF_ENV: "registry:redis.test",
        TARGET_CLASS_ENV: "non-production",
    }


def test_runner_stops_before_runtime_import_without_tty() -> None:
    with pytest.raises(PreflightSafeStop) as captured:
        run_acceptance(_environment(), stdin=SimpleNamespace(isatty=lambda: False))
    assert captured.value.code == "P12_TTY_REQUIRED"


def test_scripted_driver_selects_only_registered_tool_then_finishes() -> None:
    driver = DeterministicLocalDriver("redis_health_overview")
    tools = [{"function": {"name": "redis_health_overview"}}]
    first = driver.chat([], tools=tools)
    second = driver.chat(
        [
            {
                "role": "tool",
                "content": (
                    '{"availability":"healthy","memory_bytes":128,"client_connections":2,'
                    '"slowlog_count":0,"observed_at":"2026-09-04T00:00:00+00:00",'
                    '"source_status":"available"}'
                ),
            }
        ],
        tools=tools,
    )
    assert first["tool_calls"][0]["function"] == {
        "name": "redis_health_overview",
        "arguments": "{}",
    }
    assert second["content"].startswith("只读健康事实：")
    assert "memory_bytes" in second["content"]


def test_scripted_driver_selects_postgres_health_not_first_legacy_tool() -> None:
    driver = DeterministicLocalDriver("check_connection_pool")
    tools = [
        {"function": {"name": "explain_sql"}},
        {"function": {"name": "check_connection_pool"}},
    ]
    first = driver.chat([], tools=tools)
    assert first["tool_calls"][0]["function"] == {
        "name": "check_connection_pool",
        "arguments": "{}",
    }


def test_scripted_driver_rejects_malformed_or_extra_service_fact() -> None:
    driver = DeterministicLocalDriver("redis_health_overview")
    tools = [{"function": {"name": "redis_health_overview"}}]
    driver.chat([], tools=tools)
    with pytest.raises(PreflightSafeStop, match="P12_TOOL_FACT_MALFORMED"):
        driver.chat(
            [{"role": "tool", "content": '{"availability":"healthy","key":"secret"}'}],
            tools=tools,
        )


def test_runner_maps_unexpected_exception_without_leaking_text(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(runner, "run_acceptance", lambda: (_ for _ in ()).throw(RuntimeError("secret-dsn")))
    assert runner.main() == 3
    output = capsys.readouterr()
    assert output.out.strip() == "P12 acceptance stopped: P12_RUNTIME_FAILED"
    assert output.err == ""
    assert "secret-dsn" not in output.out


class _RunnerRedisConnector:
    def __init__(self, *, origin_ref: str = "registry:redis.test") -> None:
        self.health_reads = 0
        self._origin = BindingOrigin.from_reference(origin_ref)

    def definition(self) -> ServiceDefinitionData:
        return ServiceDefinitionData(
            id="redis.test",
            title="Runner Redis",
            kind="redis",
            supported_investigations=(
                ServiceInvestigationData(
                    id=SERVICE_HEALTH_PRESSURE_INTENT_ID,
                    title="Redis 健康调查",
                    description="固定只读标量",
                    default_query=SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
                ),
            ),
            action_boundary="只读固定指标",
            session_title="Redis 健康调查",
            has_dsn=True,
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        self.health_reads += 1
        return ServiceSnapshotData(
            observed_at=datetime.now(UTC),
            mode=ServiceMode.TARGET,
            availability=ServiceAvailability.HEALTHY,
            performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
            server_metrics=ServiceServerMetricsData(
                source_status=ServiceSourceStatus.AVAILABLE,
                memory_bytes=128,
                client_connections=2,
                slowlog_count=0,
            ),
            database=ServiceDatabaseStateData(
                source_status=ServiceSourceStatus.AVAILABLE,
                signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
            ),
        )

    def agent_health_snapshot(self) -> ServiceSnapshotData:
        return self.health_snapshot()

    def agent_capability(self):
        return self

    def capability_kind(self) -> str:
        return "redis"

    def binding_origin(self) -> BindingOrigin:
        return self._origin


def _offline_runtime_loader(tmp_path, connector, tool_menus):
    runtime = create_persistence_runtime(f"sqlite:///{(tmp_path / 'runner.sqlite3').as_posix()}")
    Base.metadata.create_all(runtime.engine)

    def load(_preflight, expected_tool):
        def coordinator_factory(service_id, binding):
            coordinator = build_coordinator(
                DeterministicLocalDriver(expected_tool),
                service_id=service_id,
                binding=binding,
            )
            db_agent = coordinator.agents["db"]
            active_tools = db_agent._tool_registry_for_query(SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY)
            tool_menus.append([item["function"]["name"] for item in active_tools.get_schemas()])
            return coordinator

        services = build_v1_services_for_runtime(runtime, coordinator_factory)
        assert services.service_registry is not None
        services.service_registry.register(connector)
        return runtime, services

    return runtime, load


def test_runner_executes_full_orchestration_offline(tmp_path) -> None:
    connector = _RunnerRedisConnector()
    tool_menus: list[list[str]] = []
    runtime, loader = _offline_runtime_loader(tmp_path, connector, tool_menus)
    try:
        result = run_acceptance(
            _environment(),
            stdin=SimpleNamespace(isatty=lambda: True),
            input_fn=lambda _prompt: "redis.test",
            runtime_loader=loader,
        )
    finally:
        runtime.engine.dispose()

    assert result["service_id"] == "redis.test"
    assert result["kind"] == "redis"
    assert result["terminal_status"] == "succeeded"
    assert result["model_source"] == "deterministic_local_driver"
    assert result["service_fact_source"] == "registry_binding"
    assert connector.health_reads == 2  # connection test + Agent Tool
    assert tool_menus == [["redis_health_overview"]]


def test_runner_rejects_origin_mismatch_before_connection_test(tmp_path) -> None:
    connector = _RunnerRedisConnector(origin_ref="registry:other")
    tool_menus: list[list[str]] = []
    runtime, loader = _offline_runtime_loader(tmp_path, connector, tool_menus)
    try:
        with pytest.raises(PreflightSafeStop) as captured:
            run_acceptance(
                _environment(),
                stdin=SimpleNamespace(isatty=lambda: True),
                input_fn=lambda _prompt: "redis.test",
                runtime_loader=loader,
            )
    finally:
        runtime.engine.dispose()

    assert captured.value.code == "P12_BINDING_ORIGIN_MISMATCH"
    assert connector.health_reads == 0
    assert tool_menus == []
