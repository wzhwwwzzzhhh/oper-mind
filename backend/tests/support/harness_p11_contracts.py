"""P11 capability v2 连续性与行为绑定断言。"""

from __future__ import annotations

from pathlib import Path

from src.application.contracts import DiagnosisExecutionResult
from src.application.runtime_contracts import (
    RuntimeCapability,
    RuntimeCapabilityStatus,
    RuntimeFailureSignal,
)
from src.application.runtime_safety import guard_runtime_stream
from src.domain.harness_contracts import FailureCodeId
from tests.support.harness_contracts import ReviewedCapabilityFixture


def load_reviewed_profile(path: Path) -> ReviewedCapabilityFixture:
    """加载封闭的 reviewed capability profile。"""

    return ReviewedCapabilityFixture.model_validate_json(path.read_text(encoding="utf-8"))


def assert_p11_profile_transition(
    previous: ReviewedCapabilityFixture,
    current: ReviewedCapabilityFixture,
) -> None:
    """v2 只能升级 P11 已有行为证明的两个 Runtime capability。"""

    if previous.profile_version != 1 or current.profile_version != 2:
        raise AssertionError("P11 capability profile 版本必须从 1 连续升级到 2")
    if previous.contract_version != current.contract_version:
        raise AssertionError("P11 不得改变 Runtime contract version")
    if previous.tool_gateway_facts != current.tool_gateway_facts:
        raise AssertionError("P11 capability v2 不得改写 P10 ToolGateway 历史事实")

    upgraded = {
        RuntimeCapability.TERMINAL_CARDINALITY,
        RuntimeCapability.UNEXPECTED_EXCEPTION,
    }
    for capability in RuntimeCapability:
        before = previous.capabilities[capability]
        after = current.capabilities[capability]
        if capability in upgraded:
            if before.expected_status is not RuntimeCapabilityStatus.UNSUPPORTED:
                raise AssertionError("P10 待升级 capability 的历史状态必须是 unsupported")
            if after.expected_status is not RuntimeCapabilityStatus.MAPPED or after.gap_id is not None:
                raise AssertionError("P11 已证明 capability 必须映射为 mapped 且清除对应 gap")
            continue
        if before != after:
            raise AssertionError(f"P11 capability v2 出现未批准漂移：{capability.value}")


def assert_p11_behavior_backed(
    profile: ReviewedCapabilityFixture,
) -> None:
    """直接运行 guard 行为探针，防止布尔硬编码自证。"""

    result = DiagnosisExecutionResult(strategy="p11-probe")
    cardinality_signals = list(guard_runtime_stream(lambda: iter([result, result])))

    def unexpected_stream():
        raise RuntimeError("probe-private-detail")
        yield

    unexpected_signals = list(guard_runtime_stream(unexpected_stream))

    def is_failure(signals: list[object], code: FailureCodeId) -> bool:
        return (
            len(signals) == 1
            and isinstance(signals[0], RuntimeFailureSignal)
            and signals[0].code.code is code
        )

    probes = {
        RuntimeCapability.TERMINAL_CARDINALITY: is_failure(
            cardinality_signals,
            FailureCodeId.INTERNAL_INVARIANT_VIOLATION,
        ),
        RuntimeCapability.UNEXPECTED_EXCEPTION: is_failure(
            unexpected_signals,
            FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION,
        ),
    }
    for capability, passed in probes.items():
        declaration = profile.capabilities[capability]
        if declaration.expected_status is RuntimeCapabilityStatus.MAPPED and not passed:
            raise AssertionError(f"P11 capability 缺少行为证明：{capability.value}")
