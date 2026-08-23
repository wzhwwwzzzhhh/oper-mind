"""服务器监控工具集 — 通过 psutil 采集系统指标"""

from data.scenarios import get_active_scenario

from src.core.tool_registry import Tool, ToolExecutionResult


def _unavailable(metric: str) -> ToolExecutionResult:
    """构造不含异常细节或虚构数值的服务器指标降级结果。"""
    return ToolExecutionResult(
        status="unavailable",
        output=f"{metric}指标采集暂不可用",
        summary=f"服务器{metric}指标采集不可用",
    )


class CheckCpuTool(Tool):
    """检查 CPU 使用率"""

    def __init__(self):
        super().__init__(
            name="check_cpu",
            description="检查 CPU 使用率、load average、高 CPU 进程",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str | ToolExecutionResult:
        """采集 CPU 指标"""
        active = get_active_scenario()
        if active is not None:  # mock 模式：读确定性场景指标，不走真机 psutil
            return active.server["cpu"]
        try:
            import psutil
            cpu_percent = psutil.cpu_percent(interval=1)
            cpu_count = psutil.cpu_count()
            load_avg = psutil.getloadavg()
            return (
                f"CPU 使用率: {cpu_percent}% ({cpu_count} 核)\n"
                f"Load Average: {load_avg[0]:.2f}, {load_avg[1]:.2f}, {load_avg[2]:.2f}"
            )
        except Exception:
            return _unavailable("CPU")


class CheckMemoryTool(Tool):
    """检查内存使用情况"""

    def __init__(self):
        super().__init__(
            name="check_memory",
            description="检查内存使用情况，包括总/已用/剩余/Swap",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str | ToolExecutionResult:
        active = get_active_scenario()
        if active is not None:  # mock 模式：读确定性场景指标
            return active.server["memory"]
        try:
            import psutil
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            return (
                f"内存: 总计 {mem.total // 1024**3}GB, "
                f"已用 {mem.used // 1024**3}GB ({mem.percent}%), "
                f"剩余 {mem.available // 1024**3}GB\n"
                f"Swap: 总计 {swap.total // 1024**3}GB, "
                f"已用 {swap.used // 1024**3}GB ({swap.percent}%)"
            )
        except Exception:
            return _unavailable("内存")


class CheckDiskTool(Tool):
    """检查磁盘使用情况"""

    def __init__(self):
        super().__init__(
            name="check_disk",
            description="检查磁盘空间和 IO",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str | ToolExecutionResult:
        active = get_active_scenario()
        if active is not None:  # mock 模式：读确定性场景指标
            return active.server["disk"]
        try:
            import psutil
            disks = []
            for part in psutil.disk_partitions():
                usage = psutil.disk_usage(part.mountpoint)
                disks.append(
                    f"  {part.mountpoint}: {usage.percent}% "
                    f"({usage.used // 1024**3}GB / {usage.total // 1024**3}GB)"
                )
            return "磁盘使用情况:\n" + "\n".join(disks)
        except Exception:
            return _unavailable("磁盘")


class CheckProcessTool(Tool):
    """检查异常进程"""

    def __init__(self):
        super().__init__(
            name="check_process",
            description="检查异常进程（僵尸、高内存、高 CPU）",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str | ToolExecutionResult:
        active = get_active_scenario()
        if active is not None:  # mock 模式：读确定性场景指标
            return active.server["process"]
        try:
            import psutil
            high_cpu = []
            high_mem = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    info = proc.info
                    if info['cpu_percent'] and info['cpu_percent'] > 50:
                        high_cpu.append(f"  {info['name']}(PID={info['pid']}): CPU {info['cpu_percent']}%")
                    if info['memory_percent'] and info['memory_percent'] > 10:
                        high_mem.append(f"  {info['name']}(PID={info['pid']}): 内存 {info['memory_percent']:.1f}%")
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

            result = []
            if high_cpu:
                result.append("高 CPU 进程:\n" + "\n".join(high_cpu[:5]))
            if high_mem:
                result.append("高内存进程:\n" + "\n".join(high_mem[:5]))
            return "\n\n".join(result) if result else "未发现异常进程"
        except Exception:
            return _unavailable("进程")


class CheckNetworkTool(Tool):
    """检查网络连接"""

    def __init__(self):
        super().__init__(
            name="check_network",
            description="检查网络连接数、TIME_WAIT 堆积、带宽",
            parameters={
                "type": "object",
                "properties": {},
                "required": [],
            },
        )

    def execute(self) -> str | ToolExecutionResult:
        active = get_active_scenario()
        if active is not None:  # mock 模式：读确定性场景指标
            return active.server["network"]
        try:
            import psutil
            conns = psutil.net_connections()
            total = len(conns)
            time_wait = sum(1 for c in conns if c.status == 'TIME_WAIT')
            established = sum(1 for c in conns if c.status == 'ESTABLISHED')
            return (
                f"总连接数: {total}\n"
                f"ESTABLISHED: {established}\n"
                f"TIME_WAIT: {time_wait}"
            )
        except Exception:
            return _unavailable("网络")
