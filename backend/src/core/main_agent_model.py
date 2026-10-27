"""V2 唯一模型决策边界：调用失败与 JSON／schema 无效分别收敛为封闭失败。"""

from __future__ import annotations

import json
from collections.abc import Callable
from enum import StrEnum

from pydantic import ValidationError

from src.core.llm import LLMClient
from src.core.main_agent_decisions import (
    _DECISION_ADAPTER,
    MainAnswerDecision,
    MainDecisionFailureCode,
    MainDecisionMaterialRefs,
    MainDecisionRequest,
    MainDecisionV1,
    MainInvokeCapabilityDecision,
    MainLoadSkillDecision,
    MainNeedsInputDecision,
    MainPromptMessage,
    ModelDecisionFailure,
    ModelDecisionResult,
    ModelDecisionSuccess,
)
from src.domain.main_agent import MAX_MODEL_CALL_SECONDS

MOCK_ANSWER_TEXT = "（模拟模型）这是一条普通回答，未执行文本比较。"
MOCK_KNOWLEDGE_ANSWER_TEXT = (
    "（模拟模型）这是基于内置只读排查手册的回答：先确认问题口径，再按慢查询、锁等待、"
    "连接池和日志错误逐步检查。知识辅助回答 · 未读取实时数据。"
)
_MOCK_KNOWLEDGE_CAPABILITY_ID = "ops.readonly_playbook"
_MOCK_KNOWLEDGE_CAPABILITY_VERSION = 1


class MainMockScenario(StrEnum):
    """显式声明的 V2 mock 决策场景；未声明或未知值一律不可用。"""

    ANSWER = "answer"
    NEEDS_INPUT = "needs_input"
    COMPARE = "compare"
    KNOWLEDGE = "knowledge"
    UNKNOWN_CAPABILITY = "unknown_capability"
    WRONG_VERSION = "wrong_version"
    BUDGET_EXHAUSTED = "budget_exhausted"


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
        client: LLMClient | None = None,
        *,
        client_factory: Callable[[float], LLMClient] | None = None,
        mock_scenario: MainMockScenario | None = None,
    ) -> None:
        if (client is None) == (client_factory is None):
            raise ValueError("必须且只能提供固定客户端或按超时构造客户端的工厂。")
        self._client = client
        self._client_factory = client_factory
        self._mock_scenario = mock_scenario
        self._mock_probe: bool | None = None

    @property
    def is_mock(self) -> bool:
        """返回是否使用显式 mock 决策替身；界面据此标注 mock 模型。"""
        if self._client is not None:
            return self._client.is_mock
        if self._mock_probe is None:
            probe = self._client_factory(MAX_MODEL_CALL_SECONDS)  # type: ignore[misc]
            self._mock_probe = probe.is_mock
        return self._mock_probe

    def decide(
        self,
        request: MainDecisionRequest,
        timeout_seconds: float | None = None,
    ) -> ModelDecisionResult:
        """调用模型并返回 typed 决策；任何失败都不执行工具。"""
        client = self._resolve_client(timeout_seconds)
        if client.is_mock:
            decision = self._mock_decision(request)
            if decision is None:
                return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE)
            return ModelDecisionSuccess(decision=decision)

        response = client.chat(
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

    def _resolve_client(self, timeout_seconds: float | None) -> LLMClient:
        """每次模型调用都按有效超时构造客户端，保证剩余预算可截断等待。"""
        if self._client is not None:
            return self._client
        effective = MAX_MODEL_CALL_SECONDS if timeout_seconds is None else timeout_seconds
        return self._client_factory(effective)  # type: ignore[misc]

    def _mock_decision(self, request: MainDecisionRequest) -> MainDecisionV1 | None:
        """按显式场景返回固定决策；场景与材料状态不符时不可用。"""
        refs = request.material_refs
        missing = [
            side for side in ("text_a", "text_b") if getattr(refs, side) is None
        ]
        if self._mock_scenario is MainMockScenario.ANSWER:
            return MainAnswerDecision(text=MOCK_ANSWER_TEXT)
        if self._mock_scenario is MainMockScenario.NEEDS_INPUT:
            if not missing:
                return None
            return MainNeedsInputDecision(slots=tuple(missing))
        if self._mock_scenario is MainMockScenario.COMPARE:
            if refs.text_a is None or refs.text_b is None:
                return None
            return MainInvokeCapabilityDecision(
                capability_id="text.literal_compare",
                capability_version=1,
                inputs={"text_a": str(refs.text_a), "text_b": str(refs.text_b)},
            )
        if self._mock_scenario is MainMockScenario.KNOWLEDGE:
            if request.observation_count == 0:
                return MainLoadSkillDecision(
                    capability_id=_MOCK_KNOWLEDGE_CAPABILITY_ID,
                    capability_version=_MOCK_KNOWLEDGE_CAPABILITY_VERSION,
                )
            return MainAnswerDecision(text=MOCK_KNOWLEDGE_ANSWER_TEXT)
        if self._mock_scenario is MainMockScenario.UNKNOWN_CAPABILITY:
            inputs = {
                side: str(material_id)
                for side in ("text_a", "text_b")
                if (material_id := getattr(refs, side)) is not None
            }
            return MainInvokeCapabilityDecision(
                capability_id="missing.capability",
                capability_version=1,
                inputs=inputs,
            )
        if self._mock_scenario is MainMockScenario.WRONG_VERSION:
            return MainLoadSkillDecision(
                capability_id=_MOCK_KNOWLEDGE_CAPABILITY_ID,
                capability_version=99,
            )
        if self._mock_scenario is MainMockScenario.BUDGET_EXHAUSTED:
            return MainLoadSkillDecision(
                capability_id=_MOCK_KNOWLEDGE_CAPABILITY_ID,
                capability_version=_MOCK_KNOWLEDGE_CAPABILITY_VERSION,
            )
        return None


__all__ = [
    "MOCK_ANSWER_TEXT",
    "MOCK_KNOWLEDGE_ANSWER_TEXT",
    "MainAgentModelAdapter",
    "MainAnswerDecision",
    "MainDecisionFailureCode",
    "MainDecisionMaterialRefs",
    "MainDecisionRequest",
    "MainDecisionV1",
    "MainInvokeCapabilityDecision",
    "MainLoadSkillDecision",
    "MainMockScenario",
    "MainNeedsInputDecision",
    "MainPromptMessage",
    "ModelDecisionFailure",
    "ModelDecisionResult",
    "ModelDecisionSuccess",
    "parse_main_mock_scenario",
]
