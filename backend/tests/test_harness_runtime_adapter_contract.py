"""P10 S2 Runtime Adapter、当前 DiagnosisExecutor 与 ToolGateway 契约测试。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.application.contracts import DiagnosisExecutionError, DiagnosisExecutionResult
from src.application.runtime_contracts import (
    RuntimeCapability,
    RuntimeCapabilityStatus,
    RuntimeControl,
    RuntimeEventSignal,
    RuntimeExecutionRequest,
    RuntimeFailureSignal,
    RuntimeResultSignal,
    RuntimeSignal,
)
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import Tool, ToolRegistry
from src.domain.harness_contracts import (
    CONTRACT_VERSION_V1,
    FailureCodeId,
    FailureCodeValue,
    FencingToken,
    HarnessIdentity,
)
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor
from tests.support.harness_contracts import (
    CurrentCoordinatorProbeFactory,
    CurrentDiagnosisExecutorCompatibilityAdapter,
    DiagnosisExecutorCompatibilityProbe,
    ReferenceRuntimeAdapter,
    ReferenceScenario,
    ReviewedCapabilityFixture,
    ScriptedRuntimeAdapter,
    StaticRuntimeControl,
    ToolGatewayCompatibilityProbe,
    ToolGatewayFact,
    ToolGatewayFactStatus,
    compare_observed_to_reviewed,
    fixed_execution_uuid,
    run_reference_contract,
)

PROFILE_PATH = Path(__file__).parent / "fixtures" / "harness" / "current_capability_profile.v1.json"
FIXED_DEADLINE = datetime(2026, 9, 1, 0, 5, tzinfo=UTC)


def _request() -> RuntimeExecutionRequest:
    return RuntimeExecutionRequest(
        execution_id=HarnessIdentity(namespace="runtime.execution", value=fixed_execution_uuid()),
        contract_version=CONTRACT_VERSION_V1,
        query="检查订单服务",
        service_id="postgres-staging",
        deadline_at=FIXED_DEADLINE,
    )


@pytest.mark.parametrize(
    ("scenario", "terminal_type", "failure_code"),
    [
        (ReferenceScenario.RESULT, RuntimeResultSignal, None),
        (
            ReferenceScenario.FAILURE,
            RuntimeFailureSignal,
            FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION,
        ),
        (
            ReferenceScenario.UNSUPPORTED,
            RuntimeFailureSignal,
            FailureCodeId.RUNTIME_UNSUPPORTED_CAPABILITY,
        ),
    ],
)
def test_reference_adapter正常失败与不支持能力完整通过contract(
    scenario: ReferenceScenario,
    terminal_type: type[RuntimeResultSignal] | type[RuntimeFailureSignal],
    failure_code: FailureCodeId | None,
) -> None:
    adapter = ReferenceRuntimeAdapter(scenario)
    control = StaticRuntimeControl()
    request = _request()

    signals = run_reference_contract(adapter, request, control)

    assert adapter.last_request == request
    assert isinstance(signals[-1], terminal_type)
    if failure_code is not None:
        terminal = signals[-1]
        assert isinstance(terminal, RuntimeFailureSignal)
        assert terminal.code.code is failure_code
    assert control.cancel_checks == 1
    assert control.remaining_checks == 1
    profile = adapter.capabilities()
    service_context = profile.declaration_for(RuntimeCapability.SERVICE_CONTEXT)
    if scenario is ReferenceScenario.UNSUPPORTED:
        assert service_context.status is RuntimeCapabilityStatus.UNSUPPORTED
        assert service_context.gap_id == "reference.service_context_unsupported"
    else:
        assert all(
            item.status is RuntimeCapabilityStatus.SUPPORTED and item.gap_id is None
            for item in profile.capabilities
        )


@pytest.mark.parametrize(
    ("control", "failure_code"),
    [
        (StaticRuntimeControl(cancel_requested=True), FailureCodeId.CANCEL_REQUESTED),
        (StaticRuntimeControl(remaining=0), FailureCodeId.TOOL_TIMEOUT),
    ],
)
def test_reference_adapter读取取消和deadline并返回typed_failure(
    control: StaticRuntimeControl,
    failure_code: FailureCodeId,
) -> None:
    signals = run_reference_contract(ReferenceRuntimeAdapter(), _request(), control)

    assert len(signals) == 1
    assert isinstance(signals[0], RuntimeFailureSignal)
    assert signals[0].code.code is failure_code


def test_reference_adapter完整观察request字段且不混入fencing权限语义() -> None:
    request = _request()
    adapter = ReferenceRuntimeAdapter()
    fencing = FencingToken(value="42345678-1234-5678-9234-567812345678")

    run_reference_contract(adapter, request, StaticRuntimeControl())

    assert adapter.last_request is request
    assert adapter.last_request.execution_id == request.execution_id
    assert adapter.last_request.query == "检查订单服务"
    assert adapter.last_request.service_id == "postgres-staging"
    assert adapter.last_request.deadline_at == FIXED_DEADLINE
    assert "fencing" not in request.model_dump(mode="json")
    assert fencing.value != request.execution_id.value


def _event_signal() -> RuntimeEventSignal:
    signals = run_reference_contract(ReferenceRuntimeAdapter(), _request(), StaticRuntimeControl())
    event = signals[0]
    assert isinstance(event, RuntimeEventSignal)
    return event


def _result_signal() -> RuntimeResultSignal:
    signals = run_reference_contract(ReferenceRuntimeAdapter(), _request(), StaticRuntimeControl())
    result = signals[-1]
    assert isinstance(result, RuntimeResultSignal)
    return result


@pytest.mark.parametrize(
    ("signals", "category"),
    [
        ([], "terminal_cardinality"),
        ([_result_signal(), _result_signal()], "terminal_after_output"),
        ([_result_signal(), _event_signal()], "terminal_after_output"),
    ],
)
def test_reference_contract拒绝零多终止及终止后事件(
    signals: list[RuntimeEventSignal | RuntimeResultSignal],
    category: str,
) -> None:
    adapter = ScriptedRuntimeAdapter(signals)

    with pytest.raises(AssertionError, match=category):
        run_reference_contract(adapter, _request(), StaticRuntimeControl())


class _UntypedExceptionRuntimeAdapter(ReferenceRuntimeAdapter):
    def stream(
        self,
        request: RuntimeExecutionRequest,
        control: RuntimeControl,
    ) -> Iterator[RuntimeSignal]:
        del request, control
        raise RuntimeError("test-only raw runtime exception")
        yield RuntimeResultSignal(
            contract_version=CONTRACT_VERSION_V1,
            result=DiagnosisExecutionResult(),
        )


def test_reference_contract拒绝未转typed_failure的意外异常() -> None:
    with pytest.raises(AssertionError, match=r"runtime\.stream\.untyped_exception"):
        run_reference_contract(
            _UntypedExceptionRuntimeAdapter(),
            _request(),
            StaticRuntimeControl(),
        )


@pytest.mark.parametrize(
    "unsafe_message",
    [
        "password=unit-test-secret raw exception",
        "API key " + "s" + "k-review123456",
        "postgresql://review-user:review-pass@localhost/review-db",
        r"无法读取 C:\review\secret.txt",
        "无法读取 /var/tmp/review-secret.txt",
        "SELECT * FROM review_table",
        "system prompt: test-only instructions",
        "chain-of-thought: test-only reasoning",
        "raw tool output: test-only payload",
    ],
)
def test_reference_contract拒绝安全约束禁止的typed_failure_message(unsafe_message: str) -> None:
    unsafe_failure = RuntimeFailureSignal(
        contract_version=CONTRACT_VERSION_V1,
        code=FailureCodeValue(
            contract_version=CONTRACT_VERSION_V1,
            code=FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION,
        ),
        message=unsafe_message,
    )

    with pytest.raises(AssertionError, match=r"runtime\.stream\.failure_message_safety"):
        run_reference_contract(
            ScriptedRuntimeAdapter([unsafe_failure]),
            _request(),
            StaticRuntimeControl(),
        )


def test_current_diagnosis_executor_observed_profile精确匹配reviewed_expected() -> None:
    reviewed = ReviewedCapabilityFixture.model_validate_json(PROFILE_PATH.read_text(encoding="utf-8"))
    observed = DiagnosisExecutorCompatibilityProbe(_request()).observe()
    tool_gateway_observed = ToolGatewayCompatibilityProbe().observe()

    compare_observed_to_reviewed(observed, tool_gateway_observed, reviewed)
    assert reviewed.profile_version == 1
    assert set(reviewed.capabilities) == set(RuntimeCapability)
    assert set(reviewed.tool_gateway_facts) == set(ToolGatewayFact)


@pytest.mark.parametrize("mutation", ["status", "gap", "locator", "unknown_key"])
def test_profile比较拒绝声明失真未知gap与证据漂移(mutation: str) -> None:
    reviewed = ReviewedCapabilityFixture.model_validate_json(PROFILE_PATH.read_text(encoding="utf-8"))
    observed = DiagnosisExecutorCompatibilityProbe(_request()).observe()
    tool_gateway_observed = ToolGatewayCompatibilityProbe().observe()

    if mutation == "unknown_key":
        observed.pop(RuntimeCapability.QUERY)
    else:
        capability = RuntimeCapability.DEADLINE
        current = observed[capability]
        if mutation == "status":
            observed[capability] = current.model_copy(update={"status": RuntimeCapabilityStatus.SUPPORTED})
        elif mutation == "gap":
            observed[capability] = current.model_copy(update={"gap_id": "unknown.gap"})
        else:
            observed[capability] = current.model_copy(
                update={"evidence": current.evidence.model_copy(update={"locator": "drifted.locator"})}
            )

    with pytest.raises(AssertionError, match="capability_profile"):
        compare_observed_to_reviewed(observed, tool_gateway_observed, reviewed)


@pytest.mark.parametrize("mutation", ["status", "gap", "locator", "unknown_key"])
def test_toolgateway_profile比较拒绝事实声明与证据漂移(mutation: str) -> None:
    reviewed = ReviewedCapabilityFixture.model_validate_json(PROFILE_PATH.read_text(encoding="utf-8"))
    observed = DiagnosisExecutorCompatibilityProbe(_request()).observe()
    tool_gateway_observed = ToolGatewayCompatibilityProbe().observe()

    if mutation == "unknown_key":
        tool_gateway_observed.pop(ToolGatewayFact.UNREGISTERED)
    else:
        fact = ToolGatewayFact.TIMEOUT
        current = tool_gateway_observed[fact]
        if mutation == "status":
            tool_gateway_observed[fact] = current.model_copy(
                update={"status": ToolGatewayFactStatus.GUARANTEED}
            )
        elif mutation == "gap":
            tool_gateway_observed[fact] = current.model_copy(update={"gap_id": "unknown.gap"})
        else:
            tool_gateway_observed[fact] = current.model_copy(
                update={"evidence": current.evidence.model_copy(update={"locator": "drifted.locator"})}
            )

    with pytest.raises(AssertionError, match=r"tool_gateway\.capability_profile"):
        compare_observed_to_reviewed(observed, tool_gateway_observed, reviewed)


class _UnsafeFailureExecutor:
    def stream(
        self,
        query: str,
        service_id: str | None = None,
    ) -> Iterator[DiagnosisExecutionResult]:
        del query, service_id
        raise DiagnosisExecutionError(
            code="UNSAFE_TEST_FAILURE",
            message="password=unit-test-secret traceback detail",
        )
        yield DiagnosisExecutionResult()


def test_current_compatibility_wrapper映射typed_failure且不暴露原始错误() -> None:
    signals = list(
        CurrentDiagnosisExecutorCompatibilityAdapter(_UnsafeFailureExecutor()).stream(
            _request(),
            StaticRuntimeControl(),
        )
    )

    assert len(signals) == 1
    assert isinstance(signals[0], RuntimeFailureSignal)
    serialized = signals[0].model_dump_json()
    assert signals[0].code.code is FailureCodeId.MODEL_EXECUTION_FAILED
    assert "unit-test-secret" not in serialized
    assert "traceback detail" not in serialized


class _FakeCoordinator:
    def route_stream(self, query: str) -> Iterator[dict[str, object]]:
        assert query == "检查订单服务"
        yield {"kind": "complete", "result": "安全报告", "strategy": "direct", "trace": []}


def test_current_coordinator_executor通过兼容wrapper映射service_context() -> None:
    seen_services: list[str | None] = []

    def factory(service_id: str | None) -> _FakeCoordinator:
        seen_services.append(service_id)
        return _FakeCoordinator()

    signals = list(
        CurrentDiagnosisExecutorCompatibilityAdapter(CoordinatorDiagnosisExecutor(factory)).stream(
            _request(),
            StaticRuntimeControl(),
        )
    )

    assert seen_services == ["postgres-staging"]
    assert len(signals) == 1
    assert isinstance(signals[0], RuntimeResultSignal)


def test_current_port意外异常与terminal_cardinality如实保留expected_gap() -> None:
    factory = CurrentCoordinatorProbeFactory()
    with pytest.raises(RuntimeError, match="test-only unexpected exception"):
        list(
            CurrentDiagnosisExecutorCompatibilityAdapter(
                factory.create("unexpected")
            ).stream(_request(), StaticRuntimeControl())
        )

    empty = list(
        CurrentDiagnosisExecutorCompatibilityAdapter(
            factory.create("empty")
        ).stream(_request(), StaticRuntimeControl())
    )
    multiple = list(
        CurrentDiagnosisExecutorCompatibilityAdapter(
            factory.create("multiple_results")
        ).stream(_request(), StaticRuntimeControl())
    )
    assert empty == []
    assert len(multiple) == 2
    assert all(isinstance(item, RuntimeResultSignal) for item in multiple)


class _CountingTool(Tool):
    def __init__(self) -> None:
        super().__init__(
            name="counting",
            description="S2 参数与准入测试工具",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
        )
        self.executions = 0

    def execute(self, text: str) -> str:
        self.executions += 1
        return text


class _UnsafeTool(Tool):
    def __init__(self, *, raises: bool) -> None:
        super().__init__(name="unsafe", description="S2 安全失败工具", parameters={"type": "object"})
        self._raises = raises

    def execute(self) -> str:
        if self._raises:
            raise RuntimeError("password=unit-test-secret raw exception")
        return "password=unit-test-secret"


@pytest.mark.parametrize(
    ("name", "arguments"),
    [
        ("missing", "{}"),
        ("counting", "{bad"),
        ("counting", "[]"),
        ("counting", "{}"),
        ("counting", json.dumps({"text": 7})),
    ],
)
def test_toolgateway拒绝非法请求且拒绝时不执行tool(name: str, arguments: str) -> None:
    registry = ToolRegistry()
    tool = _CountingTool()
    registry.register(tool)
    gateway = ToolGateway(registry)
    try:
        result = gateway.invoke(name, arguments)
    finally:
        gateway.shutdown()

    assert result.record.status == "rejected"
    assert tool.executions == 0


def test_toolgateway允许请求只执行一次并返回安全记录() -> None:
    registry = ToolRegistry()
    tool = _CountingTool()
    registry.register(tool)
    gateway = ToolGateway(registry)
    try:
        result = gateway.invoke("counting", json.dumps({"text": "allowed"}))
    finally:
        gateway.shutdown()

    assert tool.executions == 1
    assert result.output == "allowed"
    assert result.record.status == "ok"
    assert result.record.tool == "counting"
    assert result.record.duration_ms >= 0


@pytest.mark.parametrize("raises", [False, True])
def test_toolgateway脱敏输出并把异常映射为中性失败(raises: bool) -> None:
    registry = ToolRegistry()
    registry.register(_UnsafeTool(raises=raises))
    gateway = ToolGateway(registry)
    try:
        result = gateway.invoke("unsafe", "{}")
    finally:
        gateway.shutdown()

    serialized = result.model_dump_json()
    assert "unit-test-secret" not in serialized
    assert "raw exception" not in serialized
    assert result.record.status == ("error" if raises else "ok")


def test_toolgateway_timeout只声明等待超时不声明底层副作用停止() -> None:
    observed = ToolGatewayCompatibilityProbe().observe()
    timeout_fact = observed[ToolGatewayFact.TIMEOUT]

    assert timeout_fact.status is ToolGatewayFactStatus.EXPECTED_GAP
    assert timeout_fact.gap_id == "tool_gateway.timeout_does_not_cancel_execution"
    assert "只保证等待超时" in timeout_fact.evidence.assertion
