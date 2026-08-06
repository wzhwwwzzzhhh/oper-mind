"""Log Agent — 日志分析

检索错误日志、聚合异常模式、关联慢查询日志。
"""

from src.core.agent import BaseAgent
from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.tools.log_tools import SearchLogsTool, AggregateErrorsTool, QuerySlowLogTool


LOG_SYSTEM_PROMPT = """你是日志分析专家，擅长从日志中定位问题根因。

## 诊断流程
当你需要分析日志时，你应该：
1. 根据问题检索相关日志
2. 聚合错误类型和频率
3. 分析慢查询日志（如需要）
4. 综合判断根因

## 工具使用规则
- 每次只调用一个工具，根据结果决定下一步
- 拿到所有需要的信息后，汇总分析给出最终答案

## 回答要求
- 用中文回答
- 指出日志中的异常模式
- 关联到可能的根因
"""


class LogAgent(BaseAgent):
    """日志分析 Agent：错误日志检索、异常模式识别、慢查询分析"""

    def __init__(
        self,
        llm: LLMClient,
        service_id: str | None = None,
        max_steps: int = 8,
        enable_long_term_memory: bool = True,
    ):
        tools = ToolRegistry()
        tools.register(SearchLogsTool(service_id))
        tools.register(AggregateErrorsTool(service_id))
        tools.register(QuerySlowLogTool(service_id))

        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=LOG_SYSTEM_PROMPT,
            max_steps=max_steps,
        enable_long_term_memory=enable_long_term_memory,
        )
