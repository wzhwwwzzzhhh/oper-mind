"""server_tools mock 路径回归锚点（P6 AC5）。

P6 不修改 `server_tools.py`；本文件锁定「mock 模式下各工具返回原场景预格式化串、
与改动前一致」，防止后续主机指标改造意外破坏 S1–S4 评测路径。
"""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import patch

from data.scenarios import clear_active_scenario, set_active_scenario

from src.core.tool_registry import ToolExecutionResult
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


def test_real模式缺少采集依赖返回unavailable而非固定指标() -> None:
    """真实环境缺 psutil 时显式不可用，不再返回貌似真实的固定 CPU 数值。"""
    clear_active_scenario()
    with patch.dict(sys.modules, {"psutil": None}):
        result = CheckCpuTool().execute()
    assert isinstance(result, ToolExecutionResult)
    assert result.status == "unavailable"
    assert "65%" not in result.output


def test_real模式采集失败返回unavailable且不泄露异常() -> None:
    """采集异常收敛为结构化不可用结果，不外泄底层异常文本。"""
    clear_active_scenario()

    def fail_cpu(_interval: int) -> float:
        raise RuntimeError("主机内部路径与异常明文")

    fake = SimpleNamespace(cpu_percent=fail_cpu)
    with patch.dict(sys.modules, {"psutil": fake}):
        result = CheckCpuTool().execute()
    assert isinstance(result, ToolExecutionResult)
    assert result.status == "unavailable"
    assert "主机内部路径" not in result.output
