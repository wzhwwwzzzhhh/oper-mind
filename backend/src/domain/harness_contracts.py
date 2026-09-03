"""P10 Harness 的框架无关最小契约词汇。

本模块只描述机械身份、契约版本和七个彼此正交的状态维度。它不定义
业务对象、状态迁移、持久化、权限或外部副作用语义，也不接入现有生产运行链。
"""

from __future__ import annotations

from enum import Enum, StrEnum
from functools import total_ordering
from typing import Any, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _FrozenContractModel(BaseModel):
    """禁止额外字段和实例修改的契约模型基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ContractVersion(_FrozenContractModel):
    """使用非负主、次版本号表达精确契约版本。"""

    major: int = Field(ge=0, strict=True)
    minor: int = Field(ge=0, strict=True)

    def require_exact(self, supported: ContractVersion) -> None:
        """要求版本与受支持版本精确相同，不执行隐式协商。"""

        if self != supported:
            raise ValueError(
                f"契约版本不匹配：要求 {supported.major}.{supported.minor}，"
                f"收到 {self.major}.{self.minor}"
            )


CONTRACT_VERSION_V1 = ContractVersion(major=1, minor=0)


class _VersionedValue(_FrozenContractModel):
    """仅接受当前 v1 精确版本的 tagged value 基类。"""

    contract_version: ContractVersion

    @model_validator(mode="after")
    def _require_v1(self) -> Self:
        self.contract_version.require_exact(CONTRACT_VERSION_V1)
        return self


class HarnessIdentity(_FrozenContractModel):
    """不携带业务所有权或授权含义的通用机械身份。"""

    namespace: str = Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z][a-z0-9_.-]*$",
        strict=True,
    )
    value: UUID


@total_ordering
class Generation(_FrozenContractModel):
    """可排序的非负 fencing generation，不代表重试次数。"""

    value: int = Field(ge=0, strict=True)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, Generation):
            return NotImplemented
        return self.value < other.value


class FencingToken(_FrozenContractModel):
    """只支持相等比较的 opaque UUID fencing token。"""

    value: UUID


class LifecycleStateCode(StrEnum):
    """Harness 生命周期维度的 v1 封闭词汇。"""

    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"


class ResultDispositionCode(StrEnum):
    """Harness 结果处置维度的 v1 封闭词汇。"""

    COMPLETE_RESULT = "complete_result"
    PARTIAL_RESULT = "partial_result"
    NO_RESULT = "no_result"
    PENDING = "pending"


class ExternalOutcomeCode(StrEnum):
    """外部副作用结果维度的 v1 封闭词汇。"""

    NOT_EXECUTED = "not_executed"
    EXECUTED_UNVERIFIED = "executed_unverified"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    OUTCOME_UNKNOWN = "outcome_unknown"


class FailureNamespace(StrEnum):
    """失败分类 ID 的 v1 封闭命名空间。"""

    VALIDATION = "validation"
    RUNTIME = "runtime"
    MODEL = "model"
    TOOL = "tool"
    POLICY = "policy"
    APPROVAL = "approval"
    BUDGET = "budget"
    CANCEL = "cancel"
    RECOVERY = "recovery"
    PERSISTENCE = "persistence"
    INTERNAL = "internal"


class FailureCodeId(StrEnum):
    """Harness 失败维度的 v1 封闭完整 ID 集合。"""

    VALIDATION_INVALID_REQUEST = "validation.invalid_request"
    RUNTIME_UNEXPECTED_EXCEPTION = "runtime.unexpected_exception"
    RUNTIME_UNSUPPORTED_CAPABILITY = "runtime.unsupported_capability"
    MODEL_EXECUTION_FAILED = "model.execution_failed"
    TOOL_REJECTED = "tool.rejected"
    TOOL_TIMEOUT = "tool.timeout"
    POLICY_DENIED = "policy.denied"
    APPROVAL_REQUIRED = "approval.required"
    BUDGET_EXCEEDED = "budget.exceeded"
    CANCEL_REQUESTED = "cancel.requested"
    RECOVERY_REQUIRED = "recovery.required"
    PERSISTENCE_CONFLICT = "persistence.conflict"
    INTERNAL_INVARIANT_VIOLATION = "internal.invariant_violation"

    @property
    def namespace(self) -> FailureNamespace:
        """从完整 ID 唯一派生命名空间。"""

        prefix, _, _ = self.value.partition(".")
        return FailureNamespace(prefix)


class ResolutionDispositionCode(StrEnum):
    """后续处置责任维度的 v1 封闭词汇。"""

    AUTOMATIC = "automatic"
    MANUAL_REQUIRED = "manual_required"


class DispatchOverlayCode(StrEnum):
    """调度 overlay 的 v1 封闭词汇。"""

    IDLE = "idle"
    LEASE_ACQUIRED = "lease_acquired"
    DISPATCH_RECORDED = "dispatch_recorded"
    WORKER_STARTED = "worker_started"
    RELEASED = "released"
    LEASE_EXPIRED = "lease_expired"
    REASSIGNING = "reassigning"


class ControlOverlayCode(StrEnum):
    """控制 overlay 的 v1 封闭词汇。"""

    NORMAL = "normal"
    BLOCKED_FOR_REPAIR = "blocked_for_repair"


def _reject_foreign_enum(value: object, expected: type[Enum]) -> object:
    """拒绝把其他维度的枚举实例按其字符串值悄悄转换。"""

    if isinstance(value, Enum) and not isinstance(value, expected):
        raise ValueError(f"状态 code 属于错误维度：{type(value).__name__}")
    return value


class LifecycleStateValue(_VersionedValue):
    """带固定 tag 的生命周期值。"""

    dimension: Literal["lifecycle_state"] = "lifecycle_state"
    code: LifecycleStateCode

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_dimension(cls, value: object) -> object:
        return _reject_foreign_enum(value, LifecycleStateCode)


class ResultDispositionValue(_VersionedValue):
    """带固定 tag 的结果处置值。"""

    dimension: Literal["result_disposition"] = "result_disposition"
    code: ResultDispositionCode

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_dimension(cls, value: object) -> object:
        return _reject_foreign_enum(value, ResultDispositionCode)


class ExternalOutcomeValue(_VersionedValue):
    """带固定 tag 的外部副作用结果值。"""

    dimension: Literal["external_outcome"] = "external_outcome"
    code: ExternalOutcomeCode

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_dimension(cls, value: object) -> object:
        return _reject_foreign_enum(value, ExternalOutcomeCode)


class FailureCodeValue(_VersionedValue):
    """带固定 tag、完整 ID 和派生命名空间的失败值。"""

    dimension: Literal["failure_code"] = "failure_code"
    code: FailureCodeId
    namespace: FailureNamespace

    @model_validator(mode="before")
    @classmethod
    def _derive_namespace(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        payload = dict(data)
        raw_code = payload.get("code")
        if isinstance(raw_code, Enum) and not isinstance(raw_code, FailureCodeId):
            raise ValueError(f"failure code 属于错误维度：{type(raw_code).__name__}")
        if not isinstance(raw_code, str):
            return payload
        try:
            code = FailureCodeId(raw_code)
        except (TypeError, ValueError):
            return payload
        if "namespace" not in payload:
            payload["namespace"] = code.namespace
        return payload

    @model_validator(mode="after")
    def _validate_namespace(self) -> Self:
        if self.namespace is not self.code.namespace:
            raise ValueError("failure namespace 必须由完整 failure code ID 派生")
        return self


class ResolutionDispositionValue(_VersionedValue):
    """带固定 tag 的后续处置责任值。"""

    dimension: Literal["resolution_disposition"] = "resolution_disposition"
    code: ResolutionDispositionCode

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_dimension(cls, value: object) -> object:
        return _reject_foreign_enum(value, ResolutionDispositionCode)


class DispatchOverlayValue(_VersionedValue):
    """带固定 tag 的调度 overlay 值。"""

    dimension: Literal["dispatch_overlay"] = "dispatch_overlay"
    code: DispatchOverlayCode

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_dimension(cls, value: object) -> object:
        return _reject_foreign_enum(value, DispatchOverlayCode)


class ControlOverlayValue(_VersionedValue):
    """带固定 tag 的控制 overlay 值。"""

    dimension: Literal["control_overlay"] = "control_overlay"
    code: ControlOverlayCode

    @field_validator("code", mode="before")
    @classmethod
    def _validate_code_dimension(cls, value: object) -> object:
        return _reject_foreign_enum(value, ControlOverlayCode)
