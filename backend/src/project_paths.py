"""项目根目录资源的唯一解析入口。"""

from __future__ import annotations

import sys
from pathlib import Path


BACKEND_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_ROOT.parent
CONFIG_DIR = PROJECT_ROOT / "config"
DATA_DIR = PROJECT_ROOT / "data"
EXPERIMENTS_DIR = PROJECT_ROOT / "experiments"


def ensure_project_import_paths() -> None:
    """确保后端包与根目录数据包均可按固定位置导入。"""
    for path in (PROJECT_ROOT, BACKEND_ROOT):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


ensure_project_import_paths()
