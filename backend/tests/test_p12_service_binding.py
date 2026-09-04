"""P12 唯一 Registry binding 的确定性契约。"""

from datetime import UTC, datetime
from threading import Event, Thread

import pytest
from data.scenarios import get_active_scenario, set_active_scenario

from src.core.bootstrap import build_llm_from_config
from src.domain.services import (
    BindingOrigin,
    DatabaseSignal,
    PerformanceSignal,
    ServiceAvailability,
    ServiceBindingError,
    ServiceBindingFailureCode,
    ServiceDatabaseStateData,
    ServiceDefinitionData,
    ServiceInvestigationData,
    ServiceMode,
    ServiceRegistry,
    ServiceServerMetricsData,
    ServiceSnapshotData,
    ServiceSourceStatus,
    validate_service_instance_id,
)


class _Connector:
    def __init__(self, service_id: str = "pg.dynamic", kind: str = "postgres") -> None:
        self.service_id = service_id
        self.kind = kind

    def definition(self) -> ServiceDefinitionData:
        return ServiceDefinitionData(
            id=self.service_id,
            title="测试服务",
            kind=self.kind,
            supported_investigations=(
                ServiceInvestigationData(
                    id="service_health_pressure.v1",
                    title="健康调查",
                    description="固定健康调查",
                    default_query="检查健康状态",
                ),
                ServiceInvestigationData(
                    id="postgres_slow_query.v1",
                    title="慢查询",
                    description="固定只读调查",
                    default_query="检查慢查询",
                ),
            ),
            action_boundary="只读",
            session_title="健康调查",
            has_dsn=True,
        )

    def health_snapshot(self) -> ServiceSnapshotData:
        return ServiceSnapshotData(
            observed_at=datetime.now(UTC),
            mode=ServiceMode.MOCK,
            availability=ServiceAvailability.HEALTHY,
            performance_signal=PerformanceSignal.NO_SLOW_QUERY_DETECTED,
            server_metrics=ServiceServerMetricsData(source_status=ServiceSourceStatus.AVAILABLE),
            database=ServiceDatabaseStateData(
                source_status=ServiceSourceStatus.AVAILABLE,
                signal=DatabaseSignal.NO_SLOW_QUERY_DETECTED,
            ),
        )

    def agent_capability(self) -> object:
        return self

    def capability_kind(self) -> str:
        return self.kind

    def agent_health_snapshot(self) -> ServiceSnapshotData:
        return self.health_snapshot()

    def explain_select(self, sql: str) -> str:
        raise AssertionError(sql)

    def show_indexes(self, table: str) -> str:
        raise AssertionError(table)

    def show_create_table(self, table: str) -> str:
        raise AssertionError(table)

    def check_locks(self) -> str:
        raise AssertionError("binding 测试不应打开连接")

    def binding_origin(self) -> BindingOrigin:
        return BindingOrigin.from_reference(f"registry:{self.service_id}")


def test_binding_is_derived_from_the_same_connector_entry() -> None:
    connector = _Connector()
    binding = ServiceRegistry((connector,)).resolve_binding(
        "pg.dynamic",
        expected_kind="postgres",
        investigation_id="service_health_pressure.v1",
    )

    assert binding.capability is connector
    assert binding.for_agent().service_id == "pg.dynamic"
    assert not hasattr(binding.for_agent(), "origin")


@pytest.mark.parametrize(
    ("service_id", "kind", "investigation"),
    [
        ("missing", None, None),
        ("pg.dynamic", "redis", None),
        ("pg.dynamic", None, "unknown.v1"),
    ],
)
def test_binding_mismatch_fails_closed(service_id: str, kind: str | None, investigation: str | None) -> None:
    registry = ServiceRegistry((_Connector(),))
    with pytest.raises(ServiceBindingError):
        registry.resolve_binding(service_id, expected_kind=kind, investigation_id=investigation)


