"""P8 模型运行时模式解析测试（不触发真实 LLM/网络）。"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.application.model_mode import ModelModeApplicationService, resolve_runtime_mode
from src.application.model_providers import resolve_model_config
from src.infrastructure.persistence.database import Base

MASTER_MATERIAL = "test-secret-key-0123456789abcdef0123456789abcdef"


@pytest.fixture
def session_factory(monkeypatch: pytest.MonkeyPatch, tmp_path) -> sessionmaker:
    """以 mock env 与临时 SQLite 构建应用层会话工厂。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://env-base")
    monkeypatch.setenv("OPERMIND_MODEL", "env-model")
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)
    engine = create_engine(f"sqlite:///{tmp_path / 'mode.sqlite3'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def test_未切换模式时回退env决定(session_factory: sessionmaker) -> None:
    """从未显式切换时模式应来自 env（mock），来源标记为 env。"""
    resolution = resolve_runtime_mode(session_factory, None)
    assert resolution["mode"] == "mock"
    assert resolution["mode_source"] == "env"
    assert resolution["mode_available"] is True
    assert resolution["mode_unavailable_reason"] is None
    assert resolution["config"]["llm"]["api_key"] == "mock"


def test_未切换模式env真实Key时为real(session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """从未切换且 env 为真实 Key 时，模式应为 real 且可用。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")
    resolution = resolve_runtime_mode(session_factory, None)
    assert resolution["mode"] == "real"
    assert resolution["mode_source"] == "env"
    assert resolution["mode_available"] is True
    assert resolution["mode_unavailable_reason"] is None


def test_运行时切到mock覆盖env真实Key(session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """显式切到 mock 后，即使 env 有真实 Key 也应强制 mock。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")
    service = ModelModeApplicationService(session_factory)
    service.set_mode("mock")

    resolution = resolve_runtime_mode(session_factory, None)
    assert resolution["mode"] == "mock"
    assert resolution["mode_source"] == "runtime"
    assert resolution["mode_available"] is True
    # mock 模式下 LLM 构造点必须拿到 mock 场景 api_key
    assert resolution["config"]["llm"]["api_key"] == "mock"


def test_运行时切到real且env有Key时可用(session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """显式切到 real 且 env 有真实 Key 时，模式为 real 且可用。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")
    service = ModelModeApplicationService(session_factory)
    service.set_mode("real")

    resolution = resolve_runtime_mode(session_factory, None)
    assert resolution["mode"] == "real"
    assert resolution["mode_source"] == "runtime"
    assert resolution["mode_available"] is True
    assert resolution["config"]["llm"]["api_key"] == "sk-real-key-1234567890abcdef"


def test_运行时切到real但无可用Key时诚实降级(session_factory: sessionmaker) -> None:
    """real 模式但无可用 Key（env mock）时，保存成功但如实标注不可用。"""
    service = ModelModeApplicationService(session_factory)
    service.set_mode("real")

    resolution = resolve_runtime_mode(session_factory, None)
    assert resolution["mode"] == "real"
    assert resolution["mode_source"] == "runtime"
    assert resolution["mode_available"] is False
    assert resolution["mode_unavailable_reason"] == "无可用 Provider/API Key"
    # 会话链路诚实降级：config 仍是 mock，build_llm_from_config 走 mock 场景
    assert resolution["config"]["llm"]["api_key"] == "mock"


def test_切换后重启保持(session_factory: sessionmaker) -> None:
    """模式切换是持久化操作：新会话工厂读取仍保持上次设置。"""
    ModelModeApplicationService(session_factory).set_mode("real")
    resolution = resolve_runtime_mode(session_factory, None)
    assert resolution["mode"] == "real"
    assert resolution["mode_source"] == "runtime"


def test_应用库不可用时回退env并诚实标注(session_factory: sessionmaker) -> None:
    """应用库不可用/未迁移时解析层不抛错，回退 env 并标注降级原因。"""
    broken_factory = sessionmaker(bind=create_engine("sqlite://"))
    resolution = resolve_runtime_mode(broken_factory, None)
    assert resolution["mode"] == "mock"
    assert resolution["mode_source"] == "env"
    assert resolution["mode_unavailable_reason"] == "应用库不可用，回退环境变量决定"


def test_模式切换不影响Provider生效配置解析(session_factory: sessionmaker) -> None:
    """模式与 DB 激活 Provider 相互独立：切到 mock 不改变 resolve_model_config 的 Provider 解析。"""
    ModelModeApplicationService(session_factory).set_mode("mock")
    config = resolve_model_config(session_factory, None)
    assert config["llm"]["api_key"] == "mock"
    assert config["llm"]["base_url"] == "http://env-base"


def test_会话链路按生效模式构造LLM(session_factory: sessionmaker, monkeypatch: pytest.MonkeyPatch) -> None:
    """会话链路（coordinator factory 等价路径）应消费 resolve_runtime_mode 的 config 构造 LLM。"""
    from data.scenarios import get_active_scenario
    from src.core.bootstrap import build_llm_from_config

    # env 有真实 Key，但显式切到 mock → LLM 必须走 mock 场景
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")
    ModelModeApplicationService(session_factory).set_mode("mock")
    resolution = resolve_runtime_mode(session_factory, None)
    llm = build_llm_from_config(resolution["config"])
    assert llm.client.api_key == "mock"
    assert get_active_scenario() is not None

    # 切到 real 且 env 有 Key → LLM 必须拿到真实 Key，清除 mock 场景
    ModelModeApplicationService(session_factory).set_mode("real")
    resolution = resolve_runtime_mode(session_factory, None)
    llm = build_llm_from_config(resolution["config"])
    assert llm.client.api_key == "sk-real-key-1234567890abcdef"
    assert get_active_scenario() is None
