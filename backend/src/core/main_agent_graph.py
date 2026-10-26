"""V2 主 Agent 的最小 bounded 决策图：一次决策，至多一次能力调用。

图只编排控制流；模型调用、ToolGateway 与事实写入分别由适配器、网关和
应用服务负责。节点不接触 Session、ORM 或凭据。
"""

from __future__ import annotations

from collections.abc import Callable
from enum import StrEnum
from typing import Literal, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, ConfigDict, ValidationError
from typing_extensions import TypedDict

from src.capabilities import MaterialSide
from src.core.main_agent_model import (
    MainAnswerDecision,
    MainDecisionFailureCode,
    MainDecisionMaterialRefs,
    MainDecisionV1,
    MainInvokeCapabilityDecision,
    MainNeedsInputDecision,
    ModelDecisionResult,
)
from src.domain.main_agent import (
    MainAnswerDeliveryV1,
    MainComparisonDeliveryV1,
    MainDeliveryV1,
    MainNeedsInputDeliveryV1,
    TextComparisonV1,
)

_MATERIAL_LABELS: dict[MaterialSide, str] = {
    "text_a": "文本 A（旧）",
    "text_b": "文本 B（新）",
}


class MainAgentFailure(StrEnum):
    """主 Agent 内部封闭失败；执行适配器只映射为固定 Run 失败码。"""

    MODEL_UNAVAILABLE = "model_unavailable"
    MODEL_DECISION_INVALID = "model_decision_invalid"
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    TOOL_FAILED = "tool_failed"
    DELIVERY_INVALID = "delivery_invalid"


