"""日志分析工具集 — 检索错误日志、聚合异常模式"""

import os
import re
from datetime import datetime, timedelta
from collections import Counter

from src.core.tool_registry import Tool


# 模拟日志数据（Mock）
MOCK_LOGS = [
    "[ERROR] 2026-07-05 10:23:45 - Connection pool exhausted - unable to get connection from MySQL",
    "[ERROR] 2026-07-05 10:23:46 - Query timeout: SELECT * FROM orders WHERE status = 'PENDING'",
    "[ERROR] 2026-07-05 10:23:47 - Thread pool exhausted: 200 threads active",
    "[WARN] 2026-07-05 10:23:48 - Slow query (5.2s): SELECT * FROM orders ORDER BY create_time DESC",
    "[ERROR] 2026-07-05 10:24:00 - OOM Killer invoked: process mysqld (PID 1234) killed",
    "[ERROR] 2026-07-05 10:24:05 - Connection refused: too many connections",
    "[INFO] 2026-07-05 10:24:10 - MySQL restarted after crash",
    "[WARN] 2026-07-05 10:25:00 - CPU usage threshold exceeded: 95%",
    "[ERROR] 2026-07-05 10:25:30 - Disk write timeout: /data/mysql",
    "[ERROR] 2026-07-05 10:26:00 - Application exception: java.lang.OutOfMemoryError",
]


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
        # 简单 Mock 实现
        results = [log for log in MOCK_LOGS if keyword.lower() in log.lower()]
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
        errors = [log for log in MOCK_LOGS if "[ERROR]" in log]
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
        slow_queries = [
            {"sql": "SELECT * FROM orders WHERE status = 'PENDING'", "time": 5.2, "rows": 50000},
            {"sql": "SELECT * FROM orders o JOIN order_items i ON o.id = i.order_id", "time": 3.8, "rows": 200000},
            {"sql": "SELECT * FROM orders ORDER BY create_time DESC", "time": 4.1, "rows": 50000},
        ]
        result = f"慢查询日志 (Top {limit}):\n"
        for q in slow_queries[:limit]:
            result += f"  {q['time']}s | 扫描 {q['rows']} 行 | {q['sql'][:60]}\n"
        return result
