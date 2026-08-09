"""P6 主机指标采集器 — 通过 psutil 采集后端所在主机结构化指标。

诚实降级（产品定义 §5.5）：psutil 缺失 / 采集失败 / 超时 → `unavailable` + null 标量，
不伪造数值、不用 0 代替缺失。mock 模式读 `data/scenarios.py` 激活场景的预格式化串，
确定性解析（S1–S4 字符串固定，解析为纯函数、可单测锁定）。

设计见 `docs/design/monitor/P6服务主机指标监控Design.md`。
"""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Callable
from datetime import UTC, datetime

from data.scenarios import get_active_scenario

from src.domain.host_metrics import (
    HostDiskPartitionData,
    HostMetricsCollector,
    HostMetricsData,
    HostMetricsMode,
    HostMetricsSourceStatus,
    HostProcessData,
)

LOGGER = logging.getLogger(__name__)

_GIB = 1024 ** 3

# mock 预格式化串的确定性解析正则（S1–S4 字符串格式固定）。
_CPU_PATTERN = re.compile(r"CPU 使用率:\s*([\d.]+)%\s*\((\d+)\s*核\)")
_LOAD_PATTERN = re.compile(r"Load Average:\s*([\d.]+)")
_MEMORY_PATTERN = re.compile(r"内存:\s*总计\s*(\d+)GB,\s*已用\s*(\d+)GB\s*\(([\d.]+)%\)")
_DISK_PARTITION_PATTERN = re.compile(r"\s*(\S+):\s*([\d.]+)%\s*\((\d+)GB\s*/\s*(\d+)GB\)")
_PROCESS_CPU_PATTERN = re.compile(r"(?m)^\s*([^\s(]+)\(PID=(\d+)\):\s*CPU\s*([\d.]+)%")
_PROCESS_MEMORY_PATTERN = re.compile(r"(?m)^\s*([^\s(]+)\(PID=(\d+)\):\s*内存\s*([\d.]+)%")
_NETWORK_TOTAL_PATTERN = re.compile(r"总连接数:\s*(\d+)")
_NETWORK_ESTABLISHED_PATTERN = re.compile(r"ESTABLISHED:\s*(\d+)")
_NETWORK_TIME_WAIT_PATTERN = re.compile(r"TIME_WAIT:\s*(\d+)")


def _first_float(pattern: re.Pattern[str], text: str, group: int) -> float | None:
    """从文本中取第一个匹配数字；缺失或无法解析返回 None。"""
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return float(match.group(group))
    except (TypeError, ValueError):
        return None


def _first_int(pattern: re.Pattern[str], text: str, group: int) -> int | None:
    """从文本中取第一个匹配整数；缺失或无法解析返回 None。"""
    value = _first_float(pattern, text, group)
    return int(value) if value is not None else None


def _parse_mock(server: dict[str, str], observed_at: datetime) -> HostMetricsData:
    """把激活场景的预格式化串解析为确定性结构化标量。"""
    cpu_text = server.get("cpu", "")
    memory_text = server.get("memory", "")
    disk_text = server.get("disk", "")
    process_text = server.get("process", "")
    network_text = server.get("network", "")

    partitions: list[HostDiskPartitionData] = []
    for match in _DISK_PARTITION_PATTERN.finditer(disk_text):
        partitions.append(
            HostDiskPartitionData(
                mount=match.group(1),
                percent=float(match.group(2)),
                used_bytes=int(float(match.group(3)) * _GIB),
                total_bytes=int(float(match.group(4)) * _GIB),
            )
        )
    disk_used_percent = max(
        (part.percent for part in partitions if part.percent is not None), default=None
    )

    processes: list[HostProcessData] = []
    seen: dict[int, HostProcessData] = {}
    for match in _PROCESS_CPU_PATTERN.finditer(process_text):
        pid = int(match.group(2))
        seen[pid] = HostProcessData(
            name=match.group(1).strip(),
            pid=pid,
            cpu_percent=float(match.group(3)),
        )
    for match in _PROCESS_MEMORY_PATTERN.finditer(process_text):
        pid = int(match.group(2))
        existing = seen.get(pid)
        if existing is None:
            seen[pid] = HostProcessData(name=match.group(1).strip(), pid=pid)
            existing = seen[pid]
        seen[pid] = HostProcessData(
            name=existing.name,
            pid=existing.pid,
            cpu_percent=existing.cpu_percent,
            memory_percent=float(match.group(3)),
        )
    processes = list(seen.values())

    return HostMetricsData(
        mode=HostMetricsMode.MOCK,
        source_status=HostMetricsSourceStatus.AVAILABLE,
        observed_at=observed_at,
        cpu_percent=_first_float(_CPU_PATTERN, cpu_text, 1),
        cpu_count=_first_int(_CPU_PATTERN, cpu_text, 2),
        load_avg_1m=_first_float(_LOAD_PATTERN, cpu_text, 1),
        memory_total_bytes=_gib_bytes(_first_int(_MEMORY_PATTERN, memory_text, 1)),
        memory_used_bytes=_gib_bytes(_first_int(_MEMORY_PATTERN, memory_text, 2)),
        memory_percent=_first_float(_MEMORY_PATTERN, memory_text, 3),
        disk_used_percent=disk_used_percent,
        disk_top_partitions=tuple(partitions),
        network_connections=_first_int(_NETWORK_TOTAL_PATTERN, network_text, 1),
        network_established=_first_int(_NETWORK_ESTABLISHED_PATTERN, network_text, 1),
        network_time_wait=_first_int(_NETWORK_TIME_WAIT_PATTERN, network_text, 1),
        abnormal_processes=tuple(processes),
    )