def test_poison_isolated_to_one_service_id() -> None:
    registry = ServiceRegistry((_Connector("pg.one"), _Connector("pg.two")))
    registry.poison("pg.one")

    with pytest.raises(ServiceBindingError) as captured:
        registry.resolve_binding("pg.one")
    assert captured.value.code is ServiceBindingFailureCode.POISONED
    assert registry.resolve_binding("pg.two").service_id == "pg.two"
    assert registry.get_connector("pg.one") is None
    assert "pg.one" not in registry.service_ids()
    assert [item.definition().id for item in registry.list_connectors()] == ["pg.two"]


class _WrongProfileConnector(_Connector):
    def definition(self) -> ServiceDefinitionData:
        definition = super().definition()
        return definition.model_copy(update={"supported_investigations": definition.supported_investigations[:1]})


def test_registry_rejects_capability_profile_drift_before_exposure() -> None:
    with pytest.raises(ValueError, match="profile"):
        ServiceRegistry((_WrongProfileConnector(),))


def test_binding_failure_codes_are_closed_and_credential_aware() -> None:
    registry = ServiceRegistry((_Connector(),))
    cases = [
        ("missing", None, None, ServiceBindingFailureCode.NOT_FOUND),
        ("pg.dynamic", "redis", None, ServiceBindingFailureCode.TYPE_MISMATCH),
        (
            "pg.dynamic",
            None,
            "unknown.v1",
            ServiceBindingFailureCode.INVESTIGATION_NOT_SUPPORTED,
        ),
    ]
    for service_id, kind, investigation, expected in cases:
        with pytest.raises(ServiceBindingError) as captured:
            registry.resolve_binding(
                service_id,
                expected_kind=kind,
                investigation_id=investigation,
            )
        assert captured.value.code is expected

    unconfigured = _Connector("pg.empty")
    original_definition = unconfigured.definition
    unconfigured.definition = lambda: original_definition().model_copy(update={"has_dsn": False})  # type: ignore[method-assign]
    with pytest.raises(ServiceBindingError) as captured:
        ServiceRegistry((unconfigured,)).resolve_binding("pg.empty")
    assert captured.value.code is ServiceBindingFailureCode.CREDENTIAL_UNAVAILABLE


def test_full_projection_waits_for_mutation_epoch_but_other_id_get_does_not() -> None:
    registry = ServiceRegistry((_Connector("pg.one"), _Connector("pg.two")))
    mutation_entered = Event()
    release_mutation = Event()
    list_finished = Event()

    def mutate() -> None:
        with registry.mutation_guard("pg.one"):
            mutation_entered.set()
            release_mutation.wait(2)

    def read_all() -> None:
        registry.list_connectors()
        list_finished.set()

    writer = Thread(target=mutate)
    writer.start()
    assert mutation_entered.wait(1)
    reader = Thread(target=read_all)
    reader.start()
    assert not list_finished.wait(0.05)
    assert registry.get_connector("pg.two") is not None
    release_mutation.set()
    writer.join(1)
    reader.join(1)
    assert list_finished.is_set()


@pytest.mark.parametrize("value", ["1mysql", "pg.orders", "redis_cache", "mysql-local"])
def test_shared_service_id_validator_accepts_existing_grammar(value: str) -> None:
    assert validate_service_instance_id(value) == value


@pytest.mark.parametrize("value", ["", "Upper", "bad/value", "x" * 65])
def test_shared_service_id_validator_rejects_invalid_values(value: str) -> None:
    with pytest.raises(ValueError):
        validate_service_instance_id(value)


def test_model_mode_does_not_switch_service_fact_scenario() -> None:
    set_active_scenario("S2")
    original = get_active_scenario()

    build_llm_from_config(
        {"llm": {"api_key": "mock", "base_url": "http://mock", "model": "mock"}},
        manage_legacy_scenario=False,
    )
    assert get_active_scenario() is original

    build_llm_from_config(
        {"llm": {"api_key": "placeholder", "base_url": "https://provider.invalid", "model": "model"}},
        manage_legacy_scenario=False,
    )
    assert get_active_scenario() is original
