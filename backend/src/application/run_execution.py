"""V2 Run 的 typed 执行契约、封闭信号与 legacy 诊断桥。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from enum import StrEnum
from hashlib import sha256
from inspect import signature
from typing import Annotated, Literal, Protocol, TypeAlias
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from src.application.contracts import (
    ApplicationCommand,
    DiagnosisExecutionError,
    DiagnosisExecutionEvent,
    DiagnosisExecutionResult,
    DiagnosisExecutor,
)
from src.capabilities.text_compare import TextComparisonRuleError, compare_materials
from src.core.input_admission import main_input_has_sensitive_content
from src.domain.main_agent import (
    MAIN_AGENT_RULE_VERSION,
    MainAnswerDeliveryV1,
    MainComparisonDeliveryV1,
    MainContextMessageV1,
    MainDeliveryV1,
    MainInputSnapshotV1,
    MainInputV1,
    MainMaterialSnapshotV1,
    MainNeedsInputDeliveryV1,
    material_digest,
    validate_material_text,
)
from src.domain.records import DiagnosisRunData

MAIN_AGENT_CREATE_FINGERPRINT_TAG = "main-agent-create@1"
MAIN_AGENT_RERUN_FINGERPRINT_TAG = "main-agent-rerun@1"


class RunFailureCode(StrEnum):
    """写入 Run 的封闭失败码；每项只映射固定安全文案。"""

    DIAGNOSIS_FAILED = "DIAGNOSIS_FAILED"
    MAIN_AGENT_FAILED = "MAIN_AGENT_FAILED"
    MAIN_AGENT_MODEL_UNAVAILABLE = "MAIN_AGENT_MODEL_UNAVAILABLE"
    MAIN_AGENT_DECISION_INVALID = "MAIN_AGENT_DECISION_INVALID"
    MAIN_AGENT_CAPABILITY_UNAVAILABLE = "MAIN_AGENT_CAPABILITY_UNAVAILABLE"
    MAIN_AGENT_TOOL_FAILED = "MAIN_AGENT_TOOL_FAILED"
    MAIN_AGENT_INPUT_UNAVAILABLE = "MAIN_AGENT_INPUT_UNAVAILABLE"
    MAIN_AGENT_DELIVERY_INVALID = "MAIN_AGENT_DELIVERY_INVALID"
    MAIN_AGENT_RULE_UNAVAILABLE = "MAIN_AGENT_RULE_UNAVAILABLE"

    @property
    def safe_message(self) -> str:
        """返回唯一允许持久化和公开展示的中文文案。"""
        return {
            RunFailureCode.DIAGNOSIS_FAILED: "诊断执行失败，请稍后重试",
            RunFailureCode.MAIN_AGENT_FAILED: "主 Agent 执行失败，请稍后重试",
            RunFailureCode.MAIN_AGENT_MODEL_UNAVAILABLE: "主 Agent 模型暂不可用，请稍后重试",
            RunFailureCode.MAIN_AGENT_DECISION_INVALID: "主 Agent 决策无效，请重新描述任务",
            RunFailureCode.MAIN_AGENT_CAPABILITY_UNAVAILABLE: "所需能力当前不可用",
            RunFailureCode.MAIN_AGENT_TOOL_FAILED: "主 Agent 工具执行失败，请稍后重试",
            RunFailureCode.MAIN_AGENT_INPUT_UNAVAILABLE: "主 Agent 输入不可用，请重新发起",
            RunFailureCode.MAIN_AGENT_DELIVERY_INVALID: "主 Agent 交付校验失败",
            RunFailureCode.MAIN_AGENT_RULE_UNAVAILABLE: "主 Agent 规则不可用，请重新发起",
        }[self]


class MainAgentInputRejectedError(Exception):
    """输入在落库前被拒绝；错误不携带原文。"""

    def __init__(self) -> None:
        super().__init__("主 Agent 输入包含不允许的敏感内容。")


class UnsupportedMainAgentRuleError(Exception):
    """重跑引用的规则版本已不可用；绝不暗中升级。"""

    def __init__(self) -> None:
        super().__init__("主 Agent 规则版本不可用，请重新发起。")


class RunExecutionError(Exception):
    """typed 执行器可安全暴露的失败；只携带封闭失败码。"""

    def __init__(self, code: RunFailureCode) -> None:
        super().__init__(code.safe_message)
        self.code = code


class _FrozenExecutionContract(BaseModel):
    """禁止额外字段与实例修改的执行契约基类。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class CreateMainAgentRunCommand(ApplicationCommand):
    """受理一次显式 MainAgent Run。"""

    session_id: UUID
    idempotency_key: UUID
    input: MainInputV1


class MainAgentRerunCommand(ApplicationCommand):
    """内部重跑命令：携带原冻结快照，不暴露给公开 API。"""

    session_id: UUID
    idempotency_key: UUID
    source_run_id: UUID
    snapshot: MainInputSnapshotV1