def _gib_bytes(value: int | None) -> int | None:
    """把 mock 串中的 GB 值转换为字节；None 保持 None。"""
    if value is None:
        return None
    return int(value * _GIB)


class PsutilHostMetricsCollector:
    """psutil 采集后端所在主机指标，带短 TTL 缓存与显式时间预算。"""

    def __init__(self, cache_seconds: int = 10, time_budget_seconds: float = 1.5) -> None:
        self._cache_seconds = cache_seconds
        self._time_budget_seconds = time_budget_seconds
        # (过期时刻, 缓存结果)；mock 模式不走缓存。
        self._cache: tuple[float, HostMetricsData] | None = None

    def collect(self) -> HostMetricsData:
        """采集主机指标；mock 读场景，真实读 psutil，失败返回不可用。"""
        active = get_active_scenario()
        observed_at = datetime.now(UTC)
        if active is not None:
            return _parse_mock(active.server, observed_at)
        if self._cache is not None and self._cache[0] > time.monotonic():
            return self._cache[1]
        result = self._collect_target(observed_at)
        if self._cache_seconds > 0:
            self._cache = (time.monotonic() + self._cache_seconds, result)
        return result

    def _load_psutil(self):
        """延迟导入 psutil；缺失时由调用方收敛为不可用（供测试替换）。"""
        import psutil

        return psutil

    def _collect_target(self, observed_at: datetime) -> HostMetricsData:
        """真实模式采集；任何异常收敛为 unavailable，不伪造数值。"""
        try:
            return self._collect_target_unbounded(observed_at)
        except Exception:
            LOGGER.warning("主机指标采集不可用，按不可用降级处理")
            return HostMetricsData.unavailable(observed_at, mode=HostMetricsMode.TARGET)

    def _collect_target_unbounded(self, observed_at: datetime) -> HostMetricsData:
        psutil = self._load_psutil()
        deadline = time.monotonic() + self._time_budget_seconds

        def within_budget() -> bool:
            return time.monotonic() <= deadline

        # cold cache 时才用 interval=1 取一次有意义值（一次约 1s，受时间预算约束）；
        # 采样器周期性采集为缓存保温，API 请求通常直接命中缓存。
        cpu_percent = float(psutil.cpu_percent(interval=1))
        cpu_count = int(psutil.cpu_count() or 0) or None
        load_avg = psutil.getloadavg() if hasattr(psutil, "getloadavg") else None
        memory = psutil.virtual_memory()
        if not within_budget():
            raise TimeoutError("主机指标采集超出时间预算")

        partitions: list[HostDiskPartitionData] = []
        for part in psutil.disk_partitions():
            if not within_budget():
                raise TimeoutError("主机指标采集超出时间预算")
            try:
                usage = psutil.disk_usage(part.mountpoint)
            except (OSError, PermissionError):
                continue
            partitions.append(
                HostDiskPartitionData(
                    mount=part.mountpoint,
                    percent=float(usage.percent),
                    used_bytes=int(usage.used),
                    total_bytes=int(usage.total),
                )
            )
        disk_used_percent = max(
            (part.percent for part in partitions if part.percent is not None), default=None
        )

        network_connections: int | None = None
        network_established: int | None = None
        network_time_wait: int | None = None
        try:
            connections = psutil.net_connections()
            network_connections = len(connections)
            network_established = sum(1 for conn in connections if conn.status == "ESTABLISHED")
            network_time_wait = sum(1 for conn in connections if conn.status == "TIME_WAIT")
        except (psutil.AccessDenied, OSError):
            # 无权限枚举连接时标量置 null，不把整体降级为不可用。
            pass
        if not within_budget():
            raise TimeoutError("主机指标采集超出时间预算")

        return HostMetricsData(
            mode=HostMetricsMode.TARGET,
            source_status=HostMetricsSourceStatus.AVAILABLE,
            observed_at=observed_at,
            cpu_percent=cpu_percent,
            cpu_count=cpu_count,
            load_avg_1m=float(load_avg[0]) if load_avg else None,
            memory_total_bytes=int(memory.total),
            memory_used_bytes=int(memory.used),
            memory_percent=float(memory.percent),
            disk_used_percent=disk_used_percent,
            disk_top_partitions=tuple(partitions),
            network_connections=network_connections,
            network_established=network_established,
            network_time_wait=network_time_wait,
            abnormal_processes=tuple(self._collect_processes(psutil, within_budget)),
        )

    def _collect_processes(
        self,
        psutil,
        within_budget: Callable[[], bool],
    ) -> list[HostProcessData]:
        """收集高 CPU/高内存异常进程，最多 5 条，仅暴露 name/pid/占用率。"""
        result: list[HostProcessData] = []
        for proc in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
            if not within_budget():
                raise TimeoutError("主机指标采集超出时间预算")
            try:
                info = proc.info
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            pid = info.get("pid")
            if not isinstance(pid, int) or pid < 1:
                continue
            cpu = info.get("cpu_percent")
            mem = info.get("memory_percent")
            cpu_float = float(cpu) if isinstance(cpu, (int, float)) else None
            mem_float = float(mem) if isinstance(mem, (int, float)) else None
            if (cpu_float is not None and cpu_float > 50) or (mem_float is not None and mem_float > 10):
                result.append(
                    HostProcessData(
                        name=str(info.get("name") or "unknown")[:200],
                        pid=pid,
                        cpu_percent=cpu_float,
                        memory_percent=mem_float,
                    )
                )
                if len(result) >= 5:
                    break
        return result


__all__ = [
    "HostMetricsCollector",
    "HostMetricsMode",
    "HostMetricsSourceStatus",
    "PsutilHostMetricsCollector",
]
