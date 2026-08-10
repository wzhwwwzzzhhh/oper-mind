"""后端脚本的固定导入引导；不依赖调用时的当前工作目录。"""

from __future__ import annotations

import sys
from pathlib import Path


def bootstrap_import_paths() -> None:
    """将仓库根和后端根加入脚本运行时的导入路径。"""
    backend_root = Path(__file__).resolve().parents[1]
    project_root = backend_root.parent
    for path in (project_root, backend_root):
        value = str(path)
        if value not in sys.path:
            sys.path.insert(0, value)


bootstrap_import_paths()

