"""订单慢 SQL 靶场服务的配置边界测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SERVICE_FILE = (
    PROJECT_ROOT
    / "demo"
    / "orders-slow-query"
    / "order-service"
    / "app"
    / "main.py"
)


def load_order_service(monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """在固定安全环境变量下加载订单服务模块，不连接数据库。"""
    runtime_logs = (
        PROJECT_ROOT / "demo" / "orders-slow-query" / "runtime" / "logs"
    )
    monkeypatch.setenv("OPERMIND_DEMO_PG_HOST", "127.0.0.1")
    monkeypatch.setenv("OPERMIND_DEMO_PG_PORT", "5433")
    monkeypatch.setenv("OPERMIND_DEMO_PG_DATABASE", "opermind_demo")
    monkeypatch.setenv("OPERMIND_DEMO_PG_USER", "demo_user")
    monkeypatch.setenv("OPERMIND_DEMO_PG_PASSWORD", "demo_password")
    monkeypatch.setenv(
        "OPERMIND_DEMO_ORDER_LOG_PATH",
        str(runtime_logs / "settings-test.jsonl"),
    )

    module_name = "opermind_demo_order_service_settings_test"
    spec = importlib.util.spec_from_file_location(module_name, SERVICE_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError("无法加载订单靶场服务模块。")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    finally:
        sys.modules.pop(module_name, None)
    return module


def test_订单服务可构造受控配置(monkeypatch: pytest.MonkeyPatch) -> None:
    """服务初始化必须得到非空的固定目标配置。"""
    service = load_order_service(monkeypatch)

    assert service.SETTINGS.host == "127.0.0.1"
    assert service.SETTINGS.port == 5433
    assert service.SETTINGS.database == "opermind_demo"
    assert service.SETTINGS.log_path.parent == service.ALLOWED_LOG_DIRECTORY


def test_订单服务拒绝靶场外日志路径(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """日志文件不能借由环境变量逃逸到靶场 runtime 之外。"""
    service = load_order_service(monkeypatch)
    monkeypatch.setenv("OPERMIND_DEMO_ORDER_LOG_PATH", str(tmp_path / "outside.jsonl"))

    with pytest.raises(RuntimeError, match="runtime/logs"):
        service.ServiceSettings.from_environment()