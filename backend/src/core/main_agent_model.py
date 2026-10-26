"""V2 唯一模型决策边界：调用失败与 JSON／schema 无效分别收敛为封闭失败。"""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Literal, TypeAlias
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter, ValidationError, field_validator, model_validator

from src.core.llm import LLMClient
from src.domain.main_agent import (
    MAIN_AGENT_CAPABILITY_ID,
    MAIN_AGENT_CAPABILITY_VERSION,
    MAX_ANSWER_CODEPOINTS,
)


class MainDecisionFailureCode(StrEnum):
    """模型决策边界的两种封闭失败。"""

    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_DECISION_INVALID = "MODEL_DECISION_INVALID"


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
    """材料追问决策：只声明缺失材料身份，追问文案由后端固定生成。"""

    kind: Literal["needs_input"] = "needs_input"
    missing: tuple[Literal["text_a", "text_b"], ...] = Field(min_length=1, max_length=2)

    @model_validator(mode="after")
    def _unique_missing(self) -> MainNeedsInputDecision:
        if len(set(self.missing)) != len(self.missing):
            raise ValueError("缺失材料不允许重复。")
        return self


class MainInvokeCapabilityDecision(_FrozenDecision):
    """能力调用决策：只允许已注册能力与当前 Run 的材料引用。"""

    kind: Literal["invoke_capability"] = "invoke_capability"
    capability_id: Literal["text.literal_compare"] = MAIN_AGENT_CAPABILITY_ID
    capability_version: Literal[1] = MAIN_AGENT_CAPABILITY_VERSION
    a_material_id: UUID
    b_material_id: UUID

    @model_validator(mode="after")
    def _distinct_materials(self) -> MainInvokeCapabilityDecision:
        if self.a_material_id == self.b_material_id:
            raise ValueError("A／B 材料引用必须互不相同。")
        return self


MainDecisionV1: TypeAlias = Annotated[
    MainAnswerDecision | MainNeedsInputDecision | MainInvokeCapabilityDecision,
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


class ModelDecisionSuccess(_FrozenDecision):
    """模型调用成功且 JSON／schema 校验通过。"""

    outcome: Literal["success"] = "success"
    decision: MainDecisionV1


class ModelDecisionFailure(_FrozenDecision):
    """模型边界封闭失败；不携带原始响应或异常。"""

    outcome: Literal["failure"] = "failure"
    code: MainDecisionFailureCode


ModelDecisionResult: TypeAlias = ModelDecisionSuccess | ModelDecisionFailure


class MainMockScenario(StrEnum):
    """显式声明的 V2 mock 决策场景；未声明或未知值一律不可用。"""

    ANSWER = "answer"
    NEEDS_INPUT = "needs_input"
    COMPARE = "compare"


MOCK_ANSWER_TEXT = "（模拟模型）这是一条普通回答，未执行文本比较。"


def parse_main_mock_scenario(value: str | None) -> MainMockScenario | None:
    """解析显式场景名；未知值安全返回 None，不做词汇推断。"""
    if value is None or not value.strip():
        return None
    try:
        return MainMockScenario(value.strip().lower())
    except ValueError:
        return None


class MainAgentModelAdapter:
    """V2 唯一模型决策边界：一次调用、一次 JSON 解析、封闭失败。"""

    def __init__(
        self,
        client: LLMClient,
        *,
        mock_scenario: MainMockScenario | None = None,
    ) -> None:
        self._client = client
        self._mock_scenario = mock_scenario

    @property
    def is_mock(self) -> bool:
        """返回是否使用显式 mock 决策替身；界面据此标注 mock 模型。"""
        return self._client.is_mock

    def decide(self, request: MainDecisionRequest) -> ModelDecisionResult:
        """调用模型并返回 typed 决策；任何失败都不执行工具。"""
        if self._client.is_mock:
            decision = self._mock_decision(request)
            if decision is None:
                return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE)
            return ModelDecisionSuccess(decision=decision)

        response = self._client.chat(
            [{"role": message.role, "content": message.content} for message in request.messages],
            tools=None,
        )
        content = response.get("content")
        if "error" in response or not isinstance(content, str) or not content:
            return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE)
        try:
            payload = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_DECISION_INVALID)
        if not isinstance(payload, dict):
            return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_DECISION_INVALID)
        try:
            decision = _DECISION_ADAPTER.validate_python(payload)
        except ValidationError:
            return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_DECISION_INVALID)
        return ModelDecisionSuccess(decision=decision)

    def _mock_decision(self, request: MainDecisionRequest) -> MainDecisionV1 | None:
        """按显式场景返回固定决策；场景与材料状态不符时不可用。"""
        refs = request.material_refs
        if self._mock_scenario is MainMockScenario.ANSWER:
            return MainAnswerDecision(text=MOCK_ANSWER_TEXT)
        missing: list[Literal["text_a", "text_b"]] = []
        if refs.text_a is None:
            missing.append("text_a")
        if refs.text_b is None:
            missing.append("text_b")
        if self._mock_scenario is MainMockScenario.NEEDS_INPUT:
            if not missing:
                return None
            return MainNeedsInputDecision(missing=tuple(missing))
        if self._mock_scenario is MainMockScenario.COMPARE:
            if refs.text_a is None or refs.text_b is None:
                return None
            return MainInvokeCapabilityDecision(
                a_material_id=refs.text_a,
                b_material_id=refs.text_b,
            )
        return None
