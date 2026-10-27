"""主 Agent 每步的封闭决策联合：普通回答、追问、加载知识、调用能力。"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, field_validator

from src.domain.main_agent import MAX_ANSWER_CODEPOINTS

_SLOT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,31}$")


class _FrozenDecision(BaseModel):
    """决策契约禁止额外字段与实例修改。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


def _require_scalar_text(value: str) -> str:
    """拒绝 UTF-8 无法编码的孤立代理码点；错误不携带原文。"""
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError("文本包含非法 Unicode 码点。") from None
    return value


class MainAnswerDecision(_FrozenDecision):
    """普通回答决策；不是已校验的文本比较。"""

    kind: Literal["answer"] = "answer"
    text: str = Field(min_length=1, max_length=MAX_ANSWER_CODEPOINTS)

    @field_validator("text")
    @classmethod
    def _check_text(cls, value: str) -> str:
        return _require_scalar_text(value)


class MainNeedsInputDecision(_FrozenDecision):
    """材料追问决策：只声明缺失槽位，追问文案由后端固定生成。"""

    kind: Literal["needs_input"] = "needs_input"
    slots: tuple[str, ...] = Field(min_length=1, max_length=8)

    @field_validator("slots")
    @classmethod
    def _valid_slots(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(values)) != len(values):
            raise ValueError("缺失槽位不允许重复。")
        for value in values:
            if _SLOT_NAME_PATTERN.fullmatch(value) is None:
                raise ValueError("缺失槽位名不合法。")
        return values


class MainLoadSkillDecision(_FrozenDecision):
    """加载知识型能力决策；只允许已注册且激活的知识能力。"""

    kind: Literal["load_skill"] = "load_skill"
    capability_id: str = Field(min_length=1, max_length=64)
    capability_version: int = Field(ge=1)


class MainInvokeCapabilityDecision(_FrozenDecision):
    """调用执行型能力决策；输入只允许材料槽位到本 Run 材料 ID 的映射。"""

    kind: Literal["invoke_capability"] = "invoke_capability"
    capability_id: str = Field(min_length=1, max_length=64)
    capability_version: int = Field(ge=1)
    inputs: dict[str, str] = Field(default_factory=dict, max_length=8)

    @field_validator("inputs")
    @classmethod
    def _valid_inputs(cls, values: dict[str, str]) -> dict[str, str]:
        for slot, material_id in values.items():
            if _SLOT_NAME_PATTERN.fullmatch(slot) is None:
                raise ValueError("能力输入槽位名不合法。")
            try:
                UUID(material_id)
            except (ValueError, TypeError, AttributeError):
                raise ValueError("能力输入必须是材料 ID。") from None
        return values


MainDecisionV1: TypeAlias = Annotated[
    MainAnswerDecision | MainNeedsInputDecision | MainLoadSkillDecision | MainInvokeCapabilityDecision,
    Field(discriminator="kind"),
]

_DECISION_ADAPTER: TypeAdapter[MainDecisionV1] = TypeAdapter(MainDecisionV1)


class MainDecisionMaterialRefs(_FrozenDecision):
    """本次决策可见的材料引用；缺失侧为 None，不携带原文。"""

    text_a: UUID | None = None
    text_b: UUID | None = None


class MainPromptMessage(_FrozenDecision):
    """一条发送给模型的可信消息。"""

    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def _check_content(cls, value: str) -> str:
        return _require_scalar_text(value)


class MainDecisionRequest(_FrozenDecision):
    """模型决策请求：提示词与材料引用分离，mock 不解析提示词选场景。"""

    messages: tuple[MainPromptMessage, ...] = Field(min_length=1)
    material_refs: MainDecisionMaterialRefs
    observation_count: int = Field(default=0, ge=0)


class MainDecisionFailureCode(StrEnum):
    """模型决策边界的两种封闭失败。"""

    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_DECISION_INVALID = "MODEL_DECISION_INVALID"


class ModelDecisionSuccess(_FrozenDecision):
    """模型调用成功且 JSON／schema 校验通过。"""

    outcome: Literal["success"] = "success"
    decision: MainDecisionV1


class ModelDecisionFailure(_FrozenDecision):
    """模型边界封闭失败；不携带原始响应或异常。"""

    outcome: Literal["failure"] = "failure"
    code: MainDecisionFailureCode


ModelDecisionResult: TypeAlias = ModelDecisionSuccess | ModelDecisionFailure