class CapabilityCallOutcome(BaseModel):
    """一次能力调用的封闭结果；失败不带上游文案。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    comparison: TextComparisonV1 | None = None
    tool_status: str | None = None
    failure: MainAgentFailure | None = None


class MainAgentOutcome(BaseModel):
    """主 Agent 完成后交给执行适配器的 typed 结果。"""

    model_config = ConfigDict(extra="forbid", frozen=True)

    delivery: MainDeliveryV1 | None = None
    failure: MainAgentFailure | None = None
    decision_kind: Literal["answer", "needs_input", "invoke_capability"] | None = None
    tool_invoked: bool = False
    tool_status: str | None = None


class MainGraphState(TypedDict, total=False):
    """节点间传递的最小状态。"""

    decision: MainDecisionV1 | None
    decision_kind: str | None
    delivery: MainDeliveryV1 | None
    failure: MainAgentFailure | None
    tool_invoked: bool
    tool_status: str | None


def needs_input_prompt(missing: tuple[MaterialSide, ...]) -> str:
    """生成固定材料追问文案；不复制原文。"""
    labels = "和".join(_MATERIAL_LABELS[side] for side in ("text_a", "text_b") if side in missing)
    return f"请提供{labels}，我会做逐行字面比较。"


def build_main_agent_graph(
    *,
    decide: Callable[[], ModelDecisionResult],
    actual_missing: tuple[MaterialSide, ...],
    material_refs: MainDecisionMaterialRefs,
    capability_id: str,
    capability_version: int,
    run_capability: Callable[[MainInvokeCapabilityDecision], CapabilityCallOutcome],
) -> CompiledStateGraph:
    """为一个 Run 构建决策图；Run 结束后即废弃，无跨 Run 状态。"""

    def decide_node(state: MainGraphState) -> dict[str, object]:
        result = decide()
        if result.outcome == "failure":
            failure = (
                MainAgentFailure.MODEL_UNAVAILABLE
                if result.code is MainDecisionFailureCode.MODEL_UNAVAILABLE
                else MainAgentFailure.MODEL_DECISION_INVALID
            )
            return {"failure": failure}
        return {
            "decision": result.decision,
            "decision_kind": result.decision.kind,
        }

    def finalize_answer_node(state: MainGraphState) -> dict[str, object]:
        decision = state.get("decision")
        if not isinstance(decision, MainAnswerDecision):
            return {"failure": MainAgentFailure.MODEL_DECISION_INVALID}
        try:
            delivery = MainAnswerDeliveryV1(text=decision.text)
        except ValidationError:
            return {"failure": MainAgentFailure.DELIVERY_INVALID}
        return {"delivery": delivery}

    def finalize_needs_input_node(state: MainGraphState) -> dict[str, object]:
        decision = state.get("decision")
        if not isinstance(decision, MainNeedsInputDecision):
            return {"failure": MainAgentFailure.MODEL_DECISION_INVALID}
        if not actual_missing or set(decision.missing) != set(actual_missing):
            return {"failure": MainAgentFailure.MODEL_DECISION_INVALID}
        return {"delivery": _needs_input_delivery(actual_missing)}

    def invoke_capability_node(state: MainGraphState) -> dict[str, object]:
        decision = state.get("decision")
        if not isinstance(decision, MainInvokeCapabilityDecision):
            return {"failure": MainAgentFailure.MODEL_DECISION_INVALID}
        if actual_missing:
            # 模型提出已知能力但材料不足：转为固定追问，Tool 调用为零。
            return {"delivery": _needs_input_delivery(actual_missing)}
        if (
            decision.capability_id != capability_id
            or decision.capability_version != capability_version
            or decision.a_material_id != material_refs.text_a
            or decision.b_material_id != material_refs.text_b
        ):
            return {"failure": MainAgentFailure.CAPABILITY_UNAVAILABLE}
        outcome = run_capability(decision)
        update: dict[str, object] = {
            "tool_invoked": True,
            "tool_status": outcome.tool_status,
        }
        if outcome.failure is not None or outcome.comparison is None:
            update["failure"] = outcome.failure or MainAgentFailure.TOOL_FAILED
            return update
        update["delivery"] = MainComparisonDeliveryV1(comparison=outcome.comparison)
        return update

    def route_after_decide(state: MainGraphState) -> str:
        if state.get("failure") is not None:
            return END
        decision = state.get("decision")
        if isinstance(decision, MainAnswerDecision):
            return "finalize_answer"
        if isinstance(decision, MainNeedsInputDecision):
            return "finalize_needs_input"
        if isinstance(decision, MainInvokeCapabilityDecision):
            return "invoke_capability"
        return END

    graph = StateGraph(MainGraphState)
    graph.add_node("decide", decide_node)
    graph.add_node("finalize_answer", finalize_answer_node)
    graph.add_node("finalize_needs_input", finalize_needs_input_node)
    graph.add_node("invoke_capability", invoke_capability_node)
    graph.add_edge(START, "decide")
    graph.add_conditional_edges(
        "decide",
        route_after_decide,
        {
            "finalize_answer": "finalize_answer",
            "finalize_needs_input": "finalize_needs_input",
            "invoke_capability": "invoke_capability",
            END: END,
        },
    )
    graph.add_edge("finalize_answer", END)
    graph.add_edge("finalize_needs_input", END)
    graph.add_edge("invoke_capability", END)
    return graph.compile()


def _needs_input_delivery(missing: tuple[MaterialSide, ...]) -> MainNeedsInputDeliveryV1:
    """由实际缺失侧生成固定追问交付。"""
    ordered: list[Literal["text_a", "text_b"]] = []
    if "text_a" in missing:
        ordered.append("text_a")
    if "text_b" in missing:
        ordered.append("text_b")
    return MainNeedsInputDeliveryV1(missing=tuple(ordered), prompt=needs_input_prompt(missing))


def outcome_from_state(state: MainGraphState) -> MainAgentOutcome:
    """把图终态收敛为 typed 结果；缺交付且无失败视为交付校验失败。"""
    delivery = state.get("delivery")
    failure = state.get("failure")
    if delivery is None and failure is None:
        failure = MainAgentFailure.DELIVERY_INVALID
    raw_kind = state.get("decision_kind")
    decision_kind = cast(
        Literal["answer", "needs_input", "invoke_capability"] | None,
        raw_kind if raw_kind in {"answer", "needs_input", "invoke_capability"} else None,
    )
    return MainAgentOutcome(
        delivery=delivery,
        failure=failure,
        decision_kind=decision_kind,
        tool_invoked=bool(state.get("tool_invoked", False)),
        tool_status=state.get("tool_status"),
    )
