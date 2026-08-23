"""公开诊断结果的确定性安全投影。"""

from __future__ import annotations

import re

from src.core.tool_gateway import desensitize

_SQL_LINE = re.compile(r"(?i)(?:^|[^A-Za-z0-9_])(select|insert|update|delete|alter|drop|create|explain)\s+")
_WINDOWS_PATH = re.compile(r"[A-Za-z]:\\[^\s]+")
_UNIX_PATH = re.compile(r"(?<![\w/])/(?:[A-Za-z0-9._-]+(?:/[A-Za-z0-9._-]+)*)(?=$|[^A-Za-z0-9._/-])")
_UNIX_ROOT = re.compile(r"(?<![\w/])/(?![\w/])")
_DSN = re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|redis)://\S+")
_TRACEBACK = re.compile(r"(?i)(traceback|most recent call|\bfile \".*\", line \d+)")
_TOOL_ARGUMENTS = re.compile(r"调用\s+[A-Za-z0-9_]+\s*\([^)]*\)")
_TOOL_ARGUMENT_LINE = re.compile(
    r"(?i)(?:^|[^\w])['\"]?(?:工具实参|arguments|tool[_-]?(?:args|input)|kwargs)['\"]?\s*[=:]"
)
_SECRET_ASSIGNMENT = re.compile(
    r"(?i)(?:^|[^\w])['\"]?(?:password|passwd|pwd|token|secret|api[_-]?key)['\"]?\s*[=:]"
)


def safe_request_topic(query: str) -> str:
    """把原始请求归类为固定主题，不回显用户输入。"""
    text = query.lower()
    if any(word in text for word in ("sql", "数据库", "索引", "慢查询", "select")):
        return "数据库/SQL 诊断请求"
    if any(word in text for word in ("cpu", "内存", "磁盘", "服务器", "进程", "网络")):
        return "服务器运行状态诊断请求"
    if any(word in text for word in ("日志", "log", "异常", "报错")):
        return "日志诊断请求"
    if any(word in text for word in ("知识", "文档", "sop", "手册")):
        return "知识库检索请求"
    return "运维诊断请求（未识别具体领域）"


def project_public_text(text: str, *, limit: int = 2000) -> str:
    """移除不应出现在公开结果中的原始请求、语句、路径、凭据与异常细节。"""
    safe_lines: list[str] = []
    in_code_fence = False
    for raw_line in desensitize(str(text)).splitlines():
        line = raw_line.strip()
        if line.startswith("```"):
            in_code_fence = not in_code_fence
            continue
        if in_code_fence or not line:
            continue
        if (
            _SQL_LINE.search(line)
            or _TRACEBACK.search(line)
            or _SECRET_ASSIGNMENT.search(line)
            or _TOOL_ARGUMENT_LINE.search(line)
        ):
            continue
        line = _DSN.sub("[已脱敏:连接信息]", line)
        line = _WINDOWS_PATH.sub("[已脱敏:路径]", line)
        line = _UNIX_PATH.sub("[已脱敏:路径]", line)
        line = _UNIX_ROOT.sub("[已脱敏:路径]", line)
        line = _TOOL_ARGUMENTS.sub("调用受控工具", line)
        safe_lines.append(line)
    projected = "\n".join(safe_lines).strip()
    return (projected or "暂无可安全展示的证据摘要")[:limit]


def project_public_report(report: str) -> str:
    """对外部组件提供统一的报告末端安全投影。"""
    return project_public_text(report, limit=8000)
