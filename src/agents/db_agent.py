"""DB Agent — 数据库诊断

继承 BaseAgent，注册数据库诊断工具（EXPLAIN / SHOW INDEX / SHOW CREATE TABLE）。
"""

from src.core.agent import BaseAgent
from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.tools.db_tools import ExplainTool, ShowIndexTool, ShowCreateTableTool
from src.scenarios.db_diagnosis import SYSTEM_PROMPT, TOOL_CALLING_EXAMPLE


class DBAgent(BaseAgent):
    """数据库诊断 Agent：慢 SQL 分析、索引优化"""

    def __init__(self, llm: LLMClient, max_steps: int = 10):
        tools = ToolRegistry()
        tools.register(ExplainTool())
        tools.register(ShowIndexTool())
        tools.register(ShowCreateTableTool())

        system_prompt = SYSTEM_PROMPT + "\n\n" + TOOL_CALLING_EXAMPLE

        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            max_steps=max_steps,
        )
