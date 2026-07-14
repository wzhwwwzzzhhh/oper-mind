"""Agent 基类 — 所有领域 Agent 继承此类"""

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.memory.short_term import ShortTermMemory
from src.memory.long_term import LongTermMemory


class BaseAgent:
    """
    所有领域 Agent 的基类。

    封装了 ReAct 循环核心逻辑，子类只需：
    1. 在 __init__ 中注册自己的工具
    2. 提供 system_prompt
    3. 按需重写 run() 方法
    """

    def __init__(self,
                 llm: LLMClient,
                 tools: ToolRegistry,
                 system_prompt: str,
                 max_steps: int = 10,
                 memory_max_rounds: int = 5):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_steps = max_steps

        # 记忆系统
        self.short_term = ShortTermMemory(system_prompt, max_rounds=memory_max_rounds)
        self.long_term = LongTermMemory()
        self.current_query = ""
        self.thinking_log: list[str] = []

    def run(self, user_input: str) -> str:
        """
        ReAct 循环：思考 → 行动 → 观察 → 重复 → 最终回答。
        子类可以重写此方法实现自定义逻辑。
        """
        self.current_query = user_input
        self.thinking_log = []

        # 注入长期记忆
        memory_context = self.long_term.format_context(user_input)
        enriched_input = f"{user_input}\n\n{memory_context}" if memory_context else user_input

        self.short_term.add_message({"role": "user", "content": enriched_input})
        messages = self.short_term.get_messages_for_llm()
        tool_schemas = self.tools.get_schemas()

        for step in range(self.max_steps):
            print(f"\n[Step {step + 1}/{self.max_steps}]")
            response = self.llm.chat(messages, tools=tool_schemas)

            if "error" in response:
                return f"LLM 调用失败：{response['error']}"

            self.short_term.add_message(response)
            messages = self.short_term.get_messages_for_llm()

            tool_calls = response.get("tool_calls")
            content = response.get("content")

            if tool_calls:
                for tc in tool_calls:
                    func = tc["function"]
                    step_log = f"Step {step + 1}: 调用 {func['name']}({func['arguments']})"
                    print(f"→ {step_log}")

                    result = self.tools.execute_tool(func["name"], func["arguments"])
                    short_result = result[:100] + "..." if len(result) > 100 else result
                    print(f"← {short_result}")
                    self.thinking_log.append(f"{step_log} → {short_result}")

                    self.short_term.add_message({
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    })
                    messages = self.short_term.get_messages_for_llm()
                continue

            if content:
                self.long_term.add_record(
                    query=self.current_query,
                    diagnosis=content[:200],
                    tags=self._extract_tags(content),
                )
                self.thinking_log.append(f"最终回答: {content[:100]}...")
                return content

            return "Agent 没有生成有效响应"

        return f"Agent 超过最大步数（{self.max_steps}步），未得出最终结论"

    def _extract_tags(self, text: str) -> list[str]:
        """从诊断结果中提取标签，子类可重写"""
        tags = []
        if "索引" in text:
            tags.append("索引")
        if "全表扫描" in text or "ALL" in text:
            tags.append("全表扫描")
        if "慢查询" in text or "慢SQL" in text:
            tags.append("慢SQL")
        return tags

    def get_conversation_history(self) -> list[dict]:
        return self.short_term.get_messages()

    def get_memory_stats(self) -> dict:
        return {"history_records": len(self.long_term.records)}

    def get_thinking(self) -> list[str]:
        return self.thinking_log
