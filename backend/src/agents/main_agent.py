"""V2 主 Agent：一次 typed 决策，至多一次能力调用，交付由确定性程序生成。"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Literal, cast
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.capabilities import CapabilityDefinition, MaterialSide
from src.core.agent import BaseAgent
from src.core.llm import LLMClient
from src.core.main_agent_graph import (
    CapabilityCallOutcome,
    MainAgentFailure,
    MainAgentOutcome,
    MainGraphState,
    build_main_agent_graph,
    outcome_from_state,
)
from src.core.main_agent_model import (
    MainAgentModelAdapter,
    MainDecisionFailureCode,
    MainDecisionMaterialRefs,
    MainDecisionRequest,
    MainInvokeCapabilityDecision,
    MainPromptMessage,
    ModelDecisionFailure,
    ModelDecisionResult,
)
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import ToolRegistry
from src.domain.main_agent import (
    MAIN_AGENT_CAPABILITY_ID,
    MAIN_AGENT_RULE_VERSION,
    MAX_MAIN_QUERY_CODEPOINTS,
    MainContextMessageV1,
    TextComparisonV1,
    main_delivery_message,
)

MAIN_AGENT_INPUT_INVALID_TEXT = "主 Agent 输入无效，请重新发起。"
MAIN_AGENT_FAILED_TEXT = "主 Agent 执行失败，请稍后重试"


class MainAgentTask(BaseModel):
    """单次 Run 的冻结任务：只含身份、目标、材料引用与限额，不含原文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    session_id: UUID
    query: str = Field(min_length=1, max_length=MAX_MAIN_QUERY_CODEPOINTS)
    context: tuple[MainContextMessageV1, ...] = ()
    material_refs: MainDecisionMaterialRefs
    capability_id: Literal["text.literal_compare"]
    capability_version: Literal[1]
    rule_version: Literal["literal-lines@1"] = MAIN_AGENT_RULE_VERSION
    allowed_tools: tuple[str, ...] = Field(min_length=1)
    max_model_calls: int = Field(default=4, ge=1, le=4)
    max_tool_calls: int = Field(default=1, ge=1, le=1)

    @field_validator("query")
    @classmethod
    def _check_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("query 不能为空。")
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("query 包含非法 Unicode 码点。") from None
        return value


