""" CLI 入口"""
from datetime import datetime

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.core.agent import Agent
from src.tools.db_tools import ExplainTool, ShowCreateTableTool, ShowIndexTool
from src.scenarios.db_diagnosis import SYSTEM_PROMPT, TOOL_CALLING_EXAMPLE


def build_agent(api_key: str = "mock") -> Agent:
    """构造 Agent 实例，所有依赖都注入进来"""
    llm = LLMClient(api_key="ollama", base_url="http://localhost:11434/v1")

    tools = ToolRegistry()
    tools.register(ExplainTool())
    tools.register(ShowCreateTableTool())
    tools.register(ShowIndexTool())

    system_prompt = SYSTEM_PROMPT
    system_prompt += TOOL_CALLING_EXAMPLE

    return Agent(llm=llm, tools=tools, system_prompt=system_prompt)

def main():
    agent = build_agent()

    print("=" * 50)
    print("数据库诊断 Agent 已启动")
    print("输入 SQL 语句进行分析，输入 'exit' 退出")
    print("测试用例：")
    print("  1. SELECT * FROM orders WHERE status = 'PENDING'")
    print("  2. SELECT * FROM orders ORDER BY create_time DESC")
    print("=" * 50)

    while(True):
        user_input = input("\n> ").strip()
        if user_input.lower() in ("exit", "quit", "q"):
            break
        result = agent.run(user_input)
        print(f"\n{result}")

if __name__ == "__main__":
    main()