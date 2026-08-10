"""服务器监控工具集 — 通过 psutil 采集系统指标"""

from data.scenarios import get_active_scenario

from src.core.tool_registry import Tool


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

    def execute(self) -> str:
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
        except ImportError:
            # 无 psutil 时返回模拟数据
            return "CPU 使用率: 65% (4 核)\nLoad Average: 2.50, 1.80, 1.20"


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

    def execute(self) -> str:
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
        except ImportError:
            return "内存: 总计 16GB, 已用 12GB (75%), 剩余 4GB\nSwap: 总计 2GB, 已用 1.5GB (75%)"


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

    def execute(self) -> str:
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
        except ImportError:
            return "磁盘使用情况:\n  /: 65% (120GB / 185GB)"


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

    def execute(self) -> str:
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
        except ImportError:
            return "高 CPU 进程:\n  mysqld(PID=1234): CPU 85%\n\n高内存进程:\n  java(PID=5678): 内存 45%"


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

    def execute(self) -> str:
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
        except ImportError:
            return "总连接数: 1024\nESTABLISHED: 512\nTIME_WAIT: 256\nCLOSE_WAIT: 12"
