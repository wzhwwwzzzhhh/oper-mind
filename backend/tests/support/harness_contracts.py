"""P10 S2 Runtime Adapter reference 与当前端口兼容性测试支持。"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime
from enum import StrEnum
from inspect import signature
from threading import Event
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.application.contracts import (
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
    DiagnosisExecutor,
)
from src.application.runtime_contracts import (
    RuntimeAdapterContract,
    RuntimeCapability,
    RuntimeCapabilityDeclaration,
    RuntimeCapabilityProfile,
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
from src.domain.diagnosis import RunEventType
from src.domain.harness_contracts import (
    CONTRACT_VERSION_V1,
    ContractVersion,
    FailureCodeId,
    FailureCodeValue,
)
from src.infrastructure.diagnosis.coordinator_executor import CoordinatorDiagnosisExecutor

FIXED_OCCURRED_AT = datetime(2026, 9, 1, 0, 0, tzinfo=UTC)


class CapabilityEvidence(BaseModel):
    """Reviewed/observed profile 中的稳定证据定位。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    kind: Literal["behavior_probe", "signature_probe", "contract_wrapper"]
    locator: str = Field(min_length=1, max_length=200)
    assertion: str = Field(min_length=1, max_length=300)


class ExpectedCapability(BaseModel):
    """版本化 fixture 中单项能力的 reviewed expectation。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_status: RuntimeCapabilityStatus
    gap_id: str | None = Field(default=None, min_length=1, max_length=120)
    evidence: CapabilityEvidence

    @model_validator(mode="after")
    def _validate_gap(self) -> Self:
        needs_gap = self.expected_status in {
            RuntimeCapabilityStatus.EXTERNALIZED,
            RuntimeCapabilityStatus.UNSUPPORTED,
        }
        if needs_gap != (self.gap_id is not None):
            raise ValueError("externalized/unsupported expectation 必须且仅能携带 gap_id")
        return self


class ToolGatewayFact(StrEnum):
    """Design §6.1 固定的 ToolGateway 当前行为事实。"""

    UNREGISTERED = "unregistered"
    INVALID_ARGUMENTS = "invalid_arguments"
    SUCCESS = "success"
    SENSITIVE_OUTPUT = "sensitive_output"
    TIMEOUT = "timeout"
    EXCEPTION = "exception"


class ToolGatewayFactStatus(StrEnum):
    """ToolGateway 事实是当前保证，或需如实保留的 expected gap。"""

    GUARANTEED = "guaranteed"
    EXPECTED_GAP = "expected_gap"


class ExpectedToolGatewayFact(BaseModel):
    """版本化 fixture 中单项 ToolGateway reviewed expectation。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    expected_status: ToolGatewayFactStatus
    gap_id: str | None = Field(default=None, min_length=1, max_length=120)
    evidence: CapabilityEvidence

    @model_validator(mode="after")
    def _validate_gap(self) -> Self:
        needs_gap = self.expected_status is ToolGatewayFactStatus.EXPECTED_GAP
        if needs_gap != (self.gap_id is not None):
            raise ValueError("expected_gap ToolGateway fact 必须且仅能携带 gap_id")
        return self


class ReviewedCapabilityFixture(BaseModel):
    """current_capability_profile.vN.json 的封闭 schema。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    contract_version: ContractVersion
    profile_version: int = Field(ge=1, strict=True)
    capabilities: dict[RuntimeCapability, ExpectedCapability]
    tool_gateway_facts: dict[ToolGatewayFact, ExpectedToolGatewayFact]

    @model_validator(mode="after")
    def _validate_complete_profile(self) -> Self:
        self.contract_version.require_exact(CONTRACT_VERSION_V1)
        if set(self.capabilities) != set(RuntimeCapability):
            raise ValueError("reviewed fixture 必须精确覆盖 v1 完整能力集合")
        if set(self.tool_gateway_facts) != set(ToolGatewayFact):
            raise ValueError("reviewed fixture 必须精确覆盖 Design §6.1 ToolGateway 事实集合")
        return self


class ObservedCapability(BaseModel):
    """由实际调用或签名探针推导的能力事实。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: RuntimeCapabilityStatus
    gap_id: str | None = None
    evidence: CapabilityEvidence


