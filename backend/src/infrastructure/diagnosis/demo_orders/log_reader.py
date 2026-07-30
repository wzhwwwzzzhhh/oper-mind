"""P4.1 固定订单服务日志的只读聚合读取器。"""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

from src.infrastructure.diagnosis.demo_orders.models import LogEvidenceSnapshot
from src.infrastructure.diagnosis.demo_orders.postgres_reader import DemoOrdersSourceError
from src.infrastructure.diagnosis.demo_orders.settings import DemoOrdersEvidenceSettings


class OrderServiceLogReader:
    """只聚合订单服务诊断路由的有限 JSONL 窗口。"""

    def __init__(
        self,
        settings: DemoOrdersEvidenceSettings,
        line_reader: Callable[[Path, int], list[str]] | None = None,
    ) -> None:
        self._log_file = settings.log_file
        self._line_limit = settings.log_line_limit
        self._line_reader = line_reader or _read_last_lines

    def collect(self) -> LogEvidenceSnapshot:
        """返回慢查询和超时计数，跳过单条损坏日志而不回传原文。"""
        lines = self._line_reader(self._log_file, self._line_limit)
        matched_count = 0
        slow_query_count = 0
        timeout_count = 0
        for line in lines:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(record, dict):
                continue
            if record.get("event") != "order_query" or record.get("route") != "/orders/diagnostic-probe":
                continue
            matched_count += 1
            if record.get("slow_query") is True:
                slow_query_count += 1
            if record.get("timeout") is True:
                timeout_count += 1
        return LogEvidenceSnapshot(
            observed_at=datetime.now(timezone.utc),
            matched_query_count=matched_count,
            slow_query_count=slow_query_count,
            timeout_count=timeout_count,
        )


def _read_last_lines(path: Path, line_limit: int) -> list[str]:
    """有限读取固定日志文件；文件不可用时只报告安全的源失败。"""
    try:
        with path.open("r", encoding="utf-8") as file:
            return list(deque(file, maxlen=line_limit))
    except (OSError, UnicodeDecodeError) as error:
        raise DemoOrdersSourceError("日志只读证据不可用") from error
