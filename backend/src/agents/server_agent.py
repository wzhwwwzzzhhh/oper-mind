"""Server Agent — 服务器诊断

通过 psutil 采集 CPU、内存、磁盘、进程等系统指标，分析服务器健康状态。
"""

from src.core.agent import BaseAgent
from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.tools.server_tools import (
    CheckCpuTool,
    CheckDiskTool,
    CheckMemoryTool,
    CheckNetworkTool,
    CheckProcessTool,
)

SERVER_SYSTEM_PROMPT = """你是服务器运维专家，擅长分析服务器性能问题。

## 诊断流程
当你收到一个服务器相关问题，你应该：
1. 检查 CPU 使用率和负载情况
2. 检查内存使用情况
3. 检查磁盘空间和 IO
4. 检查异常进程
5. 检查网络连接

## 工具使用规则
- 每次只调用一个工具，根据结果决定下一步
- 拿到所有需要的信息后，汇总分析给出最终答案

## 回答要求
- 用中文回答
- 诊断结论要具体，包括：问题根因、优化建议
- 如果系统健康，也说明为什么好
"""


class ServerAgent(BaseAgent):
    """服务器诊断 Agent：CPU/内存/磁盘/进程/网络分析"""

    def __init__(self, llm: LLMClient, max_steps: int = 8, enable_long_term_memory: bool = True):
        tools = ToolRegistry()
        tools.register(CheckCpuTool())
        tools.register(CheckMemoryTool())
        tools.register(CheckDiskTool())
        tools.register(CheckProcessTool())
        tools.register(CheckNetworkTool())

        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=SERVER_SYSTEM_PROMPT,
            max_steps=max_steps,
        enable_long_term_memory=enable_long_term_memory,
        )
