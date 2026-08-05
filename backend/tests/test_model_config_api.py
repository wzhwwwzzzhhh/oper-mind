"""模型设置只读安全配置接口测试。"""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    """使用确定性的 mock 模型配置隔离应用启动。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "https://mock.example/v1")
    monkeypatch.setenv("OPERMIND_MODEL", "diagnostic-model")

    from src import app as api_module

    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        yield client


def test_模型配置接口返回安全的诊断和裁判配置(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """接口应只暴露配置事实，不暴露 API Key 或完整 URL。"""
    monkeypatch.setenv("OPERMIND_JUDGE_API_KEY", "judge-secret")
    monkeypatch.setenv("OPERMIND_JUDGE_BASE_URL", "https://judge.example/v1")
    monkeypatch.setenv("OPERMIND_JUDGE_MODEL", "judge-model")

    response = api_client.get("/api/v1/model/config")

    assert response.status_code == 200
    body = response.json()
    assert body["config"] == {
        "mode": "mock",
        "diagnostic_model": {
            "provider": "mock.example",
            "base_url_host": "mock.example",
            "model": "diagnostic-model",
            "status": "configured",
        },
        "judge_model": {
            "provider": "judge.example",
            "base_url_host": "judge.example",
            "model": "judge-model",
            "status": "configured",
        },
    }
    serialized = response.text
    assert "judge-secret" not in serialized
    assert "https://mock.example/v1" not in serialized
    assert "https://judge.example/v1" not in serialized
    assert "api_key" not in serialized
    assert "sk-" not in serialized


def test_模型配置接口如实返回_mock模式和未配置裁判模型(
    api_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mock 模式和缺少裁判配置都应有明确安全空态。"""
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
    assert "token" not in response.text
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
