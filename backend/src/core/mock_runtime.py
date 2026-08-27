"""确定性 mock 运行策略：角色边界、事实前置条件与质量判断。"""

from __future__ import annotations

import json
import re
from typing import Any

from data.scenarios import Scenario, get_active_scenario

ROLE_TOOL_ALLOWLISTS: dict[str, frozenset[str]] = {
    "db": frozenset(
        {"explain_sql", "show_index", "show_create_table", "check_lock_status", "check_connection_pool"}
    ),
    "server": frozenset({"check_cpu", "check_memory", "check_disk", "check_process", "check_network"}),
    "log": frozenset({"search_logs", "aggregate_errors", "query_slow_log"}),
    "knowledge": frozenset({"search_knowledge"}),
}

_ROOT_CAUSE_RE = re.compile(r"根因域[：:]\s*(db|server|log|app|config|knowledge)", re.IGNORECASE)


def infer_mock_role(tools: list[dict] | None) -> str | None:
    """仅在工具菜单属于唯一角色白名单时识别角色，否则失败关闭。"""
    if not tools:
        return None
    names: set[str] = set()
    for item in tools:
        if not isinstance(item, dict) or item.get("type") != "function":
            return None
        function = item.get("function")
        if not isinstance(function, dict):
            return None
        name = function.get("name")
        parameters = function.get("parameters")
        if not isinstance(name, str) or not name or not isinstance(parameters, dict):
            return None
        names.add(name)
    if not names:
        return None
    matches = [role for role, allowed in ROLE_TOOL_ALLOWLISTS.items() if names <= allowed]
    return matches[0] if len(matches) == 1 else None


def plan_mock_tool(role: str, query: str, tools: list[dict], scenario: Scenario | None) -> dict[str, Any] | None:
    """依据显式场景事实和当前角色菜单选择至多一个工具。"""
    available = {str(item.get("function", {}).get("name", "")) for item in tools}
    text = query.lower()
    if role == "db":
        facts = scenario.db if scenario is not None else None
        if facts is None:
            return None
        if facts.pool is not None and "check_connection_pool" in available and any(
            word in text for word in ("连接", "pool")
        ):
            return _call("check_connection_pool", {})
        if facts.lock_summary is not None and "check_lock_status" in available and any(
            word in text for word in ("锁", "阻塞", "lock")
        ):
            return _call("check_lock_status", {})
        if facts.explain is not None and "explain_sql" in available:
            return _call("explain_sql", {"sql": "SELECT 1"})
        if facts.table is not None and "show_index" in available:
            return _call("show_index", {"table": facts.table.table})
        if facts.lock_summary is not None and "check_lock_status" in available:
            return _call("check_lock_status", {})
        return None
    if role == "server" and scenario is not None:
        choices = (
            ("check_disk", ("磁盘", "disk")),
            ("check_memory", ("内存", "memory", "oom")),
            ("check_cpu", ("cpu", "负载")),
            ("check_process", ("进程", "process")),
            ("check_network", ("网络", "连接", "network")),
        )
        for name, keywords in choices:
            if name in available and any(keyword in text for keyword in keywords):
                return _call(name, {})
        preferred = {"S1": "check_cpu", "S2": "check_disk", "S3": "check_process", "S4": "check_network"}.get(
            scenario.key
        )
        return _call(preferred, {}) if preferred in available else None
    if role == "log" and scenario is not None:
        if "search_logs" in available:
            return _call("search_logs", {"keyword": "ERROR"})
        if "aggregate_errors" in available:
            return _call("aggregate_errors", {})
        if scenario.slow_queries and "query_slow_log" in available:
            return _call("query_slow_log", {})
    if role == "knowledge" and "search_knowledge" in available and any(
        word in text for word in ("知识", "文档", "sop", "手册", "howto")
    ):
        return _call("search_knowledge", {"query": query[:100]})
    return None


