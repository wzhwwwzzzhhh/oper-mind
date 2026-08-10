"""server_tools mock 路径回归锚点（P6 AC5）。

P6 不修改 `server_tools.py`；本文件锁定「mock 模式下各工具返回原场景预格式化串、
与改动前一致」，防止后续主机指标改造意外破坏 S1–S4 评测路径。
"""

from __future__ import annotations

from data.scenarios import set_active_scenario

from src.tools.server_tools import (
    CheckCpuTool,
    CheckDiskTool,
    CheckMemoryTool,
    CheckNetworkTool,
    CheckProcessTool,
)


class TestMockModeUnchanged:
    """AC5：mock 模式下每个 server 工具返回原 mock 结果。"""

    def test_s1_cpu(self) -> None:
        set_active_scenario("S1")
        from data.scenarios import get_active_scenario

        assert CheckCpuTool().execute() == get_active_scenario().server["cpu"]

    def test_s1_memory(self) -> None:
        set_active_scenario("S1")
        from data.scenarios import get_active_scenario

        assert CheckMemoryTool().execute() == get_active_scenario().server["memory"]

    def test_s1_disk(self) -> None:
        set_active_scenario("S1")
        from data.scenarios import get_active_scenario

        assert CheckDiskTool().execute() == get_active_scenario().server["disk"]

    def test_s1_process(self) -> None:
        set_active_scenario("S1")
        from data.scenarios import get_active_scenario

        assert CheckProcessTool().execute() == get_active_scenario().server["process"]

    def test_s1_network(self) -> None:
        set_active_scenario("S1")
        from data.scenarios import get_active_scenario

        assert CheckNetworkTool().execute() == get_active_scenario().server["network"]

    def test_s2_disk_and_process_formats(self) -> None:
        set_active_scenario("S2")
        from data.scenarios import get_active_scenario

        assert CheckDiskTool().execute() == get_active_scenario().server["disk"]
        assert CheckProcessTool().execute() == "未发现异常进程"

    def test_s3_memory_only_process_format(self) -> None:
        set_active_scenario("S3")
        from data.scenarios import get_active_scenario

        assert CheckProcessTool().execute() == get_active_scenario().server["process"]