class DiagnosisRunExecutionInput(_FrozenExecutionContract):
    """legacy 诊断执行输入，保留原 query/service 语义。"""

    runtime_kind: Literal["diagnosis"] = "diagnosis"
    query: str = Field(min_length=1, max_length=4000)
    service_id: str | None = Field(default=None, max_length=64)


class MainAgentRunExecutionInput(_FrozenExecutionContract):
    """MainAgent 执行输入：只携带冻结快照与 Run 身份。"""

    runtime_kind: Literal["main_agent"] = "main_agent"
    run_id: UUID
    session_id: UUID
    snapshot: MainInputSnapshotV1


RunExecutionInput: TypeAlias = Annotated[
    DiagnosisRunExecutionInput | MainAgentRunExecutionInput,
    Field(discriminator="runtime_kind"),
]


class RunEventSignal(_FrozenExecutionContract):
    """非终止安全事件 signal。"""

    kind: Literal["event"] = "event"
    event: DiagnosisExecutionEvent


class RunDiagnosisResultSignal(_FrozenExecutionContract):
    """legacy 诊断完成 signal。"""

    kind: Literal["diagnosis_result"] = "diagnosis_result"
    result: DiagnosisExecutionResult


class RunMainDeliverySignal(_FrozenExecutionContract):
    """MainAgent typed 交付完成 signal。"""

    kind: Literal["main_delivery"] = "main_delivery"
    delivery: MainDeliveryV1


class RunFailureSignal(_FrozenExecutionContract):
    """不携带上游原文的封闭失败 signal。"""

    kind: Literal["failure"] = "failure"
    code: RunFailureCode


RunSignal: TypeAlias = Annotated[
    RunEventSignal | RunDiagnosisResultSignal | RunMainDeliverySignal | RunFailureSignal,
    Field(discriminator="kind"),
]


class RunExecutor(Protocol):
    """按 Run 冻结输入执行并输出封闭信号流。"""

    def stream(self, execution_input: RunExecutionInput) -> Iterator[RunSignal]:
        """输出零到多个 event，并以恰好一个完成或失败 signal 终止。"""


class LegacyDiagnosisRunAdapter:
    """把旧 DiagnosisExecutor 桥接为 typed RunExecutor，保留原 query/service 语义。"""

    def __init__(self, executor: DiagnosisExecutor) -> None:
        self._executor = executor

    def stream(self, execution_input: RunExecutionInput) -> Iterator[RunSignal]:
        """只接受 diagnosis 输入；未知输入安全失败。"""
        if not isinstance(execution_input, DiagnosisRunExecutionInput):
            raise RunExecutionError(RunFailureCode.MAIN_AGENT_FAILED)
        stream = self._executor.stream
        items = (
            stream(execution_input.query, execution_input.service_id)
            if len(signature(stream).parameters) >= 2
            else stream(execution_input.query)
        )
        for item in items:
            if isinstance(item, DiagnosisExecutionEvent):
                yield RunEventSignal(event=item)
            elif isinstance(item, DiagnosisExecutionResult):
                yield RunDiagnosisResultSignal(result=item)
            else:
                raise RunExecutionError(RunFailureCode.DIAGNOSIS_FAILED)


def build_main_input_snapshot(
    value: MainInputV1,
    context: tuple[MainContextMessageV1, ...] = (),
) -> MainInputSnapshotV1:
    """在受理侧生成材料 ID、规范化文本与内容摘要。"""
    return MainInputSnapshotV1(
        schema_version=1,
        query=value.query,
        text_a=_material_snapshot(value.text_a),
        text_b=_material_snapshot(value.text_b),
        rule_version=MAIN_AGENT_RULE_VERSION,
        context=context,
    )


def rebuild_main_input_snapshot(snapshot: MainInputSnapshotV1) -> MainInputSnapshotV1:
    """重跑复制冻结输入并生成本 Run 的材料 ID，不重新采样上下文。"""
    if snapshot.rule_version != MAIN_AGENT_RULE_VERSION:
        raise UnsupportedMainAgentRuleError()
    return MainInputSnapshotV1(
        schema_version=1,
        query=snapshot.query,
        text_a=_copy_material(snapshot.text_a),
        text_b=_copy_material(snapshot.text_b),
        rule_version=snapshot.rule_version,
        context=snapshot.context,
    )


def _material_snapshot(value: str | None) -> MainMaterialSnapshotV1 | None:
    """原始材料为空缺时保留 None；显式空字符串仍生成快照。"""
    if value is None:
        return None
    normalized = validate_material_text(value)
    return MainMaterialSnapshotV1(
        material_id=uuid4(),
        original_text=value,
        normalized_text=normalized,
        content_sha256=material_digest(normalized),
    )


