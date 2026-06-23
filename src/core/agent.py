"""ReAct Agent 核心引擎"""
import json

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry

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
                 max_steps:int = 10):
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.max_steps = max_steps
        self.messages: list[dict] = [{"role": "system", "content": system_prompt}]

    def run(self, user_input: str) -> str:
        """
        运行Agent，处理用户输入，返回最终回答。
        """
        self.messages.append({"role": "user", "content": user_input})
        tools_schemas = self.tools.get_schemas()

        for step in range(self.max_steps):
            print(f"\n[Step {step + 1}/{self.max_steps}]")

            # 1. 调用 LLM
            response = self.llm.chat(self.messages, tools=tools_schemas)
            self.messages.append(response)

            # 检查LLM是否报错
            if "error" in response:
                return f"LLM 调用失败：{response['error']}"

            # 2. 判断LLM返回了什么
            tool_calls = response.get("tool_calls")
            content = response.get("content")

            # 如果LLM要调用工具
            if tool_calls:
                for tc in tool_calls:
                    func = tc["function"]
                    print(f" ->调用工具：{func['name']}({func['arguments']})")

                    result = self.tools.execute_tool(func["name"], func["arguments"])
                    print(f" <- 结果： {result[:100]}..." if len(result) > 100 else f" <- 结果：{result}")

                    self.messages.append({
                        "role": "tool",
                        "content": result,
                        "tool_call_id": tc["id"],
                    })
                # 继续循环，让LLM看到工具结果后决定下一步
                continue
            # 如果LLM 直接回答了（没有调工具），这就是最终答案
            if content:
                return content

            # LLM 什么都没有返回（极小概率），避免死循环
            return "Agent 没有生成有效响应"
        #超过最大步数
        return f"Agent 超过最大步数 ({self.max_steps})，未得出最终结论"

