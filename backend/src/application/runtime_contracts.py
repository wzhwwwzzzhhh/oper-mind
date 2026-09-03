"""P10 S2 的框架无关 Runtime Adapter 目标契约。

这些类型只用于 reference / compatibility contract test，不接入生产依赖注入，
也不拥有 Run 状态、Tool 副作用、权限、审批或持久化事实。
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from enum import StrEnum
from typing import Annotated, Literal, Protocol, Self, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from src.application.contracts import DiagnosisExecutionEvent, DiagnosisExecutionResult
from src.domain.harness_contracts import (
    CONTRACT_VERSION_V1,
    ContractVersion,
    FailureCodeValue,
    HarnessIdentity,
)


class _FrozenRuntimeContract(BaseModel):
    """禁止额外字段和实例修改的 Runtime 契约基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class RuntimeCapability(StrEnum):
    """Runtime Adapter v1 的完整能力声明集合。"""

    QUERY = "query"
    SERVICE_CONTEXT = "service_context"
    EXECUTION_ID = "execution_id"
    CONTRACT_VERSION = "contract_version"
    CONTROL = "control"
    STREAM_EVENT_SHAPE = "stream_event_shape"
    FINAL_RESULT = "final_result"
    TYPED_FAILURE = "typed_failure"
    UNEXPECTED_EXCEPTION = "unexpected_exception"
    TERMINAL_CARDINALITY = "terminal_cardinality"
    CAPABILITY_DECLARATION = "capability_declaration"
    DEADLINE = "deadline"
    ADAPTER_CANCELLATION = "adapter_cancellation"


class RuntimeCapabilityStatus(StrEnum):
    """能力与当前 Runtime 的诚实映射状态。"""

    SUPPORTED = "supported"
    MAPPED = "mapped"
    EXTERNALIZED = "externalized"
    UNSUPPORTED = "unsupported"


class RuntimeCapabilityDeclaration(_FrozenRuntimeContract):
    """单项能力状态；声明不构成授权或行为完成证明。"""

    capability: RuntimeCapability
    status: RuntimeCapabilityStatus
    gap_id: str | None = Field(default=None, min_length=1, max_length=120, pattern=r"^[a-z0-9_.-]+$")

    @model_validator(mode="after")
    def _validate_gap(self) -> Self:
        requires_gap = self.status in {
            RuntimeCapabilityStatus.EXTERNALIZED,
            RuntimeCapabilityStatus.UNSUPPORTED,
        }
        if requires_gap != (self.gap_id is not None):
            raise ValueError("externalized/unsupported 必须且仅能携带 gap_id")
        return self


class RuntimeCapabilityProfile(_FrozenRuntimeContract):
    """版本化且覆盖完整能力集合的 Runtime 声明。"""

    contract_version: ContractVersion
    profile_version: int = Field(ge=1, strict=True)
    capabilities: tuple[RuntimeCapabilityDeclaration, ...]

    @model_validator(mode="after")
    def _validate_profile(self) -> Self:
        self.contract_version.require_exact(CONTRACT_VERSION_V1)
        keys = [item.capability for item in self.capabilities]
        if len(keys) != len(set(keys)):
            raise ValueError("capability profile 不允许重复能力")
        missing = set(RuntimeCapability) - set(keys)
        extra = set(keys) - set(RuntimeCapability)
        if missing or extra:
            raise ValueError("capability profile 必须精确覆盖 v1 完整能力集合")
        return self

    def declaration_for(self, capability: RuntimeCapability) -> RuntimeCapabilityDeclaration:
        """按能力返回唯一声明。"""

        return next(item for item in self.capabilities if item.capability is capability)


class RuntimeExecutionRequest(_FrozenRuntimeContract):
    """传给 Runtime Adapter 的最小、不可变执行请求。"""

    execution_id: HarnessIdentity
    contract_version: ContractVersion
    query: str = Field(min_length=1, max_length=4000, strict=True)
    service_id: str | None = Field(default=None, min_length=1, max_length=64, strict=True)
    deadline_at: datetime

    @field_validator("query")
    @classmethod
    def _reject_blank_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query 不能为空")
        return value

    @field_validator("service_id")
    @classmethod
    def _reject_blank_service_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("service_id 不能为空")
        return value

    @field_validator("deadline_at")
    @classmethod
    def _require_utc_deadline(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
            raise ValueError("deadline_at 必须是 UTC aware datetime")
        return value

    @model_validator(mode="after")
    def _require_contract_v1(self) -> Self:
        self.contract_version.require_exact(CONTRACT_VERSION_V1)
        return self


class RuntimeControl(Protocol):
    """Reference Adapter 可读取的协作式取消与 deadline 视图。"""

    def is_cancel_requested(self) -> bool:
        """返回调用方是否已请求协作式取消。"""

    def remaining_seconds(self) -> float:
        """返回绝对 deadline 对应的剩余秒数。"""


class _RuntimeSignalBase(_FrozenRuntimeContract):
    """只接受精确 contract v1 的 Runtime signal 基类。"""

    contract_version: ContractVersion

    @model_validator(mode="after")
    def _require_contract_v1(self) -> Self:
        self.contract_version.require_exact(CONTRACT_VERSION_V1)
        return self


class RuntimeEventSignal(_RuntimeSignalBase):
    """包装当前安全执行事件的非终止 signal。"""

    kind: Literal["event"] = "event"
    event: DiagnosisExecutionEvent


class RuntimeResultSignal(_RuntimeSignalBase):
    """包装当前兼容诊断结果的终止 signal。"""

    kind: Literal["result"] = "result"
    result: DiagnosisExecutionResult


class RuntimeFailureSignal(_RuntimeSignalBase):
    """不保存原始异常的 typed failure 终止 signal。"""

    kind: Literal["failure"] = "failure"
    code: FailureCodeValue
    message: str = Field(min_length=1, max_length=500, strict=True)

    @model_validator(mode="after")
    def _require_nested_version_match(self) -> Self:
        if self.code.contract_version != self.contract_version:
            raise ValueError("failure code 与 signal contract version 必须一致")
        return self


RuntimeSignal: TypeAlias = Annotated[
    RuntimeEventSignal | RuntimeResultSignal | RuntimeFailureSignal,
    Field(discriminator="kind"),
]


class RuntimeAdapterContract(Protocol):
    """只供 reference / compatibility 测试使用的未激活目标协议。"""

    def capabilities(self) -> RuntimeCapabilityProfile:
        """返回完整、版本化且不代表授权的能力声明。"""

    def stream(
        self,
        request: RuntimeExecutionRequest,
        control: RuntimeControl,
    ) -> Iterator[RuntimeSignal]:
        """产生零到多个 event，并以恰好一个 result 或 failure 终止。"""