def mock_evidence_summary(role: str, tool_name: str, tool_output: str) -> str:
    """按角色、工具与输出类别生成可归因的模拟场景摘要。"""
    source = {"db": "数据库工具", "server": "服务器工具", "log": "日志工具", "knowledge": "知识库工具"}[role]
    prefix = f"模拟场景证据来源：{source}；"
    allowed = ROLE_TOOL_ALLOWLISTS[role]
    if tool_name not in allowed:
        return f"{prefix}工具不属于当前角色，已失败关闭；暂无可用证据，当前结论未知。"
    scenario = get_active_scenario()
    if not tool_output.strip() or any(
        marker in tool_output for marker in ("未提供", "无匹配", "未配置", "不可用", "未发现", "已拒绝")
    ):
        return f"{prefix}暂无可用证据，当前结论未知。"
    if tool_name == "search_knowledge":
        title = _safe_knowledge_title(tool_output)
        if title is None:
            return f"{prefix}工具输出未包含可验证的安全标题；暂无可用证据，当前结论未知。"
        return f"{prefix}受管知识文档《{title}》命中；该文档仅作为参考证据，不单独声明故障根因。"
    if scenario is None:
        return f"{prefix}工具返回了事实，但未配置可归因的场景，当前根因未知。"
    role_fact = _ROLE_SCENARIO_EVIDENCE.get(role, {}).get(scenario.key, {}).get(tool_name)
    markers = _TOOL_OUTPUT_MARKERS.get(tool_name, ())
    if role_fact is None or not markers or not any(marker.lower() in tool_output.lower() for marker in markers):
        return f"{prefix}工具输出与当前场景的事实类别不匹配；暂无可用证据，当前结论未知。"
    root_domain, summary = role_fact
    root = f"根因域：{root_domain}；" if root_domain is not None else ""
    return f"{prefix}{root}{summary}（工具：{tool_name}）。"


def has_attributable_mock_evidence(result: str) -> bool:
    """判断结果是否含已标注且非降级的模拟场景工具证据。"""
    return "模拟场景证据来源" in result and not any(
        marker in result for marker in ("暂无可用证据", "当前结论未知", "事实类别不匹配", "失败关闭")
    )


def assess_mock_conflict(results: dict[str, str]) -> bool:
    """只有多个有证据结论明确声明不同根因域时才判定实质冲突。"""
    domains = {
        match.group(1).lower()
        for result in results.values()
        if has_attributable_mock_evidence(result)
        for match in [_ROOT_CAUSE_RE.search(result)]
        if match is not None
    }
    return len(domains) > 1


def assess_mock_reflection(report: str) -> list[str]:
    """对无来源的确定性断言给出复审反馈；未知/无证据陈述可诚实通过。"""
    if "诊断" in report and "根因" in report and "证据来源" not in report:
        return ["诊断结论缺少证据来源，需降级为未知或补充受控工具事实"]
    if "暂无可用证据" in report or "当前结论未知" in report:
        return []
    if "诊断" in report and "证据来源" not in report:
        return ["诊断结论缺少证据来源，需降级为未知或补充受控工具事实"]
    return []


def resolve_mock_debate(results: dict[str, str]) -> str:
    """仅基于本轮可归因证据给出确定性、可识别且不伪造共识的辩论结果。"""
    domains = sorted(
        {
            match.group(1).lower()
            for result in results.values()
            if has_attributable_mock_evidence(result)
            for match in [_ROOT_CAUSE_RE.search(result)]
            if match is not None
        }
    )
    if len(domains) < 2:
        return "模拟场景辩论未执行：有来源的根因结论不足两个。"
    return (
        f"模拟场景辩论：检测到本轮工具证据的根因域冲突（{'、'.join(domains)}）；"
        "现有证据不足以安全裁决，保留冲突并建议人工复核。"
    )


def _call(name: str | None, arguments: dict[str, Any]) -> dict[str, Any] | None:
    if name is None:
        return None
    return {
        "id": "call_mock_1",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments, ensure_ascii=False)},
    }


def _safe_knowledge_title(tool_output: str) -> str | None:
    match = re.search(r"《([^》]{1,80})》", tool_output)
    if match is None:
        return None
    without_markup = re.sub(r"<[^>]*>", "", match.group(1))
    title = re.sub(r"[^\w\u4e00-\u9fff（）()《》·\- ]", "", without_markup).strip()
    return title[:60] or None


