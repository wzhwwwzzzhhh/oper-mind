"""V2 主 Agent：把通用 ReAct 内核装配成一次显式 Run。

能力选择、知识装入与工具调用全部由 `core/main_agent_react.py` 处理；
本模块只保存 Run 身份、注入依赖并提供 typed 兼容入口。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from src.capabilities import CapabilityRegistry, MaterialSide, SkillSource
from src.core.agent import BaseAgent
from src.core.capability_tools import ToolBindingRegistry
from src.core.llm import LLMClient
from src.core.main_agent_budget import MainAgentBudget
from src.core.main_agent_decisions import MainDecisionMaterialRefs
from src.core.main_agent_model import MainAgentModelAdapter
from src.core.main_agent_react import MainReactKernel, MainReactOutcome, MainStepSignal
from src.core.tool_gateway import GatewayResult
from src.core.tool_registry import ToolRegistry
from src.domain.main_agent import (
    MAIN_AGENT_RULE_VERSION,
    MAX_MAIN_DECISIONS,
    MAX_MAIN_QUERY_CODEPOINTS,
    MainContextMessageV1,
    main_delivery_message,
)

MAIN_AGENT_INPUT_INVALID_TEXT = "主 Agent 输入无效，请重新发起。"
MAIN_AGENT_FAILED_TEXT = "主 Agent 执行失败，请稍后重试"


class MainAgentTask(BaseModel):
    """单次 Run 的冻结任务：只含身份、目标、上下文与材料引用，不含原文。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: UUID
    session_id: UUID
    query: str = Field(min_length=1, max_length=MAX_MAIN_QUERY_CODEPOINTS)
    context: tuple[MainContextMessageV1, ...] = ()
    material_refs: MainDecisionMaterialRefs
    rule_version: str = MAIN_AGENT_RULE_VERSION

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
    """BaseAgent 子类；正式入口是 typed `stream_task`／`run_task`。"""

    def __init__(
        self,
        *,
        llm: LLMClient,
        adapter: MainAgentModelAdapter,
        capabilities: CapabilityRegistry,
        skill_source: SkillSource,
        tool_bindings: ToolBindingRegistry,
        call_tool: Callable[[str, str, float], GatewayResult],
        tools: ToolRegistry | None = None,
        is_cancelled: Callable[[], bool] | None = None,
    ) -> None:
        super().__init__(
            llm=llm,
            tools=tools or ToolRegistry(),
            system_prompt="",
            max_steps=MAX_MAIN_DECISIONS,
            enable_long_term_memory=False,
        )
        self._adapter = adapter
        self._capabilities = capabilities
        self._skill_source = skill_source
        self._tool_bindings = tool_bindings
        self._call_tool = call_tool
        self._is_cancelled = is_cancelled
        self._outcome: MainReactOutcome | None = None

    @property
    def outcome(self) -> MainReactOutcome | None:
        """最近一次运行结果；未运行返回 None。"""
        return self._outcome

    def run(self, user_input: str) -> str:
        """兼容入口：无材料目标走同一 typed 路径，不形成第二实现。"""
        try:
            task = MainAgentTask(
                run_id=uuid4(),
                session_id=uuid4(),
                query=user_input,
                material_refs=MainDecisionMaterialRefs(),
            )
        except ValidationError:
            return MAIN_AGENT_INPUT_INVALID_TEXT
        outcome = self.run_task(task)
        if outcome.delivery is not None:
            return main_delivery_message(outcome.delivery)
        return MAIN_AGENT_FAILED_TEXT

    def stream_task(self, task: MainAgentTask) -> Iterator[MainStepSignal]:
        """逐 step 产出安全事件标签；结束后可从 `outcome` 读取终态。"""
        kernel = MainReactKernel(
            capabilities=self._capabilities,
            skill_source=self._skill_source,
            tool_bindings=self._tool_bindings,
            decide=self._adapter.decide,
            call_tool=self._call_tool,
            run_id=task.run_id,
            query=task.query,
            context=task.context,
            material_refs=task.material_refs,
            actual_missing=_missing_sides(task.material_refs),
            rule_version=task.rule_version,
            is_cancelled=self._is_cancelled or _never_cancelled,
            budget=MainAgentBudget(),
        )
        self._outcome = None
        yield from kernel.stream()
        self._outcome = kernel.outcome

    def run_task(self, task: MainAgentTask) -> MainReactOutcome:
        """执行一个有界 ReAct 运行；每次调用都使用全新状态。"""
        for _signal in self.stream_task(task):
            pass
        if self._outcome is None:
            raise RuntimeError("主 Agent 内核未返回结果。")
        return self._outcome


def _missing_sides(
    refs: MainDecisionMaterialRefs,
) -> tuple[MaterialSide, ...]:
    """由材料引用推导实际缺失槽位，顺序固定。"""
    missing: list[MaterialSide] = []
    if refs.text_a is None:
        missing.append("text_a")
    if refs.text_b is None:
        missing.append("text_b")
    return tuple(missing)


def _never_cancelled() -> bool:
    return False
