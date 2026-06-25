"""ReAct Agent 核心引擎"""
import json

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.memory.long_term import LongTermMemory
from src.memory.short_term import ShortTermMemory

class Agent:
    """
    ReActAgent核心引擎。
    核心循环：
    1.把消息发给 LLM
    2．如果LLM 返回最终答案→结束
    3．如果LLM 要调工具→执行→把结果加回消息→回到第1步
    """

    def __init__(self,
                 llm: LLMClient,
                 tools: ToolRegistry,
                 system_prompt:str,
                 max_steps:int = 10,
                 memory_max_rounds: int = 5):
        self.llm = llm
        self.tools = tools
        self.max_steps = max_steps

        # 记忆系统
        self.short_term = ShortTermMemory(system_prompt, max_rounds=memory_max_rounds)
        self.long_term = LongTermMemory()
        self.current_query = ""


    def run(self, user_input: str) -> str:
        """
        运行Agent，处理用户输入，返回最终回答。
        """
        self.current_query = user_input

        # 注入长期记忆相关的上下文
        memory_context = self.long_term.format_context(user_input)
        if memory_context:
            #  把历史记录作为一条 system 消息注入
            enriched_input = f"{user_input}\n\n{memory_context}"
        else:
            enriched_input = user_input

        # 添加用户消息到短期记忆
        self.short_term.add_message({"role": "user", "content": enriched_input})
        messages = self.short_term.get_messages_for_llm()

        tool_schemas = self.tools.get_schemas()

        for step in range(self.max_steps):
            print(f"\n[step {step + 1}/{self.max_steps}]")

            response = self.llm.chat(messages, tools = tool_schemas)

            if "error" in response:
                return f"LLM调用失败：{response['error']}"

            # 把LLM的响应加到短期记忆
            self.short_term.add_message(response)

            # 同时更新 messages 引用（因为短期记忆的内容可能变了）
            messages = self.short_term.get_messages_for_llm()

            tool_calls = response.get("tool_calls")
            content = response.get("content")

            if tool_calls:
                for tc in tool_calls:
                    func = tc["function"]
                    print(f"→调用工具：{func['name']}({func['arguments']}）")

                    result = self.tools.execute_tool(func["name"], func["arguments"])
                    print(f"←结果：{result[:100]}..." if len(result) > 100 else f"←结果：{result}")

                    tool_message = {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": result,
                    }
                    self.short_term.add_message(tool_message)
                    messages = self.short_term.get_messages_for_llm()

                continue
            if content:
                # 保存到长期记忆
                self.long_term.add_record(
                    query=self.current_query,
                    diagnosis=content[:200],  # 只保存前200字
                    tags=self._extract_tags(content),
                )
                return content
            return "Agent 没有生产有效响应"

        return f"Agent 超过最大步数（{self.max_steps}步），未得出最终结论"

    def _extract_tags(self, text: str) -> list[str]:
        """从诊断结果中提取标签"""
        tags = []
        if "索引" in text:
            tags.append("索引")
        if "全表扫描" in text or "ALL" in text:
            tags.append("全表扫描")
        if "慢查询" in text or "慢SQL" in text:
            tags.append("慢SQL")
        if "JOIN" in text.upper() or "join" in text:
            tags.append("JOIN优化")
        return tags

    def get_conversation_history(self) -> list[dict]:
        """获取对话历史"""
        return self.short_term.get_messages()

    def get_memory_stats(self) -> dict:
        """获取记忆统计信息"""
        return {
            "history_records" : len(self.long_term.records)
        }


