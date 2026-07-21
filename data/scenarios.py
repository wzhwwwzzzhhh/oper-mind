"""多故障 mock 世界 —— 评测与演示的唯一确定性数据源。

背景：早期 mock 数据散落三处且只有一起故障（orders 索引级联），导致所有复合
用例答案恒定、多 Agent 无从证明价值；且日志内联在 log_tools、服务器走真 psutil，
`data/mock_logs.py` 与 `data/mock_server.py` 是无人引用的死代码。

本模块把「一起故障」扩为 S1–S4 四起**根因刻意分散在不同域**的场景，并提供
「当前激活场景」状态机：mock 模式下由 bootstrap 默认激活 S1，评测 Runner 可按
用例切换（M5 step3 接入）。工具在 mock 模式读激活场景，保证确定性、可复现。

设计见 docs/开发/M5-多Agent价值对比/design.md 与 step2。
"""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Scenario:
    """一起故障场景的完整世界状态。

    根因刻意分散：单模型只看单一表象会误判，需多 Agent 跨源印证才能定位。
    """

    key: str
    title: str
    root_cause_domain: str  # 真根因所在域：db / server / app / config
    summary: str  # 一句话根因，供文档与调试
    logs: tuple[str, ...]  # 系统日志，SearchLogsTool / AggregateErrorsTool 消费
    slow_queries: tuple[dict[str, Any], ...]  # 慢查询，QuerySlowLogTool 消费
    server: dict[str, str]  # 键：cpu/memory/disk/process/network → 预格式化指标串（只读；S1–S4 为共享单例，勿原地改）


# ============================================================
# S1 —— DB 慢查询级联（真根因：DB 缺索引）。基准场景，等价于早期唯一的 mock 世界。
# ============================================================
_S1 = Scenario(
    key="S1",
    title="DB 慢查询级联",
    root_cause_domain="db",
    summary="orders.status 缺索引导致全表扫描，拖垮连接池并触发 mysqld 被 OOM 杀",
    logs=(
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
    ),
    slow_queries=(
        {"sql": "SELECT * FROM orders WHERE status = 'PENDING'", "time": 5.2, "rows": 50000},
        {"sql": "SELECT * FROM orders o JOIN order_items i ON o.id = i.order_id", "time": 3.8, "rows": 200000},
        {"sql": "SELECT * FROM orders ORDER BY create_time DESC", "time": 4.1, "rows": 50000},
    ),
    server={
        "cpu": "CPU 使用率: 92% (4 核)\nLoad Average: 3.80, 3.10, 2.40",
        "memory": "内存: 总计 16GB, 已用 13GB (81%), 剩余 3GB\nSwap: 总计 2GB, 已用 1.2GB (60%)",
        "disk": "磁盘使用情况:\n  /: 62% (115GB / 185GB)\n  /data: 70% (358GB / 512GB)",
        "process": "高 CPU 进程:\n  mysqld(PID=1234): CPU 85%\n\n高内存进程:\n  java(PID=5678): 内存 45%",
        "network": "总连接数: 1024\nESTABLISHED: 512\nTIME_WAIT: 256\nCLOSE_WAIT: 12",
    },
)


# ============================================================
# S2 —— 磁盘写满（真根因：server 磁盘 /data 接近 100%）。DB 本身健康，与索引无关。
# ============================================================
_S2 = Scenario(
    key="S2",
    title="磁盘写满",
    root_cause_domain="server",
    summary="/data 挂载点磁盘使用率 98%，写入失败引发应用报错；DB 与 SQL 均正常",
    logs=(
        "[ERROR] 2026-07-11 14:02:10 - No space left on device: /data",
        "[ERROR] 2026-07-11 14:02:11 - Failed to write file: /data/app/upload_8821.tmp (No space left on device)",
        "[WARN] 2026-07-11 14:01:30 - Disk usage threshold exceeded: /data 98%",
        "[ERROR] 2026-07-11 14:02:15 - Application exception: java.io.IOException: No space left on device",
        "[WARN] 2026-07-11 14:02:20 - Write retry failed after 3 attempts: /data/app/session.log",
    ),
    slow_queries=(),  # DB 健康，无慢查询
    server={
        "cpu": "CPU 使用率: 35% (4 核)\nLoad Average: 1.10, 0.90, 0.80",
        "memory": "内存: 总计 16GB, 已用 6GB (38%), 剩余 10GB\nSwap: 总计 2GB, 已用 0.2GB (10%)",
        "disk": "磁盘使用情况:\n  /: 55% (102GB / 185GB)\n  /data: 98% (502GB / 512GB)",
        "process": "未发现异常进程",
        "network": "总连接数: 210\nESTABLISHED: 180\nTIME_WAIT: 20",
    },
)


