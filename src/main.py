""" CLI 入口"""
from datetime import datetime

from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry, Tool
from src.core.agent import Agent


class GetCurrentTimeTool(Tool):
    """获取当前时间的工具"""

    def __init__(self):
        super().__init__(
            name="get_current_time",
            description="获取当前时间和日期",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str:
        return f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"


def build_agent(api_key: str = "mock") -> Agent:
    """构造 Agent 实例，所有依赖都注入进来"""
    llm = LLMClient(api_key="ollama", base_url="http://localhost:11434/v1")

    tools = ToolRegistry()
    tools.register(GetCurrentTimeTool())

    system_prompt = """你是数据库诊断助手，帮助用户分析SQL性能和数据库问题。
    请用专业的知识回答用户问题。
    如果需要查询信息，可以使用提供的工具。"""

    return Agent(llm=llm, tools=tools, system_prompt=system_prompt)

def main():
    agent = build_agent()

    print("=" *50)
    print("数据库诊断 Agent 已启动（输入 'exit' 退出）")
    print("=" *50)

    while(True):
        user_input = input("\n> ").strip()
        if user_input.lower() in ("exit", "quit", "q"):
            break
        result = agent.run(user_input)
        print(f"\n{result}")

if __name__ == "__main__":
    main()