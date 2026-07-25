"""pytest 全局夹具 —— 保证模块级状态不在用例间残留。"""

import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pytest

from data.scenarios import clear_active_scenario


@pytest.fixture(autouse=True)
def _clear_active_scenario():
    """每条用例后清除激活场景。

    build_system(mock) 会把全局 `_active_scenario` 置为 S1，若不清理会污染
    后续依赖真实数据源（psutil）的用例。此处统一兜底，防止跨文件残留。
    """
    yield
    clear_active_scenario()