# ============================================================
# S3 —— 应用内存泄漏（真根因：应用 JVM 堆泄漏）。与 S1 同表象（内存高/OOM）但根因不同：
#        S1 是 DB 慢查询占内存、mysqld 被杀；S3 是 java 应用堆泄漏、mysqld 正常。
# ============================================================
_S3 = Scenario(
    key="S3",
    title="应用内存泄漏",
    root_cause_domain="app",
    summary="java 应用堆内存只增不减，Full GC 频繁并抛 OutOfMemoryError；DB 正常",
    logs=(
        "[WARN] 2026-07-12 09:15:00 - GC overhead limit approaching: Full GC 12 times in 60s",
        "[WARN] 2026-07-12 09:16:10 - Heap usage 95% after Full GC (memory leak suspected)",
        "[ERROR] 2026-07-12 09:17:22 - Application exception: java.lang.OutOfMemoryError: Java heap space",
        "[WARN] 2026-07-12 09:17:30 - Request latency spike: p99 8500ms during GC pause",
        "[INFO] 2026-07-12 09:18:00 - Application thread dump captured for heap analysis",
    ),
    slow_queries=(),  # DB 健康；变慢源于 GC 停顿而非慢查询
    server={
        "cpu": "CPU 使用率: 70% (4 核)\nLoad Average: 2.50, 2.30, 2.10",
        "memory": "内存: 总计 16GB, 已用 15GB (94%), 剩余 1GB\nSwap: 总计 2GB, 已用 1.8GB (90%)",
        "disk": "磁盘使用情况:\n  /: 48% (89GB / 185GB)\n  /data: 40% (205GB / 512GB)",
        "process": "高内存进程:\n  java(PID=5678): 内存 78%",  # 泄漏进程是 java，非 mysqld
        "network": "总连接数: 260\nESTABLISHED: 240\nTIME_WAIT: 15",
    },
)


# ============================================================
# S4 —— 连接数配置过低（真根因：max_connections 配置错误）。表象误导型：报 too many
#        connections 像 DB 慢，但 SQL 快、资源正常 —— 加索引无用，须改配置。
# ============================================================
_S4 = Scenario(
    key="S4",
    title="连接数配置过低",
    root_cause_domain="config",
    summary="max_connections=100 配置过低，高峰期连接槽耗尽；SQL 执行快、资源正常",
    logs=(
        "[ERROR] 2026-07-13 20:31:05 - Connection refused: too many connections (current: 100, max_connections=100)",
        "[ERROR] 2026-07-13 20:31:06 - FATAL: remaining connection slots are reserved",
        "[INFO] 2026-07-13 20:30:00 - MySQL config loaded: max_connections=100 (default)",
        "[WARN] 2026-07-13 20:31:10 - Connection wait timeout after 30s in application pool",
    ),
    slow_queries=(),  # 查询本身很快，只是拿不到连接
    server={
        "cpu": "CPU 使用率: 30% (4 核)\nLoad Average: 0.90, 0.80, 0.70",
        "memory": "内存: 总计 16GB, 已用 5GB (31%), 剩余 11GB\nSwap: 总计 2GB, 已用 0.1GB (5%)",
        "disk": "磁盘使用情况:\n  /: 50% (92GB / 185GB)\n  /data: 45% (230GB / 512GB)",
        "process": "未发现异常进程",
        "network": "总连接数: 100\nESTABLISHED: 100\nTIME_WAIT: 5",  # 连接数正好卡在配置上限 100
    },
)


_SCENARIOS: dict[str, Scenario] = {s.key: s for s in (_S1, _S2, _S3, _S4)}
_DEFAULT_KEY = "S1"

# 当前激活场景；None 表示未激活（真实模式，工具走真实数据源如 psutil）
_active_scenario: Scenario | None = None


def get_scenario(key: str) -> Scenario:
    """按 key 取场景，非法 key 直接报错。"""
    try:
        return _SCENARIOS[key]
    except KeyError as error:
        supported = "、".join(_SCENARIOS)
        raise ValueError(f"不支持的场景：{key}，可选值：{supported}") from error


def supported_scenarios() -> tuple[str, ...]:
    """返回全部合法场景 key。"""
    return tuple(_SCENARIOS)


def set_active_scenario(key: str) -> None:
    """激活指定场景（mock 模式下由 bootstrap / 评测 Runner 调用）。"""
    global _active_scenario
    _active_scenario = get_scenario(key)


def clear_active_scenario() -> None:
    """清除激活场景（真实模式）。"""
    global _active_scenario
    _active_scenario = None


def get_active_scenario() -> Scenario | None:
    """返回当前激活场景；None 表示未激活。服务器工具据此决定读 mock 还是 psutil。"""
    return _active_scenario


def active_or_default() -> Scenario:
    """返回激活场景，未激活时回落到默认 S1。

    供无真实数据源的工具（日志、DB 慢查询）使用——它们始终是 mock。
    """
    return _active_scenario or _SCENARIOS[_DEFAULT_KEY]
