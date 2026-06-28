""" CLI 入口"""
from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.core.agent import Agent
from src.tools.db_tools import ExplainTool, ShowCreateTableTool, ShowIndexTool
from src.scenarios.db_diagnosis import SYSTEM_PROMPT, TOOL_CALLING_EXAMPLE
from src.config import load_config


def build_agent() -> Agent:
    """构造 Agent 实例，所有依赖都注入进来"""
    config = load_config()
    llm_config = config["llm"]

    llm = LLMClient(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model=llm_config.get("model", "deepseek-chat"),
    )

    tools = ToolRegistry()
    tools.register(ExplainTool())
    tools.register(ShowCreateTableTool())
    tools.register(ShowIndexTool())

    system_prompt = SYSTEM_PROMPT
    system_prompt += TOOL_CALLING_EXAMPLE

    return Agent(llm=llm, tools=tools, system_prompt=system_prompt)

def test_fallback():
    """测试降级模式：LLM 不可用时使用规则引擎"""
    from src.core.fallback import RuleEngine
    from data.mock_db import explain_sql

    test_sqls = [
        "SELECT * FROM orders WHERE status = 'PENDING'",
        "SELECT * FROM orders ORDER BY create_time DESC",
        "SELECT * FROM orders o JOIN order_items i ON o.id = i.order_id WHERE i.product_id = 123",
        "SELECT YEAR(create_time) FROM orders WHERE id = 1",
        "SELECT * FROM products WHERE id = 1",
    ]

    print("=" * 60)
    print("降级模式测试：LLM 不可用，使用规则引擎")
    print("=" * 60)

    engine = RuleEngine()
    for sql in test_sqls:
        print(f"\n---")
        print(f"SQL: {sql}")
        plan = explain_sql(sql)
        print(f"EXPLAIN: type={plan['type']}, rows={plan['rows']}")
        print(f"\n{engine.diagnose(sql)}")

    print("\n" + "=" * 60)
    print("降级模式测试完成")

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
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--fallback":
        from src.core.fallback import RuleEngine

        engine = RuleEngine()
        sql = input("请输入SQL: ")
        print(engine.diagnose(sql))
    else:
        main()