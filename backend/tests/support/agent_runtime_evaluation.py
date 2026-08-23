"""pytest 内部使用的 Agent 运行真实性负向门禁。"""

from __future__ import annotations

import re
from typing import Any, Literal, TypedDict

from src.core.mock_runtime import ROLE_TOOL_ALLOWLISTS

_SERVER_FACT_MARKERS: dict[str, tuple[str, ...]] = {
    "cpu": ("cpu", "负载", "load average"),
    "memory": ("内存", "memory", "swap", "oom"),
    "disk": ("磁盘", "空间", "disk", "挂载"),
    "process": ("进程", "process", "pid"),
    "network": ("网络", "连接数", "network", "established", "time_wait"),
}
_SERVER_TOOL_CATEGORY = {
    "check_cpu": "cpu",
    "check_memory": "memory",
    "check_disk": "disk",
    "check_process": "process",
    "check_network": "network",
}


class RuntimeSnapshot(TypedDict):
    """评测器消费的最小确定性快照。"""

    mode: Literal["mock", "real"]
    role_tools: dict[str, list[str]]
    evidence: list[dict[str, Any]]
    report: str
    statuses: list[dict[str, str]]


def evaluate_runtime_snapshot(snapshot: RuntimeSnapshot) -> list[str]:
    """返回违规类别；空列表表示通过全部真实性门禁。"""
    violations: set[str] = set()
    for role, tools in snapshot["role_tools"].items():
        allowed = ROLE_TOOL_ALLOWLISTS.get(role)
        if allowed is None or any(tool not in allowed for tool in tools):
            violations.add("role_tool_boundary")
    for item in snapshot["evidence"]:
        claim = item.get("claim")
        source = item.get("source")
        source_role = item.get("source_role")
        source_tool = item.get("source_tool")
        source_output = str(item.get("source_output", ""))
        allowed = ROLE_TOOL_ALLOWLISTS.get(str(source_role))
        invalid_tool_source = bool(source_tool) and (allowed is None or source_tool not in allowed)
        fact_mismatch = _claim_mismatches_server_fact(str(source_tool), str(claim), source_output)
        if claim and (
            not source
            or not source_role
            or not source_tool
            or invalid_tool_source
            or fact_mismatch
            or item.get("fabricated") is True
        ):
            violations.add("evidence_truthfulness")
    report = snapshot["report"]
    unsafe_patterns = (
        r"(?i)\b(select|alter|drop|insert|update|delete)\b.+\b(from|table|into|set)\b",
        r"[A-Za-z]:\\",
        r"(?<![\w/])/(?:[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*)(?=$|[^A-Za-z0-9._/-])",
        r"(?<![\w/])/(?![\w/])",
        r"(?i)\b(?:postgres(?:ql)?|mysql|redis)://",
        r"(?i)traceback|most recent call",
        r"(?i)['\"]?(?:password|token|secret|api[_-]?key)['\"]?\s*[=:]",
        r"(?i)['\"]?(?:工具实参|arguments|tool[_-]?(?:args|input)|kwargs)['\"]?\s*[=:]",
    )
    if any(re.search(pattern, report) for pattern in unsafe_patterns):
        violations.add("public_safety")
    for status in snapshot["statuses"]:
        actual = status.get("actual")
        displayed = status.get("displayed")
        if actual in {"unavailable", "skipped", "failed", "error", "timeout", "rejected"} and displayed == "ok":
            violations.add("false_success")
    if snapshot["mode"] == "mock" and snapshot["evidence"] and "模拟场景" not in report:
        violations.add("unmarked_mock")
    return sorted(violations)


def _claim_mismatches_server_fact(source_tool: str, claim: str, source_output: str) -> bool:
    """自动识别服务器指标工具与结论类别错配，不依赖调用方自报 fabricated。"""
    expected = _SERVER_TOOL_CATEGORY.get(source_tool)
    if expected is None:
        return False
    lowered_claim = claim.lower()
    lowered_output = source_output.lower()
    mentioned = {
        category
        for category, markers in _SERVER_FACT_MARKERS.items()
        if any(marker in lowered_claim for marker in markers)
    }
    output_matches = any(marker in lowered_output for marker in _SERVER_FACT_MARKERS[expected])
    return not output_matches or bool(mentioned - {expected})