class ObservedToolGatewayFact(BaseModel):
    """由实际 ToolGateway 调用推导的当前边界事实。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: ToolGatewayFactStatus
    gap_id: str | None = None
    evidence: CapabilityEvidence


class StaticRuntimeControl:
    """记录 reference / compatibility Adapter 是否读取控制信号。"""

    def __init__(self, *, cancel_requested: bool = False, remaining: float = 60.0) -> None:
        self._cancel_requested = cancel_requested
        self._remaining = remaining
        self.cancel_checks = 0
        self.remaining_checks = 0

    def is_cancel_requested(self) -> bool:
        self.cancel_checks += 1
        return self._cancel_requested

    def remaining_seconds(self) -> float:
        self.remaining_checks += 1
        return self._remaining


class ReferenceScenario(StrEnum):
    """Reference Adapter 的确定性终止场景。"""

    RESULT = "result"
    FAILURE = "failure"
    UNSUPPORTED = "unsupported"


def _failure_signal(code: FailureCodeId, message: str) -> RuntimeFailureSignal:
    return RuntimeFailureSignal(
        contract_version=CONTRACT_VERSION_V1,
        code=FailureCodeValue(contract_version=CONTRACT_VERSION_V1, code=code),
        message=message,
    )


class ReferenceRuntimeAdapter(RuntimeAdapterContract):
    """完整遵守目标协议的离线 reference Adapter。"""

    def __init__(self, scenario: ReferenceScenario = ReferenceScenario.RESULT) -> None:
        self._scenario = scenario
        self.last_request: RuntimeExecutionRequest | None = None

    def capabilities(self) -> RuntimeCapabilityProfile:
        return RuntimeCapabilityProfile(
            contract_version=CONTRACT_VERSION_V1,
            profile_version=1,
            capabilities=tuple(
                RuntimeCapabilityDeclaration(
                    capability=capability,
                    status=(
                        RuntimeCapabilityStatus.UNSUPPORTED
                        if self._scenario is ReferenceScenario.UNSUPPORTED
                        and capability is RuntimeCapability.SERVICE_CONTEXT
                        else RuntimeCapabilityStatus.SUPPORTED
                    ),
                    gap_id=(
                        "reference.service_context_unsupported"
                        if self._scenario is ReferenceScenario.UNSUPPORTED
                        and capability is RuntimeCapability.SERVICE_CONTEXT
                        else None
                    ),
                )
                for capability in RuntimeCapability
            ),
        )

    def stream(
        self,
        request: RuntimeExecutionRequest,
        control: RuntimeControl,
    ) -> Iterator[RuntimeSignal]:
        request.contract_version.require_exact(CONTRACT_VERSION_V1)
        self.last_request = request
        if control.is_cancel_requested():
            yield _failure_signal(FailureCodeId.CANCEL_REQUESTED, "执行已按请求取消")
            return
        if control.remaining_seconds() <= 0:
            yield _failure_signal(FailureCodeId.TOOL_TIMEOUT, "执行期限已到")
            return
        if self._scenario is ReferenceScenario.FAILURE:
            yield _failure_signal(FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION, "运行失败")
            return
        if self._scenario is ReferenceScenario.UNSUPPORTED:
            yield _failure_signal(FailureCodeId.RUNTIME_UNSUPPORTED_CAPABILITY, "请求的能力未受支持")
            return
        yield RuntimeEventSignal(
            contract_version=CONTRACT_VERSION_V1,
            event=DiagnosisExecutionEvent(
                type=RunEventType.ROUTE_DECIDED,
                node="reference",
                occurred_at=FIXED_OCCURRED_AT,
                data={"status": "running"},
            ),
        )
        yield RuntimeResultSignal(
            contract_version=CONTRACT_VERSION_V1,
            result=DiagnosisExecutionResult(strategy="reference", report="reference result"),
        )


class ScriptedRuntimeAdapter(RuntimeAdapterContract):
    """刻意产生给定 signal 序列的负向 conformance 测试桩。"""

    def __init__(self, signals: Sequence[RuntimeSignal]) -> None:
        self._signals = tuple(signals)

    def capabilities(self) -> RuntimeCapabilityProfile:
        return ReferenceRuntimeAdapter().capabilities()

    def stream(
        self,
        request: RuntimeExecutionRequest,
        control: RuntimeControl,
    ) -> Iterator[RuntimeSignal]:
        del request, control
        yield from self._signals


_UNSAFE_FAILURE_MESSAGE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"(?i)\b(password|passwd|pwd|token|secret|api[_-]?key)\b\s*[=:]\s*\S+"),
    re.compile(r"(?i)\bs[k]-[a-z0-9_-]{6,}\b"),
    re.compile(r"(?i)\b[a-z][a-z0-9+.-]*://[^\s/@:]+:[^@\s]+@[^\s]+"),
    re.compile(r"(?i)(?:\b[a-z]:\\|\\\\)[^\s]+"),
    re.compile(r"(?<![\w/])/(?:[^/\s]+/)*[^/\s]+"),
    re.compile(
        r"(?is)\b(?:select|insert|update|delete|alter|drop|create|truncate|merge|grant|revoke)\b\s+\S+"
    ),
    re.compile(r"(?i)\b(traceback|stack trace|raw exception)\b"),
    re.compile(r"(?i)\b(?:chain[- ]of[- ]thought|c[o]t|system prompt|developer prompt|user prompt)\b"),
    re.compile(r"(?i)\braw tool output\b"),
    re.compile(r"(?i)\b(?:file|line)\s+\"[^\"]+\""),
)


def _assert_failure_message_safe(message: str) -> None:
    if any(pattern.search(message) for pattern in _UNSAFE_FAILURE_MESSAGE_PATTERNS):
        raise AssertionError(
            "runtime.stream.failure_message_safety：typed failure message 包含敏感值或原始异常详情"
        )


def assert_runtime_signal_sequence(signals: Sequence[RuntimeSignal]) -> None:
    """断言零到多个 event 后恰有一个终止 signal，且终止后无输出。"""

    terminal_seen = False
    terminal_count = 0
    for signal in signals:
        if terminal_seen:
            raise AssertionError("runtime.stream.terminal_after_output：终止 signal 后仍有输出")
        if isinstance(signal, RuntimeEventSignal):
            continue
        if isinstance(signal, RuntimeFailureSignal):
            _assert_failure_message_safe(signal.message)
            terminal_seen = True
            terminal_count += 1
            continue
        if isinstance(signal, RuntimeResultSignal):
            terminal_seen = True
            terminal_count += 1
            continue
        raise AssertionError("runtime.stream.unknown_signal：出现未知 signal")
    if terminal_count != 1:
        raise AssertionError("runtime.stream.terminal_cardinality：必须恰有一个终止 signal")


def run_reference_contract(
    adapter: RuntimeAdapterContract,
    request: RuntimeExecutionRequest,
    control: RuntimeControl,
) -> list[RuntimeSignal]:
    """执行 reference contract 并校验 signal cardinality。"""

    profile = adapter.capabilities()
    if set(item.capability for item in profile.capabilities) != set(RuntimeCapability):
        raise AssertionError("runtime.capability_profile：能力集合不完整")
    try:
        signals = list(adapter.stream(request, control))
    except Exception as exc:
        raise AssertionError("runtime.stream.untyped_exception：Adapter 意外异常必须转为 typed failure") from exc
    assert_runtime_signal_sequence(signals)
    return signals


class CurrentDiagnosisExecutorCompatibilityAdapter:
    """只存在于测试中的当前 DiagnosisExecutor 兼容 wrapper。"""

    def __init__(self, executor: DiagnosisExecutor) -> None:
        self._executor = executor

    def stream(
        self,
        request: RuntimeExecutionRequest,
        control: RuntimeControl,
    ) -> Iterator[RuntimeSignal]:
        del control
        request.contract_version.require_exact(CONTRACT_VERSION_V1)
        try:
            for item in self._executor.stream(request.query, request.service_id):
                if isinstance(item, DiagnosisExecutionEvent):
                    yield RuntimeEventSignal(contract_version=CONTRACT_VERSION_V1, event=item)
                else:
                    yield RuntimeResultSignal(contract_version=CONTRACT_VERSION_V1, result=item)
        except DiagnosisExecutionError:
            yield _failure_signal(FailureCodeId.MODEL_EXECUTION_FAILED, "诊断执行失败，请稍后重试")


class _ProbeCoordinator:
    """只向当前 Coordinator executor 提供确定性流的 fake coordinator。"""

    def __init__(self, scenario: str, queries: list[str]) -> None:
        self._scenario = scenario
        self._queries = queries

    def route_stream(self, query: str) -> Iterator[dict[str, object]]:
        self._queries.append(query)
        if self._scenario == "unexpected":
            raise RuntimeError("test-only unexpected exception")
        if self._scenario == "empty":
            return
        if self._scenario == "typed_failure":
            yield {
                "kind": "error",
                "code": "DIAGNOSIS_FAILED",
                "message": "诊断执行失败，请稍后重试",
            }
            return
        if self._scenario == "event_result":
            yield {
                "kind": "trace",
                "event": {
                    "type": "route_decided",
                    "node": "current",
                    "timestamp": FIXED_OCCURRED_AT.isoformat(),
                },
            }
        yield {"kind": "complete", "result": "current result", "strategy": "current"}
        if self._scenario == "multiple_results":
            yield {"kind": "complete", "result": "second result", "strategy": "current"}


class CurrentCoordinatorProbeFactory:
    """用 fake coordinator 驱动真实 CoordinatorDiagnosisExecutor 的场景工厂。"""

    def __init__(self) -> None:
        self.queries: list[str] = []
        self.service_ids: list[str | None] = []

    def create(self, scenario: str) -> DiagnosisExecutor:
        """为一次 observed 场景构造真实当前 executor。"""

        def coordinator_factory(service_id: str | None) -> _ProbeCoordinator:
            self.service_ids.append(service_id)
            return _ProbeCoordinator(scenario, self.queries)

        return CoordinatorDiagnosisExecutor(coordinator_factory)


def _observed(
    *,
    capability: RuntimeCapability,
    condition: bool,
    passing_status: RuntimeCapabilityStatus,
    passing_gap_id: str | None,
    evidence_kind: Literal["behavior_probe", "signature_probe", "contract_wrapper"],
    assertion: str,
) -> tuple[RuntimeCapability, ObservedCapability]:
    if condition:
        status = passing_status
        gap_id = passing_gap_id
    else:
        status = RuntimeCapabilityStatus.UNSUPPORTED
        gap_id = f"observed.{capability.value}.mismatch"
    return (
        capability,
        ObservedCapability(
            status=status,
            gap_id=gap_id,
            evidence=CapabilityEvidence(
                kind=evidence_kind,
                locator=f"DiagnosisExecutorCompatibilityProbe.{capability.value}",
                assertion=assertion,
            ),
        ),
    )


class DiagnosisExecutorCompatibilityProbe:
    """不读取 expected fixture、只从当前端口调用与签名推导 observed facts。"""

    def __init__(
        self,
        request: RuntimeExecutionRequest,
        factory: CurrentCoordinatorProbeFactory | None = None,
    ) -> None:
        self._request = request
        self._factory = factory or CurrentCoordinatorProbeFactory()

    def observe(self) -> dict[RuntimeCapability, ObservedCapability]:
        normal = self._factory.create("event_result")
        normal_control = StaticRuntimeControl()
        normal_signals = list(CurrentDiagnosisExecutorCompatibilityAdapter(normal).stream(self._request, normal_control))
        normal_query = self._factory.queries[-1] if self._factory.queries else None
        normal_service = self._factory.service_ids[-1] if self._factory.service_ids else None

        typed = self._factory.create("typed_failure")
        typed_signals = list(
            CurrentDiagnosisExecutorCompatibilityAdapter(typed).stream(self._request, StaticRuntimeControl())
        )

        unexpected_escaped = False
        try:
            list(
                CurrentDiagnosisExecutorCompatibilityAdapter(
                    self._factory.create("unexpected")
                ).stream(self._request, StaticRuntimeControl())
            )
        except RuntimeError:
            unexpected_escaped = True

        empty_signals = list(
            CurrentDiagnosisExecutorCompatibilityAdapter(
                self._factory.create("empty")
            ).stream(self._request, StaticRuntimeControl())
        )
        multiple_signals = list(
            CurrentDiagnosisExecutorCompatibilityAdapter(
                self._factory.create("multiple_results")
            ).stream(self._request, StaticRuntimeControl())
        )

        invalid_request = self._request.model_copy(
            update={"contract_version": ContractVersion(major=2, minor=0)}
        )
        version_rejected = False
        invalid_executor = self._factory.create("event_result")
        calls_before_invalid = len(self._factory.queries)
        try:
            list(
                CurrentDiagnosisExecutorCompatibilityAdapter(invalid_executor).stream(
                    invalid_request,
                    StaticRuntimeControl(),
                )
            )
        except ValueError:
            version_rejected = len(self._factory.queries) == calls_before_invalid

        cancelled_control = StaticRuntimeControl(cancel_requested=True)
        cancelled_signals = list(
            CurrentDiagnosisExecutorCompatibilityAdapter(
                self._factory.create("event_result")
            ).stream(self._request, cancelled_control)
        )

        port_parameters = set(signature(DiagnosisExecutor.stream).parameters)
        executor_has_capabilities = hasattr(normal, "capabilities")
        has_event = any(isinstance(item, RuntimeEventSignal) for item in normal_signals)
        has_result = any(isinstance(item, RuntimeResultSignal) for item in normal_signals)
        has_typed_failure = len(typed_signals) == 1 and isinstance(typed_signals[0], RuntimeFailureSignal)
        terminal_unenforced = not empty_signals and sum(
            isinstance(item, RuntimeResultSignal) for item in multiple_signals
        ) == 2

        return dict(
            [
                _observed(
                    capability=RuntimeCapability.QUERY,
                    condition=normal_query == self._request.query,
                    passing_status=RuntimeCapabilityStatus.SUPPORTED,
                    passing_gap_id=None,
                    evidence_kind="behavior_probe",
                    assertion="当前端口收到原始 query",
                ),
                _observed(
                    capability=RuntimeCapability.SERVICE_CONTEXT,
                    condition=normal_service == self._request.service_id,
                    passing_status=RuntimeCapabilityStatus.MAPPED,
                    passing_gap_id=None,
                    evidence_kind="behavior_probe",
                    assertion="可选 service_id 映射到当前端口第二参数",
                ),
                _observed(
                    capability=RuntimeCapability.EXECUTION_ID,
                    condition="execution_id" not in port_parameters,
                    passing_status=RuntimeCapabilityStatus.EXTERNALIZED,
                    passing_gap_id="diagnosis_executor.execution_id_externalized",
                    evidence_kind="signature_probe",
                    assertion="当前端口签名不接收 execution_id",
                ),
                _observed(
                    capability=RuntimeCapability.CONTRACT_VERSION,
                    condition=version_rejected,
                    passing_status=RuntimeCapabilityStatus.MAPPED,
                    passing_gap_id=None,
                    evidence_kind="contract_wrapper",
                    assertion="compatibility wrapper 在调用当前端口前精确校验 v1",
                ),
                _observed(
                    capability=RuntimeCapability.CONTROL,
                    condition="control" not in port_parameters and normal_control.cancel_checks == 0,
                    passing_status=RuntimeCapabilityStatus.EXTERNALIZED,
                    passing_gap_id="diagnosis_executor.control_externalized",
                    evidence_kind="signature_probe",
                    assertion="当前端口不接收或读取 RuntimeControl",
                ),
                _observed(
                    capability=RuntimeCapability.STREAM_EVENT_SHAPE,
                    condition=has_event,
                    passing_status=RuntimeCapabilityStatus.SUPPORTED,
                    passing_gap_id=None,
                    evidence_kind="behavior_probe",
                    assertion="DiagnosisExecutionEvent 映射为 RuntimeEventSignal",
                ),
                _observed(
                    capability=RuntimeCapability.FINAL_RESULT,
                    condition=has_result,
                    passing_status=RuntimeCapabilityStatus.MAPPED,
                    passing_gap_id=None,
                    evidence_kind="behavior_probe",
                    assertion="DiagnosisExecutionResult 映射为兼容 result signal",
                ),
                _observed(
                    capability=RuntimeCapability.TYPED_FAILURE,
                    condition=has_typed_failure,
                    passing_status=RuntimeCapabilityStatus.MAPPED,
                    passing_gap_id=None,
                    evidence_kind="behavior_probe",
                    assertion="DiagnosisExecutionError 映射为安全 typed failure",
                ),
                _observed(
                    capability=RuntimeCapability.UNEXPECTED_EXCEPTION,
                    condition=unexpected_escaped,
                    passing_status=RuntimeCapabilityStatus.UNSUPPORTED,
                    passing_gap_id="diagnosis_executor.unexpected_exception_untyped",
                    evidence_kind="behavior_probe",
                    assertion="非 DiagnosisExecutionError 仍会逸出当前端口",
                ),
                _observed(
                    capability=RuntimeCapability.TERMINAL_CARDINALITY,
                    condition=terminal_unenforced,
                    passing_status=RuntimeCapabilityStatus.UNSUPPORTED,
                    passing_gap_id="diagnosis_executor.terminal_cardinality_unenforced",
                    evidence_kind="behavior_probe",
                    assertion="当前端口允许零终止或多个 result",
                ),
                _observed(
                    capability=RuntimeCapability.CAPABILITY_DECLARATION,
                    condition=not executor_has_capabilities,
                    passing_status=RuntimeCapabilityStatus.EXTERNALIZED,
                    passing_gap_id="diagnosis_executor.capability_declaration_externalized",
                    evidence_kind="signature_probe",
                    assertion="能力声明由 reviewed profile 与 probe 持有",
                ),
                _observed(
                    capability=RuntimeCapability.DEADLINE,
                    condition="deadline_at" not in port_parameters and normal_control.remaining_checks == 0,
                    passing_status=RuntimeCapabilityStatus.UNSUPPORTED,
                    passing_gap_id="diagnosis_executor.deadline_unsupported",
                    evidence_kind="signature_probe",
                    assertion="当前端口不接收 deadline 且 wrapper 不伪装支持",
                ),
                _observed(
                    capability=RuntimeCapability.ADAPTER_CANCELLATION,
                    condition=(
                        "control" not in port_parameters
                        and cancelled_control.cancel_checks == 0
                        and any(isinstance(item, RuntimeResultSignal) for item in cancelled_signals)
                    ),
                    passing_status=RuntimeCapabilityStatus.EXTERNALIZED,
                    passing_gap_id="diagnosis_executor.cancellation_externalized",
                    evidence_kind="behavior_probe",
                    assertion="取消继续由 Run service 外层协调，当前端口不可中断",
                ),
            ]
        )


class _ToolGatewayProbeTool(Tool):
    """为 ToolGateway 六项 observed facts 提供确定性执行计数。"""

    def __init__(self) -> None:
        super().__init__(
            name="probe-counting",
            description="P10 S2 ToolGateway probe",
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


class _ToolGatewaySensitiveProbeTool(Tool):
    """返回或抛出测试哨兵，验证网关只暴露安全结果。"""

    def __init__(self, *, raises: bool) -> None:
        super().__init__(
            name="probe-sensitive",
            description="P10 S2 ToolGateway safety probe",
            parameters={"type": "object"},
        )
        self._raises = raises

    def execute(self) -> str:
        if self._raises:
            raise RuntimeError("password=unit-test-secret raw exception")
        return "password=unit-test-secret"


class _ToolGatewayTimeoutProbeTool(Tool):
    """在网关返回 timeout 后才结束，用于证明等待超时不等于执行取消。"""

    def __init__(self) -> None:
        super().__init__(
            name="probe-timeout",
            description="P10 S2 ToolGateway timeout probe",
            parameters={"type": "object"},
        )
        self.started = Event()
        self.release = Event()
        self.finished = Event()

    def execute(self) -> str:
        self.started.set()
        self.release.wait(timeout=1.0)
        self.finished.set()
        return "finished-after-timeout"


def _tool_gateway_observed(
    *,
    fact: ToolGatewayFact,
    condition: bool,
    passing_status: ToolGatewayFactStatus,
    passing_gap_id: str | None,
    assertion: str,
) -> tuple[ToolGatewayFact, ObservedToolGatewayFact]:
    if condition:
        status = passing_status
        gap_id = passing_gap_id
    elif passing_status is ToolGatewayFactStatus.GUARANTEED:
        status = ToolGatewayFactStatus.EXPECTED_GAP
        gap_id = f"observed.tool_gateway.{fact.value}.mismatch"
    else:
        status = ToolGatewayFactStatus.GUARANTEED
        gap_id = None
    return (
        fact,
        ObservedToolGatewayFact(
            status=status,
            gap_id=gap_id,
            evidence=CapabilityEvidence(
                kind="behavior_probe",
                locator=f"ToolGatewayCompatibilityProbe.{fact.value}",
                assertion=assertion,
            ),
        ),
    )


class ToolGatewayCompatibilityProbe:
    """不读取 fixture，以真实 ToolGateway 调用计算 Design §6.1 六项事实。"""

    def observe(self) -> dict[ToolGatewayFact, ObservedToolGatewayFact]:
        counting = _ToolGatewayProbeTool()
        counting_registry = ToolRegistry()
        counting_registry.register(counting)
        counting_gateway = ToolGateway(counting_registry)
        try:
            unregistered = counting_gateway.invoke("missing", "{}")
            after_unregistered = counting.executions
            invalid_results = [
                counting_gateway.invoke("probe-counting", arguments)
                for arguments in ("{bad", "[]", "{}", json.dumps({"text": 7}))
            ]
            after_invalid = counting.executions
            success = counting_gateway.invoke(
                "probe-counting",
                json.dumps({"text": "allowed"}),
            )
        finally:
            counting_gateway.shutdown()

        sensitive_registry = ToolRegistry()
        sensitive_registry.register(_ToolGatewaySensitiveProbeTool(raises=False))
        sensitive_gateway = ToolGateway(sensitive_registry)
        try:
            sensitive = sensitive_gateway.invoke("probe-sensitive", "{}")
        finally:
            sensitive_gateway.shutdown()

        exception_registry = ToolRegistry()
        exception_registry.register(_ToolGatewaySensitiveProbeTool(raises=True))
        exception_gateway = ToolGateway(exception_registry)
        try:
            exception = exception_gateway.invoke("probe-sensitive", "{}")
        finally:
            exception_gateway.shutdown()

        timeout_tool = _ToolGatewayTimeoutProbeTool()
        timeout_registry = ToolRegistry()
        timeout_registry.register(timeout_tool)
        timeout_gateway = ToolGateway(timeout_registry, timeout_seconds=0.05)
        try:
            timeout = timeout_gateway.invoke("probe-timeout", "{}")
            started_when_gateway_returned = timeout_tool.started.is_set()
            finished_when_gateway_returned = timeout_tool.finished.is_set()
            timeout_tool.release.set()
            finished_after_gateway_returned = timeout_tool.finished.wait(timeout=1.0)
        finally:
            timeout_tool.release.set()
            timeout_gateway.shutdown()

        sensitive_serialized = sensitive.model_dump_json()
        exception_serialized = exception.model_dump_json()
        success_record_safe = (
            success.record.status == "ok"
            and success.record.tool == "probe-counting"
            and success.record.duration_ms >= 0
            and success.output == "allowed"
            and counting.executions == 1
        )
        return dict(
            [
                _tool_gateway_observed(
                    fact=ToolGatewayFact.UNREGISTERED,
                    condition=unregistered.record.status == "rejected" and after_unregistered == 0,
                    passing_status=ToolGatewayFactStatus.GUARANTEED,
                    passing_gap_id=None,
                    assertion="未注册 Tool 被拒绝且已注册 probe 未执行",
                ),
                _tool_gateway_observed(
                    fact=ToolGatewayFact.INVALID_ARGUMENTS,
                    condition=(
                        all(item.record.status == "rejected" for item in invalid_results)
                        and after_invalid == 0
                    ),
                    passing_status=ToolGatewayFactStatus.GUARANTEED,
                    passing_gap_id=None,
                    assertion="非法 JSON、非对象、缺参数与类型错误均被拒绝且 Tool 未执行",
                ),
                _tool_gateway_observed(
                    fact=ToolGatewayFact.SUCCESS,
                    condition=success_record_safe,
                    passing_status=ToolGatewayFactStatus.GUARANTEED,
                    passing_gap_id=None,
                    assertion="允许请求只执行一次并返回脱敏 output 与完整安全 record",
                ),
                _tool_gateway_observed(
                    fact=ToolGatewayFact.SENSITIVE_OUTPUT,
                    condition=(
                        sensitive.record.status == "ok"
                        and "unit-test-secret" not in sensitive_serialized
                    ),
                    passing_status=ToolGatewayFactStatus.GUARANTEED,
                    passing_gap_id=None,
                    assertion="敏感输出命中规则后被脱敏",
                ),
                _tool_gateway_observed(
                    fact=ToolGatewayFact.TIMEOUT,
                    condition=(
                        timeout.record.status == "timeout"
                        and started_when_gateway_returned
                        and not finished_when_gateway_returned
                        and finished_after_gateway_returned
                    ),
                    passing_status=ToolGatewayFactStatus.EXPECTED_GAP,
                    passing_gap_id="tool_gateway.timeout_does_not_cancel_execution",
                    assertion="网关返回 timeout 后同步 Tool 仍可继续并完成，故只保证等待超时",
                ),
                _tool_gateway_observed(
                    fact=ToolGatewayFact.EXCEPTION,
                    condition=(
                        exception.record.status == "error"
                        and "unit-test-secret" not in exception_serialized
                        and "raw exception" not in exception_serialized
                    ),
                    passing_status=ToolGatewayFactStatus.GUARANTEED,
                    passing_gap_id=None,
                    assertion="Tool 异常映射为不泄露原始异常的中性 error",
                ),
            ]
        )


def compare_observed_to_reviewed(
    observed: dict[RuntimeCapability, ObservedCapability],
    tool_gateway_observed: dict[ToolGatewayFact, ObservedToolGatewayFact],
    reviewed: ReviewedCapabilityFixture,
) -> None:
    """精确比较 Runtime capability 与 ToolGateway fact 的版本化事实。"""

    if set(observed) != set(reviewed.capabilities):
        raise AssertionError("runtime.capability_profile.keys：observed 与 reviewed 能力集合不一致")
    for capability in RuntimeCapability:
        actual = observed[capability]
        expected = reviewed.capabilities[capability]
        if actual.status is not expected.expected_status:
            raise AssertionError(f"runtime.capability_profile.status：{capability.value}")
        if actual.gap_id != expected.gap_id:
            raise AssertionError(f"runtime.capability_profile.gap_id：{capability.value}")
        if actual.evidence.kind != expected.evidence.kind:
            raise AssertionError(f"runtime.capability_profile.evidence.kind：{capability.value}")
        if actual.evidence.locator != expected.evidence.locator:
            raise AssertionError(f"runtime.capability_profile.evidence.locator：{capability.value}")

    if set(tool_gateway_observed) != set(reviewed.tool_gateway_facts):
        raise AssertionError("tool_gateway.capability_profile.keys：observed 与 reviewed 事实集合不一致")
    for fact in ToolGatewayFact:
        actual_fact = tool_gateway_observed[fact]
        expected_fact = reviewed.tool_gateway_facts[fact]
        if actual_fact.status is not expected_fact.expected_status:
            raise AssertionError(f"tool_gateway.capability_profile.status：{fact.value}")
        if actual_fact.gap_id != expected_fact.gap_id:
            raise AssertionError(f"tool_gateway.capability_profile.gap_id：{fact.value}")
        if actual_fact.evidence.kind != expected_fact.evidence.kind:
            raise AssertionError(f"tool_gateway.capability_profile.evidence.kind：{fact.value}")
        if actual_fact.evidence.locator != expected_fact.evidence.locator:
            raise AssertionError(f"tool_gateway.capability_profile.evidence.locator：{fact.value}")


def fixed_execution_uuid() -> UUID:
    """返回 S2 测试使用的固定 execution UUID。"""

    return UUID("32345678-1234-5678-9234-567812345678")
