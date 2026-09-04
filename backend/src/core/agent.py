"""Agent 基类 — 所有领域 Agent 继承此类"""

import logging
from collections.abc import Mapping

from src.core.llm import LLMClient
from src.core.tool_gateway import ToolGateway
from src.core.tool_registry import ToolRegistry
from src.memory.long_term import LongTermMemory
from src.memory.short_term import ShortTermMemory

LOGGER = logging.getLogger(__name__)


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
        """执行 ReAct 循环并返回最终诊断结论。"""
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
        invocation_count = 0
        try:
            for step in range(self.max_steps):
                LOGGER.debug("ReAct 第 %d/%d 步", step + 1, self.max_steps)
                response = self.llm.chat(messages, tools=tool_schemas)

                if "error" in response:
                    return "LLM 调用失败：服务暂不可用"

                self.short_term.add_message(response)
                messages = self.short_term.get_messages_for_llm()

                tool_calls = response.get("tool_calls")
                content = response.get("content")

                if tool_calls:
                    for tc in tool_calls:
                        if invocation_limit is not None and invocation_count >= invocation_limit:
                            return "本次只读调查已达到工具调用上限"
                        func = tc["function"]
                        # 只记工具名：arguments 可能含 SQL 或连接参数，不进日志。
                        LOGGER.debug("第 %d 步调用工具 %s", step + 1, func["name"])

                        gw_result = gateway.invoke(func["name"], func["arguments"])
                        invocation_count += 1
                        result = gw_result.output
                        self._tool_invocations.append(gw_result.record)
                        self.thinking_log.append(
                            f"Step {step + 1}: 工具 {func['name']} 状态={gw_result.record.status}"
                        )

                        self.short_term.add_message(
                            {
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "content": result,
                            }
                        )
                        messages = self.short_term.get_messages_for_llm()
                    continue

                if content:
                    if self.long_term:
                        self.long_term.add_record(
                            query=self.current_query,
                            diagnosis=content[:200],
                            tags=self._extract_tags(content),
                        )
                    self.thinking_log.append("最终回答已生成")
                    return content

                return "Agent 没有生成有效响应"

            return f"Agent 超过最大步数（{self.max_steps}步），未得出最终结论"
        finally:
            gateway.shutdown()

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

