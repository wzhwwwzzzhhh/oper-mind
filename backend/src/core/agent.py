"""Agent 基类 — 所有领域 Agent 继承此类。

ReAct 循环由 LangGraph 子图（src.core.react_graph）编排：模型节点调用
LLM，工具节点经 ToolGateway 受控执行；本类只保留记忆、思考摘要与
工具审计收集等实例状态，不再手写循环控制流。
"""

from collections.abc import Mapping

from src.core.llm import LLMClient
from src.core.react_graph import build_react_graph
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import ToolRegistry
from src.memory.long_term import LongTermMemory
from src.memory.short_term import ShortTermMemory


class BaseAgent:
    """封装领域 Agent 共用的 ReAct 循环与记忆能力。"""

    def __init__(
        self,
        llm: LLMClient,
        tools: ToolRegistry,
        system_prompt: str,
        max_steps: int = 10,
        memory_max_rounds: int = 5,
        enable_long_term_memory: bool = True,
        tool_timeout_by_name: Mapping[str, float] | None = None,
    ) -> None:
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_steps = max_steps

        # 短期记忆始终保留；评测模式关闭长期记忆以隔离用例。
        self.short_term = ShortTermMemory(system_prompt, max_rounds=memory_max_rounds)
        self.long_term = LongTermMemory() if enable_long_term_memory else None
        self.current_query = ""
        self.thinking_log: list[str] = []
        self._tool_invocations: list = []   # 本次 run 的工具调用审计记录（供上层串入 Trace）
        self._tool_timeout_by_name = dict(tool_timeout_by_name or {})

    def run(self, user_input: str) -> str:
        """驱动 LangGraph ReAct 子图并返回最终诊断结论。"""
        self.current_query = user_input
        self.thinking_log = []
        self._tool_invocations = []

        # 评测模式禁用长期记忆，保证样例之间互不影响。
        memory_context = self.long_term.format_context(user_input) if self.long_term else ""
        enriched_input = f"{user_input}\n\n{memory_context}" if memory_context else user_input

        self.short_term.add_message({"role": "user", "content": enriched_input})
        messages = self.short_term.get_messages_for_llm()
        active_tools = self._tool_registry_for_query(user_input)
        tool_schemas = active_tools.get_schemas()
        active_timeouts = {
            name: timeout
            for name, timeout in self._tool_timeout_by_name.items()
            if active_tools.get(name) is not None
        }

        gateway = (
            ToolGateway(active_tools, timeout_by_tool=active_timeouts)
            if active_timeouts
            else ToolGateway(active_tools)
        )
        invocation_limit = self._tool_invocation_limit_for_query(user_input)
        if self.max_steps <= 0:
            # 与旧循环语义一致：步数预算为空时直接视为耗尽，不做任何模型调用。
            return f"Agent 超过最大步数（{self.max_steps}步），未得出最终结论"
        graph = build_react_graph(self, tool_schemas, gateway, invocation_limit)
        try:
            # 模型↔工具每对消耗 2 个图步，放宽 recursion_limit 以支持任意 max_steps。
            final_state = graph.invoke(
                {"messages": messages, "step": 1},
                config={"recursion_limit": self.max_steps * 2 + 8},
            )
        finally:
            gateway.shutdown()

        outcome = str(final_state.get("outcome", ""))
        if outcome:
            return outcome
        return "Agent 没有生成有效响应"

    def _tool_registry_for_query(self, user_input: str) -> ToolRegistry:
        """返回本次 Run 的可信 Tool 菜单；默认保持既有完整注册表。"""
        del user_input
        return self.tools

    def _tool_invocation_limit_for_query(self, user_input: str) -> int | None:
        """返回本次查询允许的 Tool 调用总数；默认不改变历史行为。"""
        del user_input
        return None

    def _extract_tags(self, text: str) -> list[str]:
        """从诊断结果中提取用于检索的基础标签。"""
        tags = []
        if "索引" in text:
            tags.append("索引")
        if "全表扫描" in text or "ALL" in text:
            tags.append("全表扫描")
        if "慢查询" in text or "慢SQL" in text:
            tags.append("慢SQL")
        return tags

    def reset_for_evaluation(self) -> None:
        """清空单条评测结束后遗留的短期会话和思考记录。"""
        self.short_term.clear()
        self.current_query = ""
        self.thinking_log = []
    def get_conversation_history(self) -> list[dict]:
        """返回短期会话记录。"""
        return self.short_term.get_messages()

    def get_memory_stats(self) -> dict:
        """返回长期记忆记录数量；禁用时为零。"""
        return {"history_records": len(self.long_term.records) if self.long_term else 0}

    def get_thinking(self) -> list[str]:
        """返回本次诊断的关键步骤。"""
        return self.thinking_log

    def get_tool_invocations(self) -> list:
        """返回本次 run 收集到的工具调用审计记录（供编排层串入 Trace）。"""
        return self._tool_invocations

