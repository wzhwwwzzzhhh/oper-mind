"""pytest 导入引导与全局状态隔离。"""

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
for path in (PROJECT_ROOT, BACKEND_ROOT):
    value = str(path)
    if value not in sys.path:
        sys.path.insert(0, value)

import pytest

from data.scenarios import clear_active_scenario
from src.project_paths import ensure_project_import_paths

ensure_project_import_paths()


@pytest.fixture(autouse=True)
def _clear_active_scenario():
    """每条用例后清除激活场景，避免模块级状态跨用例残留。"""
    yield
    clear_active_scenario()