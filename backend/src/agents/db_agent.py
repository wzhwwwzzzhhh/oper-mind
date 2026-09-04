"""DB Agent — 数据库诊断

继承 BaseAgent，注册数据库诊断工具（EXPLAIN / SHOW INDEX / SHOW CREATE TABLE）。
"""

from typing import cast

from src.core.agent import BaseAgent
from src.core.llm import LLMClient
from src.core.tool_registry import ToolRegistry
from src.domain.services import (
    SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY,
    SERVICE_HEALTH_PRESSURE_INTENT_ID,
    BoundServiceCapabilities,
)
from src.scenarios.db_diagnosis import SYSTEM_PROMPT, TOOL_CALLING_EXAMPLE
from src.tools.db_tools import (
    CheckConnectionPoolTool,
    CheckLockStatusTool,
    ExplainTool,
    PostgresToolCapability,
    ShowCreateTableTool,
    ShowIndexTool,
)
from src.tools.service_health_tools import (
    MySqlHealthOverviewTool,
    PostgresHealthOverviewTool,
    RedisHealthOverviewTool,
)


class DBAgent(BaseAgent):
    """数据库诊断 Agent：慢 SQL 分析、索引优化"""

    def __init__(
        self,
        llm: LLMClient,
        service_id: str | None = None,
        max_steps: int = 10,
        enable_long_term_memory: bool = True,
        binding: BoundServiceCapabilities | None = None,
    ):
        tools = ToolRegistry()
        timeout_by_tool: dict[str, float] = {}
        self._postgres_health_tools: ToolRegistry | None = None
        self.health_query_is_bound = (
            binding is not None
            and SERVICE_HEALTH_PRESSURE_INTENT_ID in binding.supported_investigations
        )
        if binding is None:
            # 仅保留旧 CLI/确定性评测兼容入口；正式 v1 Run 总是注入 registry binding。
            tools.register(ExplainTool(service_id))
            tools.register(ShowIndexTool(service_id))
            tools.register(ShowCreateTableTool(service_id))
            tools.register(CheckLockStatusTool(service_id))
            tools.register(CheckConnectionPoolTool(service_id))
            system_prompt = SYSTEM_PROMPT + "\n\n" + TOOL_CALLING_EXAMPLE
        elif binding.service_id != service_id:
            raise ValueError("DBAgent service_id 与 binding 不一致")
        elif binding.kind == "postgres":
            capability = cast(PostgresToolCapability, binding.capability)
            tools.register(ExplainTool(service_id, capability))
            tools.register(ShowIndexTool(service_id, capability))
            tools.register(ShowCreateTableTool(service_id, capability))
            tools.register(CheckLockStatusTool(service_id, capability))
            self._postgres_health_tools = ToolRegistry()
            self._postgres_health_tools.register(PostgresHealthOverviewTool(binding.capability))
            timeout_by_tool["check_connection_pool"] = 15.0
            system_prompt = SYSTEM_PROMPT + "\n\n" + TOOL_CALLING_EXAMPLE
        elif binding.kind == "redis":
            tools.register(RedisHealthOverviewTool(binding.capability))
            timeout_by_tool["redis_health_overview"] = 18.0
            system_prompt = _health_prompt("Redis", "redis_health_overview")
        elif binding.kind == "mysql":
            tools.register(MySqlHealthOverviewTool(binding.capability))
            timeout_by_tool["mysql_health_overview"] = 18.0
            system_prompt = _health_prompt("MySQL", "mysql_health_overview")
        else:
            raise ValueError("DBAgent 不支持该服务类型")

        super().__init__(
            llm=llm,
            tools=tools,
            system_prompt=system_prompt,
            max_steps=max_steps,
            enable_long_term_memory=enable_long_term_memory,
            tool_timeout_by_name=timeout_by_tool,
        )

    def _tool_registry_for_query(self, user_input: str) -> ToolRegistry:
        """服务端 exact health query 只暴露健康 Tool，模型无法扩展菜单。"""
        if (
            self._postgres_health_tools is not None
            and user_input.strip() == SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY
        ):
            return self._postgres_health_tools
        return super()._tool_registry_for_query(user_input)

    def _tool_invocation_limit_for_query(self, user_input: str) -> int | None:
        """三服务健康调查最多接纳一次 Tool 调用。"""
        if self.health_query_is_bound and user_input.strip() == SERVICE_HEALTH_PRESSURE_DEFAULT_QUERY:
            return 1
        return super()._tool_invocation_limit_for_query(user_input)


def _health_prompt(kind: str, tool_name: str) -> str:
    """生成与实际无参数 Tool 菜单一致的最小提示。"""
    return (
        f"你是 {kind} 只读健康调查 Agent。只能调用已注册的 {tool_name}，"
        "不得请求 SQL、命令、连接参数、库名、凭据或目标切换。"
        f"需要事实时以空对象调用 {tool_name}，并只基于返回的结构化标量作答。"
    )
