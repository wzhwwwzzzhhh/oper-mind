"""日志真实源只读 Connector —— 受管日志目录接入。

真实模式下 Log Agent 经本 Connector 读取绑定服务实例的受管日志目录，
只做行级只读检索 / 错误聚合 / 慢查询与超时模式解析，不做任何写操作。

安全约束：
- `log_dir` 为 None（环境变量未配置）→ `not_configured`；目录缺失/不可读 → `unavailable`，均不暴露异常详情。
- 遍历有解析根前缀校验（符号链接/解析到目录外一律拒绝）与凭据/隐藏文件排除。
- 读取有界（单行限长截断、扫描行数/返回条数上限）；检索关键字防路径逃逸。
- 跨层数据走 Pydantic 结构化模型，禁止隐式字典协议。
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field


# ---- 常量：有界扫描与安全防护（对齐知识检索工具集） ----
_LOG_SUFFIXES = (".log", ".txt")
_MAX_LINE_CHARS = 8192  # 单行日志上限（超长行截断，防超大单行撑爆内存）
_MAX_LINES_SCANNED = 50_000  # 单次检索扫描行数上限
_MAX_SEARCH_RESULTS = 50  # 检索返回条目上限
_MAX_ERROR_TYPES = 20  # 错误聚合类型上限
_MAX_SLOW_QUERIES = 10  # 慢查询/超时返回上限
_QUERY_MAX_LEN = 100  # 检索词长度上限
_ILLEGAL_QUERY_RE = re.compile(r"[/\\\x00-\x1f\x7f]")
_EXCLUDED_SUFFIXES = (".env", ".local.yaml", ".key", ".pem", ".secret")
_EXCLUDED_FILENAMES = {".env", "config.local.yaml"}
_LEVEL_RE = re.compile(r"^\[(ERROR|WARN|INFO|DEBUG|FATAL|WARNING)\]\s*(.*)$", re.IGNORECASE)
_TIMESTAMP_RE = re.compile(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)")
_SLOW_QUERY_RE = re.compile(r"Slow\s+query\b[^\d]{0,24}([\d.]+)\s*s", re.IGNORECASE)
_TIMEOUT_RE = re.compile(r"\btimeout\b|\btime\s+out\b|\btimed\s+out\b", re.IGNORECASE)


class LogEntry(BaseModel):
    """一条日志行的结构化事实（跨层数据，正文交由网关脱敏兜底）。"""

    source: str = Field(description="相对日志文件名")
    level: str = Field(description="日志级别（ERROR/WARN/INFO 等）")
    message: str = Field(description="日志行正文，不承载凭据（网关兜底脱敏）")
    timestamp: datetime | None = Field(default=None, description="解析到的时间戳；未解析为 None")


class LogSearchResult(BaseModel):
    """检索真实日志源的结果或诚实降级。"""

    status: Literal["not_configured", "unavailable", "invalid", "ok"]
    message: str = Field(description="面向用户的摘要/降级文案")
    keyword: str = ""
    total_hits: int = 0
    entries: list[LogEntry] = Field(default_factory=list)


class ErrorAggregationResult(BaseModel):
    """错误类型与频率聚合结果或诚实降级。"""

    status: Literal["not_configured", "unavailable", "ok"]
    message: str
    error_counts: dict[str, int] = Field(default_factory=dict)
    total_errors: int = 0


class SlowQueryEntry(BaseModel):
    """解析到的一条慢查询记录。"""

    source: str
    time_seconds: float
    snippet: str


class SlowQueryReport(BaseModel):
    """慢查询与超时关联报告或诚实降级。"""

    status: Literal["not_configured", "unavailable", "ok"]
    message: str
    slow_queries: list[SlowQueryEntry] = Field(default_factory=list)
    timeout_count: int = 0
    timeout_snippets: list[str] = Field(default_factory=list)


class LogSourceConnector:
    """受管日志目录只读 Connector。

    - `log_dir` 为 None → `not_configured`；目录缺失/不可读 → `unavailable`。
    - 只读扫描，禁止任何写操作；遍历有解析根前缀校验与凭据/隐藏文件排除。
    """

    def __init__(self, log_dir: str | None, instance_id: str = "") -> None:
        self._log_dir = log_dir
        self._instance_id = instance_id

    # ---- 状态解析 ----
    def _resolve_root(self) -> Path | None:
        """解析受管目录根；未配置返回 None（not_configured），缺失/不可读也返回 None。"""
        if not self._log_dir:
            return None
        try:
            root = Path(self._log_dir).resolve()
        except OSError:
            return None
        if not root.is_dir():
            return None
        return root

    def _degradation(self, field: str) -> tuple[str, str]:
        """按配置状态返回 (status, message) 的诚实降级对。"""
        if not self._log_dir:
            return "not_configured", "日志源未配置"
        return "unavailable", "日志源不可用"

    # ---- 遍历与过滤 ----
    def _allowed(self, path: Path, root: Path) -> bool:
        """判断日志文件是否在受管根内且非隐藏/凭据类文件。"""
        try:
            rel = path.resolve().relative_to(root)
        except ValueError:
            # 符号链接等解析到受管目录之外：拒绝越权访问
            return False
        if any(part.startswith(".") for part in rel.parts):
            return False
        lowered = path.name.lower()
        if lowered in _EXCLUDED_FILENAMES or lowered.endswith(_EXCLUDED_SUFFIXES):
            return False
        return True

    def _scan_lines(self, root: Path) -> list[tuple[str, str]] | None:
        """确定性遍历受管目录内文本日志行；目录不可遍历返回 None 以降级为 unavailable。"""
        lines: list[tuple[str, str]] = []
        try:
            for path in sorted(root.rglob("*")):
                if len(lines) >= _MAX_LINES_SCANNED:
                    break
                if not path.is_file() or path.suffix.lower() not in _LOG_SUFFIXES:
                    continue
                if not self._allowed(path, root):
                    continue
                try:
                    with path.open("r", encoding="utf-8", errors="ignore") as handle:
                        for raw in handle:
                            if len(lines) >= _MAX_LINES_SCANNED:
                                break
                            line = raw.rstrip("\n")
                            if len(line) > _MAX_LINE_CHARS:
                                line = line[:_MAX_LINE_CHARS] + "…(超长行已截断)"
                            lines.append((path.name, line))
                except OSError:
                    # 单文件读取失败跳过，不拖垮整体
                    continue
        except OSError:
            return None
        return lines

    @staticmethod
    def _level_and_message(line: str) -> tuple[str, str]:
        """拆出级别与正文；无法识别级别时按 INFO 处理。"""
        match = _LEVEL_RE.match(line)
        if match:
            return match.group(1).upper(), match.group(2)
        return "INFO", line

    @staticmethod
    def _timestamp(line: str) -> datetime | None:
        """解析行内首处时间戳；格式不支持或非法返回 None。"""
        match = _TIMESTAMP_RE.search(line)
        if not match:
            return None
        try:
            return datetime.fromisoformat(match.group(1))
        except ValueError:
            return None

    @staticmethod
    def _extract_error_type(message: str) -> str:
        """提取错误类别：去时间戳与分隔符前缀后取首个冒号/括号前的前 3 个词。"""
        text = re.sub(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?\s*", "", message)
        text = re.sub(r"^-\s+", "", text)
        text = re.split(r"[:：(]|\.", text, maxsplit=1)[0]
        words = " ".join(text.split()).split()[:3]
        return " ".join(words) or "未知"

    # ---- 只读检索与分析 ----
    def search(self, keyword: str, time_range_hours: float | None) -> LogSearchResult:
        """按关键字（可选时间范围）检索真实日志源，返回有界命中。"""
        normalized = (keyword or "").strip()
        if not normalized:
            return LogSearchResult(status="invalid", message="检索词为空，已拒绝")
        if len(normalized) > _QUERY_MAX_LEN or _ILLEGAL_QUERY_RE.search(normalized):
            return LogSearchResult(status="invalid", message="检索词含路径分隔符或控制字符，已拒绝（防路径逃逸）")

        root = self._resolve_root()
        if root is None:
            status, message = self._degradation("search")
            return LogSearchResult(status=status, message=message, keyword=normalized)
        lines = self._scan_lines(root)
        if lines is None:
            return LogSearchResult(status="unavailable", message="日志源不可用", keyword=normalized)

        needle = normalized.lower()
        now = datetime.now()
        matches: list[LogEntry] = []
        hits = 0
        for name, line in lines:
            if needle not in line.lower():
                continue
            ts = self._timestamp(line)
            if time_range_hours is not None and ts is not None and now - ts > timedelta(hours=time_range_hours):
                continue
            hits += 1
            if len(matches) < _MAX_SEARCH_RESULTS:
                level, message = self._level_and_message(line)
                matches.append(LogEntry(source=name, level=level, message=message, timestamp=ts))

        return LogSearchResult(
            status="ok",
            keyword=normalized,
            total_hits=hits,
            entries=matches,
            message=f"日志源检索命中 {hits} 条",
        )

    def aggregate_errors(self) -> ErrorAggregationResult:
        """聚合错误类型与频率（取级别为 ERROR 的行）。"""
        root = self._resolve_root()
        if root is None:
            status, message = self._degradation("aggregate")
            return ErrorAggregationResult(status=status, message=message)
        lines = self._scan_lines(root)
        if lines is None:
            return ErrorAggregationResult(status="unavailable", message="日志源不可用")

        counter: Counter[str] = Counter()
        for _, line in lines:
            if "[ERROR]" not in line.upper():
                continue
            _, message = self._level_and_message(line)
            counter[self._extract_error_type(message)] += 1

        error_counts = dict(counter.most_common(_MAX_ERROR_TYPES))
        return ErrorAggregationResult(
            status="ok",
            error_counts=error_counts,
            total_errors=sum(error_counts.values()),
            message=f"日志源聚合 {sum(error_counts.values())} 条错误、{len(error_counts)} 类",
        )

    def slow_query_patterns(
        self,
        limit: int = _MAX_SLOW_QUERIES,
        threshold_seconds: float = 1.0,
    ) -> SlowQueryReport:
        """解析慢查询行并关联超时模式，返回有界报告。"""
        root = self._resolve_root()
        if root is None:
            status, message = self._degradation("slow_query")
            return SlowQueryReport(status=status, message=message)
        lines = self._scan_lines(root)
        if lines is None:
            return SlowQueryReport(status="unavailable", message="日志源不可用")

        slow: list[SlowQueryEntry] = []
        timeout_snippets: list[str] = []
        timeout_total = 0
        for name, line in lines:
            match = _SLOW_QUERY_RE.search(line)
            if match:
                try:
                    seconds = float(match.group(1))
                except ValueError:
                    seconds = 0.0
                if seconds >= threshold_seconds and len(slow) < limit:
                    slow.append(SlowQueryEntry(source=name, time_seconds=seconds, snippet=line[:120]))
            if _TIMEOUT_RE.search(line):
                timeout_total += 1
                if len(timeout_snippets) < limit:
                    timeout_snippets.append(line[:120])

        return SlowQueryReport(
            status="ok",
            slow_queries=slow,
            timeout_count=timeout_total,
            timeout_snippets=timeout_snippets,
            message=f"日志源慢查询 {len(slow)} 条、超时 {timeout_total} 次",
        )
