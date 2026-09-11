"""LangGraph ReAct 子图 —— 领域 Agent 的统一执行内核。

把「模型 → 工具 → 再模型」的 ReAct 循环表达为一张最小 LangGraph 状态图：
model 节点只负责一次 LLM 调用，tools 节点经 ToolGateway 受控执行工具，
条件边负责终态收敛。安全边界（准入、校验、限时、脱敏、审计）全部由
既有 ToolGateway 承担，本模块只编排控制流，不引入新能力或旁路。

终态文案与思考摘要格式是被测试与前端锚定的行为契约，保持逐字一致。
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Literal

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from typing_extensions import TypedDict

if TYPE_CHECKING:
    from src.core.tool_gateway import ToolGateway

LOGGER = logging.getLogger(__name__)

# 行为契约文案：与既有 BaseAgent 返回值逐字一致。
LLM_UNAVAILABLE_TEXT = "LLM 调用失败：服务暂不可用"
TOOL_INVOCATION_LIMIT_TEXT = "本次只读调查已达到工具调用上限"
NO_RESPONSE_TEXT = "Agent 没有生成有效响应"


class ReactState(TypedDict, total=False):
    """ReAct 子图在节点之间传递的最小状态。"""

    messages: list[dict]   # 喂给 LLM 的消息流（由 ShortTermMemory 维护）
    step: int              # 即将执行的 model 调用序号（1-based，供思考摘要使用）
    response: dict         # 最近一次 LLM 响应（model → tools 传递）
    invocation_count: int  # 已执行的工具调用总数
    outcome: str           # 终态返回文案（设置即终止）


def build_react_graph(
    agent: Any,
    tool_schemas: list[dict],
    gateway: ToolGateway,
    invocation_limit: int | None,
) -> CompiledStateGraph:
    """为一个 Agent 实例构建本次 Run 的 ReAct 子图。

    Args:
        agent: BaseAgent 实例；节点直接操作其短期记忆、思考摘要与审计收集器。
        tool_schemas: 本次 Run 的可信工具菜单（OpenAI Function Calling 格式）。
        gateway: 由调用方构造的工具网关实例，保持既有可替换契约。
        invocation_limit: 本次查询允许的工具调用总数；None 表示不限制。

    Returns:
        编译后的子图，通过 .invoke(state) 运行；Run 结束后即废弃，无跨 Run 状态。
    """
    max_steps = agent.max_steps

    # ---- 节点：模型调用 ----
    def model_node(state: ReactState) -> dict[str, Any]:
        step = int(state.get("step", 1))
        LOGGER.debug("ReAct 第 %d/%d 步", step, max_steps)
        response = agent.llm.chat(state["messages"], tools=tool_schemas)

        if "error" in response:
            # 与旧循环一致：失败响应不进入短期记忆。
            return {"outcome": LLM_UNAVAILABLE_TEXT}

        agent.short_term.add_message(response)
        messages = agent.short_term.get_messages_for_llm()

        if response.get("tool_calls"):
            return {"response": response, "messages": messages}

        content = response.get("content")
        if content:
            if agent.long_term is not None:
                agent.long_term.add_record(
                    query=agent.current_query,
                    diagnosis=content[:200],
                    tags=agent._extract_tags(content),
                )
            agent.thinking_log.append("最终回答已生成")
            return {"outcome": content, "messages": messages}
        return {"outcome": NO_RESPONSE_TEXT, "messages": messages}

    # ---- 节点：受控工具执行 ----
    def tools_node(state: ReactState) -> dict[str, Any]:
        response = state["response"]
        step = int(state.get("step", 1))
        count = int(state.get("invocation_count", 0))

        for tc in response.get("tool_calls", []):
            # 与旧循环一致：逐个调用前检查总数上限，超限立即终止本轮调查。
            if invocation_limit is not None and count >= invocation_limit:
                return {"outcome": TOOL_INVOCATION_LIMIT_TEXT}
            func = tc["function"]
            # 只记工具名：arguments 可能含 SQL 或连接参数，不进日志。
            LOGGER.debug("第 %d 步调用工具 %s", step, func["name"])

            gw_result = gateway.invoke(func["name"], func["arguments"])
            count += 1
            agent._tool_invocations.append(gw_result.record)
            agent.thinking_log.append(
                f"Step {step}: 工具 {func['name']} 状态={gw_result.record.status}"
            )

            agent.short_term.add_message(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": gw_result.output,
                }
            )
        messages = agent.short_term.get_messages_for_llm()

        if step >= max_steps:
            # 与旧循环一致：最后一次模型调用返回工具时，处理完本轮工具后步数耗尽。
            return {
                "outcome": f"Agent 超过最大步数（{max_steps}步），未得出最终结论",
                "messages": messages,
            }
        return {"step": step + 1, "invocation_count": count, "messages": messages}

    # ---- 条件边 ----
    def _route_after_model(state: ReactState) -> Literal["tools", "__end__"]:
        return END if state.get("outcome") else "tools"  # type: ignore[return-value]

    def _route_after_tools(state: ReactState) -> Literal["model", "__end__"]:
        return END if state.get("outcome") else "model"  # type: ignore[return-value]

    # ---- 组装图 ----
    graph = StateGraph(ReactState)
    graph.add_node("model", model_node)
    graph.add_node("tools", tools_node)
    graph.add_edge(START, "model")
    graph.add_conditional_edges("model", _route_after_model, {"tools": "tools", END: END})
    graph.add_conditional_edges("tools", _route_after_tools, {"model": "model", END: END})
    return graph.compile()