class MainAgent(BaseAgent):
    """BaseAgent 子类；正式入口是 typed `run_task`，保留兼容 `run`。"""

    def __init__(
        self,
        *,
        llm: LLMClient,
        adapter: MainAgentModelAdapter,
        tools: ToolRegistry,
        gateway: ToolGateway,
        capability: CapabilityDefinition,
    ) -> None:
        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt="",
            max_steps=1,
            enable_long_term_memory=False,
        )
        self._adapter = adapter
        self._gateway = gateway
        self._capability = capability
        self._model_calls = 0
        self._tool_calls = 0

    def run(self, user_input: str) -> str:
        """兼容入口：把无材料输入包装成同一 typed 路径，不形成第二实现。"""
        try:
            task = MainAgentTask(
                run_id=uuid4(),
                session_id=uuid4(),
                query=user_input,
                material_refs=MainDecisionMaterialRefs(),
                capability_id=MAIN_AGENT_CAPABILITY_ID,
                capability_version=1,
                allowed_tools=self._capability.allowed_tools,
            )
        except ValidationError:
            return MAIN_AGENT_INPUT_INVALID_TEXT
        outcome = self.run_task(task)
        if outcome.delivery is not None:
            return main_delivery_message(outcome.delivery)
        return MAIN_AGENT_FAILED_TEXT

    def run_task(self, task: MainAgentTask) -> MainAgentOutcome:
        """执行一个有界决策图；每次调用都使用本次 Run 的全新状态。"""
        if task.capability_id != self._capability.capability_id or task.capability_version != self._capability.version:
            return MainAgentOutcome(failure=MainAgentFailure.CAPABILITY_UNAVAILABLE)
        if tuple(task.allowed_tools) != self._capability.allowed_tools:
            return MainAgentOutcome(failure=MainAgentFailure.CAPABILITY_UNAVAILABLE)
        self._model_calls = 0
        self._tool_calls = 0
        actual_missing = _missing_sides(task.material_refs)
        graph = build_main_agent_graph(
            decide=lambda: self._decide(task),
            actual_missing=actual_missing,
            material_refs=task.material_refs,
            capability_id=self._capability.capability_id,
            capability_version=self._capability.version,
            run_capability=self._invoke_capability(task),
        )
        state = cast(MainGraphState, graph.invoke({}, config={"recursion_limit": 6}))
        return outcome_from_state(state)

    def _decide(self, task: MainAgentTask) -> ModelDecisionResult:
        """执行至多一次模型决策；计数先于调用，失败也计入尝试。"""
        if self._model_calls >= task.max_model_calls:
            return ModelDecisionFailure(code=MainDecisionFailureCode.MODEL_UNAVAILABLE)
        self._model_calls += 1
        return self._adapter.decide(_decision_request(task, self._capability))

    def _invoke_capability(
        self,
        task: MainAgentTask,
    ) -> Callable[[MainInvokeCapabilityDecision], CapabilityCallOutcome]:
        """构造能力调用闭包：只经 Gateway，只允许声明内 Tool。"""

        def invoke(decision: MainInvokeCapabilityDecision) -> CapabilityCallOutcome:
            tool_name = self._capability.allowed_tools[0]
            if self._tool_calls >= task.max_tool_calls or self.tools.get(tool_name) is None:
                return CapabilityCallOutcome(tool_status="rejected", failure=MainAgentFailure.TOOL_FAILED)
            arguments = json.dumps(
                {
                    "a_material_id": str(decision.a_material_id),
                    "b_material_id": str(decision.b_material_id),
                    "rule_version": task.rule_version,
                },
                ensure_ascii=False,
            )
            self._tool_calls += 1
            result = self._gateway.invoke(tool_name, arguments)
            if result.record.status != "ok":
                return CapabilityCallOutcome(
                    tool_status=result.record.status,
                    failure=MainAgentFailure.TOOL_FAILED,
                )
            try:
                comparison = TextComparisonV1.model_validate_json(result.output)
            except ValidationError:
                return CapabilityCallOutcome(
                    tool_status=result.record.status,
                    failure=MainAgentFailure.DELIVERY_INVALID,
                )
            if (
                comparison.run_id != task.run_id
                or comparison.a_material_id != decision.a_material_id
                or comparison.b_material_id != decision.b_material_id
                or comparison.rule_version != task.rule_version
            ):
                return CapabilityCallOutcome(
                    tool_status=result.record.status,
                    failure=MainAgentFailure.DELIVERY_INVALID,
                )
            return CapabilityCallOutcome(comparison=comparison, tool_status="ok")

        return invoke


def _missing_sides(refs: MainDecisionMaterialRefs) -> tuple[MaterialSide, ...]:
    """由材料引用推导实际缺失侧，顺序固定。"""
    missing: list[MaterialSide] = []
    if refs.text_a is None:
        missing.append("text_a")
    if refs.text_b is None:
        missing.append("text_b")
    return tuple(missing)


def _decision_request(task: MainAgentTask, capability: CapabilityDefinition) -> MainDecisionRequest:
    """构造模型可见信息：目标与材料身份，绝不含 A/B 原文。"""
    messages = [
        MainPromptMessage(
            role="system",
            content=(
                "你是 OperMind 主 Agent。只输出一个 JSON 对象，不要输出 Markdown、代码块或额外文字。\n"
                "允许的决策：\n"
                '1. {"kind":"answer","text":"..."}：普通回答，不得声称已完成文本比较。\n'
                '2. {"kind":"needs_input","missing":["text_a"]}：材料缺失；missing 只写实际缺失侧。\n'
                '3. {"kind":"invoke_capability","capability_id":"text.literal_compare",'
                '"capability_version":1,"a_material_id":"<材料A的ID>","b_material_id":"<材料B的ID>"}。\n'
                f"能力说明：{capability.description}\n"
                f"使用指引：{capability.usage_guide}\n"
                "只引用下方列出的材料 ID；不要输出或复述材料正文。"
            ),
        )
    ]
    messages.extend(
        MainPromptMessage(role=message.role, content=message.content)
        for message in task.context
    )
    messages.append(
        MainPromptMessage(
            role="user",
            content=(
                f"本次目标：{task.query}\n"
                f"材料 A：{_material_line(task.material_refs.text_a)}\n"
                f"材料 B：{_material_line(task.material_refs.text_b)}"
            ),
        )
    )
    return MainDecisionRequest(
        messages=tuple(messages),
        material_refs=task.material_refs,
    )


def _material_line(material_id: UUID | None) -> str:
    """描述材料是否提供；未提供不生成任何伪引用。"""
    return "未提供" if material_id is None else f"已提供，材料 ID：{material_id}"