def _copy_material(material: MainMaterialSnapshotV1 | None) -> MainMaterialSnapshotV1 | None:
    """复制材料内容但更换材料身份。"""
    if material is None:
        return None
    return MainMaterialSnapshotV1(
        material_id=uuid4(),
        original_text=material.original_text,
        normalized_text=material.normalized_text,
        content_sha256=material.content_sha256,
    )


def assert_main_input_is_safe(value: MainInputV1) -> None:
    """在落库与模型调用前拒绝凭据形态输入；不返回命中内容。"""
    if main_input_has_sensitive_content(value):
        raise MainAgentInputRejectedError()


def main_agent_create_fingerprint(value: MainInputV1) -> str:
    """计算创建摘要：区分缺失与空文本，不包含服务端材料 ID。"""
    payload = {
        "tag": MAIN_AGENT_CREATE_FINGERPRINT_TAG,
        "runtime_kind": "main_agent",
        "schema_version": value.schema_version,
        "query": value.query,
        "text_a": value.text_a,
        "text_b": value.text_b,
    }
    return _fingerprint(payload)


def main_agent_rerun_fingerprint(source_run_id: UUID, snapshot: MainInputSnapshotV1) -> str:
    """计算重跑摘要：纳入来源 Run、规则版本与冻结输入，不包含每 Run 材料 ID。"""
    payload = {
        "tag": MAIN_AGENT_RERUN_FINGERPRINT_TAG,
        "runtime_kind": "main_agent",
        "source_run_id": str(source_run_id),
        "schema_version": snapshot.schema_version,
        "rule_version": snapshot.rule_version,
        "query": snapshot.query,
        "text_a": snapshot.text_a.original_text if snapshot.text_a is not None else None,
        "text_b": snapshot.text_b.original_text if snapshot.text_b is not None else None,
        "context": [
            {
                "message_id": str(message.message_id),
                "role": message.role,
                "content": message.content,
            }
            for message in snapshot.context
        ],
    }
    return _fingerprint(payload)


def _fingerprint(payload: dict[str, object]) -> str:
    """固定序列化后计算 64 位十六进制摘要。"""
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(serialized.encode("utf-8")).hexdigest()


def validate_main_delivery(
    delivery: MainDeliveryV1,
    run: DiagnosisRunData,
    snapshot: MainInputSnapshotV1,
) -> None:
    """写成功事务前复核 typed 交付与冻结输入的身份、行号和引文。"""
    if isinstance(delivery, MainNeedsInputDeliveryV1):
        available = {
            side
            for side, material in (("text_a", snapshot.text_a), ("text_b", snapshot.text_b))
            if material is None
        }
        if set(delivery.missing) != available:
            raise RunExecutionError(RunFailureCode.MAIN_AGENT_DELIVERY_INVALID)
        return
    if isinstance(delivery, MainAnswerDeliveryV1):
        return
    if not isinstance(delivery, MainComparisonDeliveryV1):
        raise RunExecutionError(RunFailureCode.MAIN_AGENT_DELIVERY_INVALID)
    comparison = delivery.comparison
    if snapshot.text_a is None or snapshot.text_b is None:
        raise RunExecutionError(RunFailureCode.MAIN_AGENT_DELIVERY_INVALID)
    try:
        expected = compare_materials(
            run_id=run.id,
            text_a=snapshot.text_a,
            text_b=snapshot.text_b,
        )
    except TextComparisonRuleError:
        raise RunExecutionError(RunFailureCode.MAIN_AGENT_DELIVERY_INVALID) from None
    # 身份、版本与完整块序列必须等于对冻结输入重新求得的结果，不能只抽查局部引文。
    if comparison != expected:
        raise RunExecutionError(RunFailureCode.MAIN_AGENT_DELIVERY_INVALID)


def safe_failure_signal(code: RunFailureCode) -> RunFailureSignal:
    """由封闭码构造失败 signal，丢弃任何上游文案。"""
    return RunFailureSignal(code=code)


def diagnosis_failure_tuple() -> tuple[str, str]:
    """legacy 诊断失败的唯一安全二元组。"""
    return RunFailureCode.DIAGNOSIS_FAILED.value, RunFailureCode.DIAGNOSIS_FAILED.safe_message


def main_agent_failure_tuple() -> tuple[str, str]:
    """MainAgent 未知失败的唯一安全二元组。"""
    return RunFailureCode.MAIN_AGENT_FAILED.value, RunFailureCode.MAIN_AGENT_FAILED.safe_message


def failure_tuple_for_exception(error: Exception) -> tuple[str, str]:
    """把执行期异常收敛为封闭安全码，不读取异常文本。"""
    if isinstance(error, RunExecutionError):
        return error.code.value, error.code.safe_message
    if isinstance(error, DiagnosisExecutionError):
        return diagnosis_failure_tuple()
    return main_agent_failure_tuple()
