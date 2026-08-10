"""日志分析工具集 — 检索错误日志、聚合异常模式。

mock 模式读取 `data/scenarios.py` 当前激活场景（S1–S4 确定性不变）；
真实模式经受控只读 `LogSourceConnector` 读取绑定服务实例的受管日志目录，
未配置/不可用诚实降级，不伪造日志内容。
"""

from __future__ import annotations

import re
from collections import Counter

from data.scenarios import active_or_default, get_active_scenario

from src.config import load_service_log_dir
from src.core.tool_registry import Tool
from src.infrastructure.logs.log_source import LogSourceConnector

_MOCK_RESULT_LIMIT = 10
_SLOW_LIMIT_MAX = 10
_SNIPPET_LEN = 120


def _parse_time_range(time_range: str | None) -> float | None:
    """把时间范围串解析为小时数；空/非法返回 None（不限时）。"""
    if not time_range:
        return None
    match = re.match(r"^\s*(\d+(?:\.\d+)?)\s*(h|hour|hours|m|min|minute|minutes)?\s*$", time_range)
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2)
    if unit and unit.startswith("m"):
        value /= 60
    return value


def _resolve_connector(service_id: str | None) -> tuple[LogSourceConnector | None, str | None]:
    """按绑定服务解析日志源 Connector。

    返回 (connector, 降级文案)：service_id 未绑定返回 (None, 文案)；
    日志源未配置由 Connector 内部 `not_configured` 诚实降级。
    """
    if service_id is None:
        return None, "日志源未选择目标服务"
    log_dir = load_service_log_dir(service_id)
    return LogSourceConnector(log_dir=log_dir, instance_id=service_id), None


class SearchLogsTool(Tool):
    """检索错误日志（mock 或真实日志源）。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        self._last_summary = "日志分析未执行"
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

    def audit_summary(self) -> str:
        """返回最近一次检索的脱敏审计摘要（供 Trace 展示）。"""
        return self._last_summary

    def execute(self, keyword: str, time_range: str = "1h") -> str:
        """按当前模式返回 mock 或真实日志源检索结果。"""
        if get_active_scenario() is not None:
            return self._mock_search(keyword)

        connector, degraded = _resolve_connector(self._service_id)
        if connector is None:
            self._last_summary = degraded or "日志源不可用"
            return degraded or "日志源不可用"
        result = connector.search(keyword, _parse_time_range(time_range))
        self._last_summary = result.message
        if result.status != "ok":
            return result.message
        if result.total_hits == 0:
            return f"未找到包含 '{keyword}' 的日志（真实日志源）"
        lines = [
            f"找到 {result.total_hits} 条相关日志（真实日志源，展示前 {len(result.entries)} 条）:"
        ]
        for entry in result.entries:
            lines.append(f"[{entry.level}] {entry.message[:_SNIPPET_LEN]}")
        return "\n".join(lines)

    def _mock_search(self, keyword: str) -> str:
        """保留既有 mock 检索行为与文案。"""
        logs = active_or_default().logs
        results = [log for log in logs if keyword.lower() in log.lower()]
        self._last_summary = f"mock 场景检索命中 {len(results)} 条"
        if not results:
            return f"未找到包含 '{keyword}' 的日志"
        return f"找到 {len(results)} 条相关日志:\n" + "\n".join(results[:_MOCK_RESULT_LIMIT])


class AggregateErrorsTool(Tool):
    """聚合错误类型和频率（mock 或真实日志源）。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        self._last_summary = "日志分析未执行"
        super().__init__(
            name="aggregate_errors",
            description="聚合错误类型和频率，识别异常模式",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def audit_summary(self) -> str:
        """返回最近一次聚合的脱敏审计摘要（供 Trace 展示）。"""
        return self._last_summary

    def execute(self) -> str:
        """按当前模式返回 mock 或真实日志源错误聚合。"""
        if get_active_scenario() is not None:
            return self._mock_aggregate()

        connector, degraded = _resolve_connector(self._service_id)
        if connector is None:
            self._last_summary = degraded or "日志源不可用"
            return degraded or "日志源不可用"
        result = connector.aggregate_errors()
        self._last_summary = result.message
        if result.status != "ok":
            return result.message
        if result.total_errors == 0:
            return "未发现错误日志（真实日志源）"
        lines = ["错误聚合统计（真实日志源）:"]
        for err_type, count in result.error_counts.items():
            lines.append(f"  {err_type}: {count} 次")
        lines.append(f"\n共 {result.total_errors} 条错误日志")
        return "\n".join(lines)

    def _mock_aggregate(self) -> str:
        """保留既有 mock 聚合行为与文案。"""
        errors = [log for log in active_or_default().logs if "[ERROR]" in log]
        self._last_summary = f"mock 场景聚合 {len(errors)} 条错误"
        error_types: Counter[str] = Counter()
        for log in errors:
            # 提取错误类型
            match = re.search(r"-\s+(.+?)(?:[:]|\s+\d)", log)
            if match:
                error_types[match.group(1)] += 1

        result = "错误聚合统计:\n"
        for err_type, count in error_types.most_common():
            result += f"  {err_type}: {count} 次\n"
        result += f"\n共 {len(errors)} 条错误日志"
        return result


class QuerySlowLogTool(Tool):
    """慢查询与超时模式分析（mock 或真实日志源）。"""

    def __init__(self, service_id: str | None = None) -> None:
        self._service_id = service_id
        self._last_summary = "日志分析未执行"
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

    def audit_summary(self) -> str:
        """返回最近一次慢查询分析的脱敏审计摘要（供 Trace 展示）。"""
        return self._last_summary

    def execute(self, limit: int = 5) -> str:
        """按当前模式返回 mock 或真实日志源慢查询分析。"""
        if get_active_scenario() is not None:
            return self._mock_slow_query(limit)

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 5
        limit = max(1, min(limit, _SLOW_LIMIT_MAX))

        connector, degraded = _resolve_connector(self._service_id)
        if connector is None:
            self._last_summary = degraded or "日志源不可用"
            return degraded or "日志源不可用"
        report = connector.slow_query_patterns(limit=limit, threshold_seconds=1.0)
        self._last_summary = report.message
        if report.status != "ok":
            return report.message

        lines: list[str] = []
        if report.slow_queries:
            lines.append(f"慢查询日志（真实日志源，Top {len(report.slow_queries)}）:")
            for entry in report.slow_queries:
                lines.append(f"  {entry.time_seconds}s | {entry.snippet}")
        else:
            lines.append("未发现慢查询（真实日志源）")
        if report.timeout_count:
            lines.append(f"\n超时关联：检测到 {report.timeout_count} 次超时/连接超时:")
            for snippet in report.timeout_snippets:
                lines.append(f"  · {snippet}")
        return "\n".join(lines)

    def _mock_slow_query(self, limit: int) -> str:
        """保留既有 mock 慢查询行为与文案。"""
        slow_queries = active_or_default().slow_queries
        self._last_summary = f"mock 场景慢查询 {len(slow_queries)} 条"
        if not slow_queries:
            return "未发现慢查询（当前场景 DB 执行正常）"
        result = f"慢查询日志 (Top {limit}):\n"
        for q in slow_queries[:limit]:
            result += f"  {q['time']}s | 扫描 {q['rows']} 行 | {q['sql'][:60]}\n"
        return result
