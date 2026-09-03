"""P10 S1 Harness Contract Kernel 的封闭类型与边界测试。"""

from __future__ import annotations

import ast
import inspect
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from pydantic import BaseModel, ValidationError

import src.domain.harness_contracts as kernel
from src.domain.harness_contracts import (
    CONTRACT_VERSION_V1,
    ContractVersion,
    ControlOverlayCode,
    ControlOverlayValue,
    DispatchOverlayCode,
    DispatchOverlayValue,
    ExternalOutcomeCode,
    ExternalOutcomeValue,
    FailureCodeId,
    FailureCodeValue,
    FailureNamespace,
    FencingToken,
    Generation,
    HarnessIdentity,
    LifecycleStateCode,
    LifecycleStateValue,
    ResolutionDispositionCode,
    ResolutionDispositionValue,
    ResultDispositionCode,
    ResultDispositionValue,
)

FIXED_UUID = UUID("12345678-1234-5678-9234-567812345678")

VERSIONED_VALUE_CASES: tuple[tuple[type[BaseModel], str, Enum, str], ...] = (
    (
        LifecycleStateValue,
        "lifecycle_state",
        LifecycleStateCode.RUNNING,
        "external_outcome",
    ),
    (
        ResultDispositionValue,
        "result_disposition",
        ResultDispositionCode.COMPLETE_RESULT,
        "lifecycle_state",
    ),
    (
        ExternalOutcomeValue,
        "external_outcome",
        ExternalOutcomeCode.SUCCEEDED,
        "result_disposition",
    ),
    (
        FailureCodeValue,
        "failure_code",
        FailureCodeId.RUNTIME_UNEXPECTED_EXCEPTION,
        "resolution_disposition",
    ),
    (
        ResolutionDispositionValue,
        "resolution_disposition",
        ResolutionDispositionCode.MANUAL_REQUIRED,
        "dispatch_overlay",
    ),
    (
        DispatchOverlayValue,
        "dispatch_overlay",
        DispatchOverlayCode.LEASE_ACQUIRED,
        "control_overlay",
    ),
    (
        ControlOverlayValue,
        "control_overlay",
        ControlOverlayCode.BLOCKED_FOR_REPAIR,
        "failure_code",
    ),
)


def _round_trip(model: BaseModel) -> BaseModel:
    """通过稳定 JSON 边界往返一个具体 Pydantic model。"""

    return type(model).model_validate_json(model.model_dump_json())


def _versioned_payload(*, dimension: str, code: str) -> dict[str, Any]:
    return {
        "contract_version": {"major": 1, "minor": 0},
        "dimension": dimension,
        "code": code,
    }


@pytest.mark.parametrize(
    ("model_type", "expected_dimension", "valid_code", "wrong_dimension"),
    VERSIONED_VALUE_CASES,
)
def test_七维分别固定tag封闭code并稳定往返(
    model_type: type[BaseModel],
    expected_dimension: str,
    valid_code: Enum,
    wrong_dimension: str,
) -> None:
    payload = {
        "contract_version": {"major": 1, "minor": 0},
        "dimension": expected_dimension,
        "code": valid_code,
    }
    value = model_type.model_validate(payload)

    assert _round_trip(value) == value
    assert value.model_dump(mode="json")["dimension"] == expected_dimension
    assert value.model_dump(mode="json")["contract_version"] == {"major": 1, "minor": 0}

    with pytest.raises(ValidationError, match="dimension"):
        model_type.model_validate({**payload, "dimension": wrong_dimension})
    with pytest.raises(ValidationError, match="code"):
        model_type.model_validate({**payload, "code": "not_in_contract_v1"})


def test_同名failed不能跨生命周期与外部结果维度() -> None:
    with pytest.raises(ValidationError, match="错误维度"):
        LifecycleStateValue(
            contract_version=CONTRACT_VERSION_V1,
            code=ExternalOutcomeCode.FAILED,
        )
    with pytest.raises(ValidationError, match="错误维度"):
        ExternalOutcomeValue(
            contract_version=CONTRACT_VERSION_V1,
            code=LifecycleStateCode.FAILED,
        )

    lifecycle_payload = LifecycleStateValue(
        contract_version=CONTRACT_VERSION_V1,
        code=LifecycleStateCode.FAILED,
    ).model_dump(mode="json")
    external_payload = ExternalOutcomeValue(
        contract_version=CONTRACT_VERSION_V1,
        code=ExternalOutcomeCode.FAILED,
    ).model_dump(mode="json")

    with pytest.raises(ValidationError, match="dimension"):
        ExternalOutcomeValue.model_validate(lifecycle_payload)
    with pytest.raises(ValidationError, match="dimension"):
        LifecycleStateValue.model_validate(external_payload)


def test_failure错误namespace被拒绝() -> None:
    with pytest.raises(ValidationError, match="namespace"):
        FailureCodeValue(
            contract_version=CONTRACT_VERSION_V1,
            code=FailureCodeId.TOOL_TIMEOUT,
            namespace=FailureNamespace.RUNTIME,
        )


