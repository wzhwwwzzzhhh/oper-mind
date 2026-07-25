"""日志分析工具集 — 检索错误日志、聚合异常模式

日志数据来自 data/scenarios.py 的当前激活场景（mock 模式），不再内联硬编码。
"""

import re
from collections import Counter

from data.scenarios import active_or_default
from src.core.tool_registry import Tool


class SearchLogsTool(Tool):
    """检索错误日志"""

    def __init__(self):
        super().__init__(
            name="search_logs",
            description="按关键字和时间范围检索日志",
            parameters={
                "type": "object",
                "properties": {
                    "keyword": {"type": "string", "description": "检索关键字，如 error、timeout、OOM"},
                    "time_range": {"type": "string", "description": "时间范围，如 1h、30m、24h"},
                },
                "required": ["keyword"],
            },
        )

    def execute(self, keyword: str, time_range: str = "1h") -> str:
        """检索匹配的日志"""
        logs = active_or_default().logs
        results = [log for log in logs if keyword.lower() in log.lower()]
        if not results:
            return f"未找到包含 '{keyword}' 的日志"
        return f"找到 {len(results)} 条相关日志:\n" + "\n".join(results[:10])


class AggregateErrorsTool(Tool):
    """聚合错误类型和频率"""

    def __init__(self):
        super().__init__(
            name="aggregate_errors",
            description="聚合错误类型和频率，识别异常模式",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str:
        """聚合错误日志"""
        errors = [log for log in active_or_default().logs if "[ERROR]" in log]
        error_types = Counter()
        for log in errors:
            # 提取错误类型
            match = re.search(r'-\s+(.+?)(?:[:]|\s+\d)', log)
            if match:
                error_types[match.group(1)] += 1

        result = "错误聚合统计:\n"
        for err_type, count in error_types.most_common():
            result += f"  {err_type}: {count} 次\n"
        result += f"\n共 {len(errors)} 条错误日志"
        return result


class QuerySlowLogTool(Tool):
    """慢查询日志分析"""

    def __init__(self):
        super().__init__(
            name="query_slow_log",
            description="分析慢查询日志，返回执行时间最长的 SQL",
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "返回条数"},
                },
                "required": [],
            },
        )

    def execute(self, limit: int = 5) -> str:
        """返回慢查询日志"""
        slow_queries = active_or_default().slow_queries
        if not slow_queries:
            return "未发现慢查询（当前场景 DB 执行正常）"
        result = f"慢查询日志 (Top {limit}):\n"
        for q in slow_queries[:limit]:
            result += f"  {q['time']}s | 扫描 {q['rows']} 行 | {q['sql'][:60]}\n"
        return result
