"""Capability 契约 v1：声明身份、类型、输入输出、资源、工具与完成语义。

契约只描述能力本身，不持有 Tool、连接、凭据或执行句柄；注册表与主循环只读声明。
知识型能力不允许声明工具、资源或权限；执行型能力必须声明只读权限、工具与输出契约。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from src.domain.main_agent import MAX_SKILL_CODEPOINTS

CAPABILITY_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
MATERIAL_SLOT_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
RESOURCE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_.-]{0,63}$")
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")

MAX_CAPABILITY_ID_CODEPOINTS = 64
MAX_TITLE_CODEPOINTS = 40
MAX_DESCRIPTION_CODEPOINTS = 280
MAX_USAGE_GUIDE_CODEPOINTS = 600
MAX_INSTRUCTION_CODEPOINTS = 400
MAX_SKILL_TITLE_CODEPOINTS = 80

class CapabilityKind(StrEnum):
    """能力类型：知识型只装 Skill，执行型只经 ToolGateway。"""

    KNOWLEDGE = "knowledge"
    EXECUTION = "execution"


class CompletionSemantics(StrEnum):
    """能力完成后的交付语义。"""

    RESPONSE = "response"
    TYPED_RESULT = "typed_result"


class FailureSemantics(StrEnum):
    """能力声明必须覆盖的封闭失败语义；主循环据此选择安全失败。"""

    INPUT_MISSING = "input_missing"
    INPUT_INVALID = "input_invalid"
    SOURCE_UNAVAILABLE = "source_unavailable"
    SOURCE_INVALID = "source_invalid"
    TOOL_UNAVAILABLE = "tool_unavailable"
    TOOL_TIMEOUT = "tool_timeout"
    RESULT_INVALID = "result_invalid"
    BUDGET_EXHAUSTED = "budget_exhausted"


_KNOWLEDGE_FAILURES = frozenset(
    {
        FailureSemantics.INPUT_MISSING,
        FailureSemantics.SOURCE_UNAVAILABLE,
        FailureSemantics.SOURCE_INVALID,
    }
)
_EXECUTION_FAILURES = frozenset(
    {
        FailureSemantics.INPUT_MISSING,
        FailureSemantics.INPUT_INVALID,
        FailureSemantics.TOOL_UNAVAILABLE,
        FailureSemantics.TOOL_TIMEOUT,
        FailureSemantics.RESULT_INVALID,
        FailureSemantics.BUDGET_EXHAUSTED,
    }
)


def _require_text(value: object, field_name: str, *, maximum: int) -> str:
    """校验契约文本为可编码、非空且不超上限的字符串；错误不回显正文。"""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} 必须是非空字符串。")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(f"{field_name} 包含非法 Unicode 码点。") from None
    if len(value) > maximum:
        raise ValueError(f"{field_name} 超过 {maximum} 码点上限。")
    return value


def _require_optional_text(value: object, field_name: str, *, maximum: int) -> str | None:
    if value is None:
        return None
    return _require_text(value, field_name, maximum=maximum)


@dataclass(frozen=True, slots=True)
class MaterialSlot:
    """能力声明的一个材料槽位；V2-1 只支持 material slots。"""

    slot: str
    label: str

    def __post_init__(self) -> None:
        if not isinstance(self.slot, str) or MATERIAL_SLOT_PATTERN.fullmatch(self.slot) is None:
            raise ValueError("材料槽位名必须是小写字母开头的标识符。")
        _require_text(self.label, "材料槽位标签", maximum=MAX_TITLE_CODEPOINTS)


@dataclass(frozen=True, slots=True)
class CapabilityInputContract:
    """输入契约：V2-1 只有 material slots，全部必填。"""

    material_slots: tuple[MaterialSlot, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.material_slots, tuple):
            raise ValueError("材料槽位必须是元组。")
        names = [item.slot for item in self.material_slots]
        if len(set(names)) != len(names):
            raise ValueError("材料槽位不允许重复。")
        if len(names) > 8:
            raise ValueError("材料槽位数量超过上限。")


@dataclass(frozen=True, slots=True)
class CapabilityOutputContract:
    """输出契约：V2-1 只允许已校验比较结果或纯文本回答。"""

    delivery_kind: Literal["comparison"] | None = None
    result_schema: str | None = None
    summary_fields: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.delivery_kind is None:
            if self.result_schema is not None or self.summary_fields:
                raise ValueError("知识型输出契约不得声明 typed 结果字段。")
            return
        if self.delivery_kind != "comparison":
            raise ValueError("V2-1 只支持 comparison 交付类型。")
        _require_text(self.result_schema, "结果 schema", maximum=64)
        if not isinstance(self.summary_fields, tuple) or not self.summary_fields:
            raise ValueError("typed 输出契约必须声明摘要字段。")
        if len(self.summary_fields) > 16:
            raise ValueError("摘要字段数量超过上限。")
        for name in self.summary_fields:
            _require_text(name, "摘要字段", maximum=40)


@dataclass(frozen=True, slots=True)
class ResourceDeclaration:
    """执行型能力显式声明的只读资源；不包含句柄或凭据。"""

    resource: str
    access: Literal["read_only"] = "read_only"

    def __post_init__(self) -> None:
        if not isinstance(self.resource, str) or RESOURCE_ID_PATTERN.fullmatch(self.resource) is None:
            raise ValueError("资源名必须是小写标识符。")
        if self.access != "read_only":
            raise ValueError("V2-1 只允许只读资源声明。")


@dataclass(frozen=True, slots=True)
class SkillDeclaration:
    """知识型能力声明的受管 Skill；V2-1 只允许仓库内置来源。"""

    source: Literal["builtin"]
    skill_id: str
    skill_version: int
    title: str
    expected_sha256: str
    max_codepoints: int = MAX_SKILL_CODEPOINTS

    def __post_init__(self) -> None:
        if self.source != "builtin":
            raise ValueError("V2-1 只允许 builtin Skill 来源。")
        if not isinstance(self.skill_id, str) or CAPABILITY_ID_PATTERN.fullmatch(self.skill_id) is None:
            raise ValueError("Skill id 必须是命名空间小写标识符。")
        if type(self.skill_version) is not int or self.skill_version < 1:
            raise ValueError("Skill 版本必须是正整数。")
        _require_text(self.title, "Skill 标题", maximum=MAX_SKILL_TITLE_CODEPOINTS)
        if not isinstance(self.expected_sha256, str) or SHA256_PATTERN.fullmatch(self.expected_sha256) is None:
            raise ValueError("Skill 摘要必须是 64 位小写十六进制。")
        if type(self.max_codepoints) is not int or not 1 <= self.max_codepoints <= MAX_SKILL_CODEPOINTS:
            raise ValueError(f"Skill 大小上限必须介于 1 和 {MAX_SKILL_CODEPOINTS} 码点之间。")


@dataclass(frozen=True, slots=True)
class CapabilityDefinition:
    """一个能力版本的可校验声明；不持有任何执行句柄。"""

    capability_id: str
    version: int
    kind: CapabilityKind
    title: str
    description: str
    usage_guide: str
    instruction: str
    input_contract: CapabilityInputContract = field(default_factory=CapabilityInputContract)
    output_contract: CapabilityOutputContract = field(default_factory=CapabilityOutputContract)
    resources: tuple[ResourceDeclaration, ...] = ()
    permissions: tuple[Literal["read_only"], ...] = ()
    tool_bindings: tuple[str, ...] = ()
    completion: CompletionSemantics = CompletionSemantics.RESPONSE
    failure: tuple[FailureSemantics, ...] = ()
    skill: SkillDeclaration | None = None
    rule_version: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.capability_id, str)
            or CAPABILITY_ID_PATTERN.fullmatch(self.capability_id) is None
            or len(self.capability_id) > MAX_CAPABILITY_ID_CODEPOINTS
        ):
            raise ValueError("capability_id 必须是命名空间小写标识符且不超过 64 码点。")
        if type(self.version) is not int or self.version < 1:
            raise ValueError("能力版本必须是正整数。")
        try:
            kind = CapabilityKind(self.kind)
            completion = CompletionSemantics(self.completion)
        except ValueError:
            raise ValueError("未知的能力类型或完成语义。") from None
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "completion", completion)
        _require_text(self.title, "能力标题", maximum=MAX_TITLE_CODEPOINTS)
        _require_text(self.description, "能力说明", maximum=MAX_DESCRIPTION_CODEPOINTS)
        _require_text(self.usage_guide, "使用指引", maximum=MAX_USAGE_GUIDE_CODEPOINTS)
        _require_text(self.instruction, "能力指令", maximum=MAX_INSTRUCTION_CODEPOINTS)
        if not isinstance(self.input_contract, CapabilityInputContract):
            raise ValueError("输入契约必须是 CapabilityInputContract。")
        if not isinstance(self.output_contract, CapabilityOutputContract):
            raise ValueError("输出契约必须是 CapabilityOutputContract。")
        if not isinstance(self.resources, tuple) or not all(
            isinstance(item, ResourceDeclaration) for item in self.resources
        ):
            raise ValueError("资源声明必须是 ResourceDeclaration 元组。")
        if not isinstance(self.permissions, tuple) or not isinstance(self.tool_bindings, tuple):
            raise ValueError("权限与工具绑定必须是元组。")
        if not isinstance(self.failure, tuple):
            raise ValueError("失败语义必须是元组。")
        try:
            failures = tuple(FailureSemantics(item) for item in self.failure)
        except ValueError:
            raise ValueError("未知的失败语义。") from None
        object.__setattr__(self, "failure", failures)
        if self.rule_version is not None:
            _require_optional_text(self.rule_version, "规则版本", maximum=64)
        if kind is CapabilityKind.KNOWLEDGE:
            self._validate_knowledge(failures)
        else:
            self._validate_execution(failures)

    def _validate_knowledge(self, failures: tuple[FailureSemantics, ...]) -> None:
        if self.permissions or self.tool_bindings or self.resources:
            raise ValueError("知识型能力不得声明工具、资源或权限。")
        if self.output_contract.delivery_kind is not None:
            raise ValueError("知识型能力不得声明 typed 交付。")
        if self.completion is not CompletionSemantics.RESPONSE:
            raise ValueError("知识型能力完成语义必须是 response。")
        if self.skill is None:
            raise ValueError("知识型能力必须声明 Skill 来源。")
        if not failures or not set(failures) <= _KNOWLEDGE_FAILURES:
            raise ValueError("知识型能力失败语义超出允许范围。")

    def _validate_execution(self, failures: tuple[FailureSemantics, ...]) -> None:
        if self.permissions != ("read_only",):
            raise ValueError("执行型能力权限必须且只能是 read_only。")
        if not self.tool_bindings:
            raise ValueError("执行型能力必须声明至少一个工具绑定。")
        if any(not isinstance(name, str) or not name for name in self.tool_bindings):
            raise ValueError("工具绑定名必须是非空字符串。")
        if len(set(self.tool_bindings)) != len(self.tool_bindings):
            raise ValueError("工具绑定不允许重复。")
        if self.output_contract.delivery_kind is None:
            raise ValueError("执行型能力必须声明 typed 交付。")
        if self.completion is not CompletionSemantics.TYPED_RESULT:
            raise ValueError("执行型能力完成语义必须是 typed_result。")
        if self.skill is not None:
            raise ValueError("执行型能力不得声明 Skill。")
        if not failures or not set(failures) <= _EXECUTION_FAILURES:
            raise ValueError("执行型能力失败语义超出允许范围。")

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        """兼容 V2-0 的工具菜单读取；等价于 tool_bindings。"""
        return self.tool_bindings

    @property
    def required_materials(self) -> tuple[str, ...]:
        """兼容 V2-0 的必填材料读取；由输入契约派生。"""
        return tuple(item.slot for item in self.input_contract.material_slots)


@dataclass(frozen=True, slots=True)
class CapabilitySummary:
    """模型可见的能力安全摘要；不含实现、资源句柄或凭据。"""

    capability_id: str
    version: int
    kind: CapabilityKind
    title: str
    description: str
    usage_guide: str
    input_slots: tuple[MaterialSlot, ...]
    available: bool = True


@dataclass(frozen=True, slots=True)
class CapabilityResolution:
    """按 id + version + 期望类型解析的封闭结果。"""

    kind: ResolutionKind
    definition: CapabilityDefinition | None = None
    expected_kind: CapabilityKind | None = None
    actual_kind: CapabilityKind | None = None

    @property
    def resolved(self) -> bool:
        return self.kind is ResolutionKind.RESOLVED


class ResolutionKind(StrEnum):
    """能力解析的五种封闭结果。"""

    RESOLVED = "resolved"
    UNKNOWN_ID = "unknown_id"
    UNKNOWN_VERSION = "unknown_version"
    INACTIVE_VERSION = "inactive_version"
    KIND_MISMATCH = "kind_mismatch"
