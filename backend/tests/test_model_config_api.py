"""模型设置只读安全配置接口测试。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.services import RunApplicationService, SessionApplicationService
from src.infrastructure.persistence.database import Base, create_persistence_runtime


class _NoopExecutor:
    """配置接口测试不触发的确定性执行器占位。"""

    def stream(self, _query: str, _service_id: str | None = None):
        yield from ()
        return None


class _StubAssembler:
    """配置接口测试不触发的结果组装占位。"""

    def assemble(self, run: object, result: object) -> object:
        """配置接口测试不应触发 Run 完成。"""
        raise AssertionError("配置接口测试不应触发 Run 完成。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """使用确定性的 mock 模型配置与已迁移临时应用库隔离应用启动。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "https://mock.example/v1")
    monkeypatch.setenv("OPERMIND_MODEL", "diagnostic-model")

    database_path = tmp_path / "config-api.sqlite3"
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    Base.metadata.create_all(runtime.engine)
    services = V1Services(
        session_factory=runtime.session_factory,
        session_service=SessionApplicationService(runtime.session_factory),
        run_service=RunApplicationService(runtime.session_factory, _NoopExecutor(), _StubAssembler()),
    )
    monkeypatch.setenv("OPERMIND_APP_DATABASE_URL", f"sqlite:///{database_path.as_posix()}")

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client
    runtime.engine.dispose()


def test_模型配置接口返回安全的诊断配置且裁判恒未启用(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """接口应只暴露配置事实，不暴露 API Key 或完整 URL。

    独立裁判（judge_llm）已收口为未启用（issue #104）：即使设置 OPERMIND_JUDGE_*
    环境变量，`judge_model` 也恒为 None（字段结构保留，值表达未启用）。
    """
    monkeypatch.setenv("OPERMIND_JUDGE_API_KEY", "judge-secret")
    monkeypatch.setenv("OPERMIND_JUDGE_BASE_URL", "https://judge.example/v1")
    monkeypatch.setenv("OPERMIND_JUDGE_MODEL", "judge-model")

    response = api_client.get("/api/v1/model/config")

    assert response.status_code == 200
    body = response.json()
    assert body["config"] == {
        "mode": "mock",
        "mode_source": "env",
        "mode_available": True,
        "mode_unavailable_reason": None,
        "diagnostic_model": {
            "provider": "mock.example",
            "base_url_host": "mock.example",
            "model": "diagnostic-model",
            "status": "configured",
        },
        "judge_model": None,
        "params": {"temperature": None, "max_tokens": None},
        "params_defaults": {"temperature": 0.0, "max_tokens": None},
    }
    serialized = response.text
    assert "judge-secret" not in serialized
    assert "https://mock.example/v1" not in serialized
    assert "https://judge.example/v1" not in serialized
    assert "api_key" not in serialized
    assert "sk-" not in serialized


def test_模型配置接口如实返回_mock模式和裁判未启用(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mock 模式与裁判未启用都应有明确安全空态（judge_model 恒为 None）。"""
    monkeypatch.setenv("OPERMIND_JUDGE_API_KEY", "")
    monkeypatch.setenv("OPERMIND_JUDGE_BASE_URL", "")
    monkeypatch.setenv("OPERMIND_JUDGE_MODEL", "")

    response = api_client.get("/api/v1/model/config")

    assert response.status_code == 200
    assert response.json()["config"]["mode"] == "mock"
    assert response.json()["config"]["judge_model"] is None


def test_模型配置接口脱敏完整连接串中的凭据(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """URL 中的用户、密码、路径和查询参数均不可出现在安全视图。"""
    monkeypatch.setenv("OPERMIND_BASE_URL", "https://user:password@private.example/v1?token=secret")

    response = api_client.get("/api/v1/model/config")

    assert response.status_code == 200
    config = response.json()["config"]["diagnostic_model"]
    assert config["provider"] == "private.example"
    assert config["base_url_host"] == "private.example"
    assert "password" not in response.text
    assert "token=secret" not in response.text
    assert "private.example/v1" not in response.text


def test_诊断模型未配置时返回安全空态(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """诊断配置缺失时接口仍返回可展示的未配置状态。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "")
    monkeypatch.setenv("OPERMIND_BASE_URL", "")
    monkeypatch.setenv("OPERMIND_MODEL", "")

    response = api_client.get("/api/v1/model/config")

    assert response.status_code == 200
    assert response.json()["config"]["diagnostic_model"] == {
        "provider": "未配置",
        "base_url_host": "未配置",
        "model": "未配置",
        "status": "not_configured",
    }