def test_failure命名空间由封闭完整id派生() -> None:
    expected_ids = {
        "validation.invalid_request",
        "runtime.unexpected_exception",
        "runtime.unsupported_capability",
        "model.execution_failed",
        "tool.rejected",
        "tool.timeout",
        "policy.denied",
        "approval.required",
        "budget.exceeded",
        "cancel.requested",
        "recovery.required",
        "persistence.conflict",
        "internal.invariant_violation",
    }
    assert {item.value for item in FailureCodeId} == expected_ids

    for code in FailureCodeId:
        value = FailureCodeValue(contract_version=CONTRACT_VERSION_V1, code=code)
        assert value.namespace.value == code.value.partition(".")[0]
        assert _round_trip(value) == value

    with pytest.raises(ValidationError, match="code"):
        FailureCodeValue.model_validate(
            {
                **_versioned_payload(
                    dimension="failure_code",
                    code="runtime.not_in_contract_v1",
                ),
                "namespace": "runtime",
            }
        )


def test_identity_version_generation_fencing合法往返并拒绝非法值() -> None:
    identity = HarnessIdentity(namespace="runtime.worker-1", value=FIXED_UUID)
    generation_1 = Generation(value=1)
    generation_2 = Generation(value=2)
    fencing = FencingToken(value=FIXED_UUID)

    assert _round_trip(identity) == identity
    assert _round_trip(CONTRACT_VERSION_V1) == CONTRACT_VERSION_V1
    assert _round_trip(generation_1) == generation_1
    assert _round_trip(fencing) == fencing
    assert generation_1 < generation_2
    assert sorted([generation_2, generation_1]) == [generation_1, generation_2]
    assert fencing == FencingToken(value=str(FIXED_UUID))

    with pytest.raises(ValidationError, match="namespace"):
        HarnessIdentity(namespace="", value=FIXED_UUID)
    with pytest.raises(ValidationError, match="namespace"):
        HarnessIdentity(namespace="Runtime Worker", value=FIXED_UUID)
    with pytest.raises(ValidationError, match="UUID"):
        HarnessIdentity(namespace="runtime", value="not-a-uuid")
    with pytest.raises(ValidationError, match="major"):
        ContractVersion(major=-1, minor=0)
    with pytest.raises(ValidationError, match="value"):
        Generation(value=-1)
    with pytest.raises(TypeError):
        _ = fencing < FencingToken(value=UUID("22345678-1234-5678-9234-567812345678"))


def test_contract_model冻结拒绝额外字段并精确匹配v1() -> None:
    value = LifecycleStateValue(
        contract_version=CONTRACT_VERSION_V1,
        code=LifecycleStateCode.RUNNING,
    )

    with pytest.raises(ValidationError, match="frozen"):
        value.code = LifecycleStateCode.COMPLETED
    with pytest.raises(ValidationError, match="extra"):
        LifecycleStateValue.model_validate(
            {
                **_versioned_payload(dimension="lifecycle_state", code="running"),
                "status": "running",
            }
        )
    with pytest.raises(ValidationError, match="契约版本不匹配"):
        LifecycleStateValue(
            contract_version=ContractVersion(major=1, minor=1),
            code=LifecycleStateCode.RUNNING,
        )
    with pytest.raises(ValidationError, match="contract_version"):
        LifecycleStateValue.model_validate(
            {"dimension": "lifecycle_state", "code": "running"}
        )


def test_kernel不包含阶段B业务实体或持久化映射() -> None:
    forbidden_names = {
        "AgentTask",
        "Attempt",
        "BindingSnapshot",
        "ContextManifest",
        "HarnessUnitOfWork",
        "ResultAcceptance",
        "ToolCallId",
    }
    declared_classes = {
        name
        for name, value in inspect.getmembers(kernel, inspect.isclass)
        if value.__module__ == kernel.__name__
    }
    assert declared_classes.isdisjoint(forbidden_names)

    module_path = Path(kernel.__file__ or "")
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    imported_roots = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert imported_roots <= {
        "__future__",
        "enum",
        "functools",
        "typing",
        "uuid",
        "pydantic",
    }
    assert "sqlalchemy" not in imported_roots


def test_v1封闭词汇与设计完全一致() -> None:
    expected: dict[type[Enum], set[str]] = {
        LifecycleStateCode: {
            "created",
            "ready",
            "running",
            "waiting",
            "completed",
            "failed",
            "cancelling",
            "cancelled",
        },
        ResultDispositionCode: {
            "complete_result",
            "partial_result",
            "no_result",
            "pending",
        },
        ExternalOutcomeCode: {
            "not_executed",
            "executed_unverified",
            "succeeded",
            "failed",
            "outcome_unknown",
        },
        ResolutionDispositionCode: {"automatic", "manual_required"},
        DispatchOverlayCode: {
            "idle",
            "lease_acquired",
            "dispatch_recorded",
            "worker_started",
            "released",
            "lease_expired",
            "reassigning",
        },
        ControlOverlayCode: {"normal", "blocked_for_repair"},
    }
    for enum_type, codes in expected.items():
        assert {item.value for item in enum_type} == codes