_TOOL_OUTPUT_MARKERS: dict[str, tuple[str, ...]] = {
    "explain_sql": ("访问类型", "执行计划"),
    "show_index": ("索引",),
    "show_create_table": ("CREATE TABLE", "表结构"),
    "check_lock_status": ("锁等待",),
    "check_connection_pool": ("连接池", "连接占用"),
    "check_cpu": ("CPU", "Load Average"),
    "check_memory": ("内存", "Swap"),
    "check_disk": ("磁盘",),
    "check_process": ("进程",),
    "check_network": ("连接数", "ESTABLISHED"),
    "search_logs": ("相关日志", "[ERROR]", "[WARN]"),
    "aggregate_errors": ("错误聚合", "错误日志"),
    "query_slow_log": ("慢查询",),
}


_ROLE_SCENARIO_EVIDENCE: dict[str, dict[str, dict[str, tuple[str | None, str]]]] = {
    "db": {
        "S1": {
            "explain_sql": ("db", "执行计划事实显示目标表存在全表扫描且未使用索引"),
            "show_index": ("db", "索引事实显示目标过滤列缺少适用索引"),
            "show_create_table": (None, "表结构事实已采集，单独不足以声明根因"),
            "check_lock_status": (None, "锁等待事实已采集，未显示锁竞争根因"),
            "check_connection_pool": (None, "连接池压力是影响证据，单独不足以声明数据库根因"),
        },
        "S4": {
            "check_connection_pool": ("config", "连接占用已达到场景显式提供的最大连接数"),
            "check_lock_status": (None, "锁等待事实已采集，未显示锁竞争根因"),
        },
    },
    "server": {
        "S1": {
            "check_cpu": (None, "主机 CPU 压力升高；这是影响证据，不能单独证明数据库根因"),
            "check_memory": (None, "主机内存压力事实已采集，单独不足以声明根因"),
            "check_disk": (None, "磁盘事实已采集，未显示空间耗尽根因"),
            "check_process": (None, "进程资源事实已采集，单独不足以声明根因"),
            "check_network": (None, "网络连接事实已采集，单独不足以声明根因"),
        },
        "S2": {
            "check_cpu": (None, "CPU 事实已采集，未显示 CPU 压力根因"),
            "check_memory": (None, "内存事实已采集，未显示内存压力根因"),
            "check_disk": ("server", "磁盘事实显示数据盘空间接近耗尽"),
            "check_process": (None, "进程事实已采集，未显示异常进程根因"),
            "check_network": (None, "网络连接事实已采集，未显示连接异常根因"),
        },
        "S3": {
            "check_cpu": (None, "CPU 压力是影响证据，不能单独证明应用根因"),
            "check_memory": (None, "内存压力是影响证据，不能单独证明应用根因"),
            "check_disk": (None, "磁盘事实已采集，未显示空间压力根因"),
            "check_process": ("app", "进程事实显示应用进程内存占用异常升高"),
            "check_network": (None, "网络连接事实已采集，未显示连接异常根因"),
        },
        "S4": {
            "check_cpu": (None, "CPU 事实已采集，未显示资源压力根因"),
            "check_memory": (None, "内存事实已采集，未显示资源压力根因"),
            "check_disk": (None, "磁盘事实已采集，未显示空间压力根因"),
            "check_process": (None, "进程事实已采集，未显示异常进程根因"),
            "check_network": (None, "网络连接数集中在场景给定值；本证据不能单独证明配置根因"),
        },
    },
    "log": {
        "S1": {
            "search_logs": ("db", "日志同时出现慢查询、连接池耗尽和数据库进程内存异常级联"),
            "aggregate_errors": ("db", "错误聚合显示数据库连接与查询异常集中出现"),
            "query_slow_log": ("db", "慢查询事实显示数据库访问存在明显延迟"),
        },
        "S2": {
            "search_logs": ("server", "日志明确出现数据盘空间耗尽与写入失败"),
            "aggregate_errors": ("server", "错误聚合显示空间不足与写入失败集中出现"),
        },
        "S3": {
            "search_logs": ("app", "日志明确出现频繁 Full GC 与应用堆内存溢出"),
            "aggregate_errors": ("app", "错误聚合显示应用内存异常集中出现"),
        },
        "S4": {
            "search_logs": ("config", "日志明确记录最大连接数配置及连接槽耗尽"),
            "aggregate_errors": ("config", "错误聚合显示连接槽耗尽集中出现"),
        },
    },
}
