"""P8 模型运行时模式切换 API 测试（不触发真实 LLM/网络）。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.services import RunApplicationService, SessionApplicationService
from src.infrastructure.persistence.database import Base, create_persistence_runtime

MASTER_MATERIAL = "test-secret-key-0123456789abcdef0123456789abcdef"
PLAINTEXT_VALUE = "sk-test-provider-secret-1234"


class _NoopExecutor:
    """模式测试不触发的确定性执行器占位。"""

    def stream(self, _query: str, _service_id: str | None = None):
        yield from ()
        return None


class _StubAssembler:
    """模式测试不触发的结果组装占位。"""

    def assemble(self, run: object, result: object) -> object:
        """模式测试不应触发 Run 完成。"""
        raise AssertionError("模式测试不应触发 Run 完成。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以临时 SQLite 与加密主密钥构建 v1 API 客户端。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)

    database_path = tmp_path / "mode-api.sqlite3"
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


def _put_mode(client: TestClient, mode: str) -> object:
    """切换模式并返回响应对象。"""
    return client.put("/api/v1/model/mode", json={"mode": mode})


def test_切换mock返回新模式并即时生效(api_client: TestClient) -> None:
    """未切换基线 mock，PUT mock 后 GET /model/config 应一致。"""
    before = api_client.get("/api/v1/model/config")
    assert before.json()["config"]["mode"] == "mock"

    response = _put_mode(api_client, "mock")
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["mode"] == "mock"
    assert config["mode_source"] == "runtime"

    after = api_client.get("/api/v1/model/config")
    assert after.json()["config"]["mode"] == "mock"


def test_切换到real返回新模式(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """env 有真实 Key 时 PUT real，GET /model/config 应返回 real。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")

    response = _put_mode(api_client, "real")
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["mode"] == "real"
    assert config["mode_source"] == "runtime"
    assert config["mode_available"] is True

    after = api_client.get("/api/v1/model/config")
    assert after.json()["config"]["mode"] == "real"


def test_real无可用Key时保存成功但如实标注不可用(api_client: TestClient) -> None:
    """env 为 mock 时 PUT real 应保存成功，但页面如实提示不可用。"""
    response = _put_mode(api_client, "real")
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["mode"] == "real"
    assert config["mode_source"] == "runtime"
    assert config["mode_available"] is False
    assert config["mode_unavailable_reason"] == "无可用 Provider/API Key"


def test_切换后GET与页面状态一致(api_client: TestClient) -> None:
    """PUT 返回值与随后 GET 的值必须一致，无前后端漂移。"""
    put_config = _put_mode(api_client, "mock").json()["config"]
    get_config = api_client.get("/api/v1/model/config").json()["config"]
    assert put_config == get_config


def test_非法模式字面量返回422(api_client: TestClient) -> None:
    """mode 非 mock/real 应返回 422。"""
    response = api_client.put("/api/v1/model/mode", json={"mode": "auto"})
    assert response.status_code == 422, response.text


def test_切换幂等重复设置返回相同结果(api_client: TestClient) -> None:
    """同值重复 PUT 应返回相同结果，无需 Idempotency-Key。"""
    first = _put_mode(api_client, "mock")
    second = _put_mode(api_client, "mock")
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["config"]["mode"] == second.json()["config"]["mode"] == "mock"


def test_切换接口不暴露凭据(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """请求/响应不得包含 API Key 明文、完整 DSN 或 sk- 内容。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")
    response = _put_mode(api_client, "real")
    assert response.status_code == 200
    assert PLAINTEXT_VALUE not in response.text
    assert "sk-real-key-1234567890abcdef" not in response.text
    assert "api_key" not in response.text
    assert "postgresql://" not in response.text


def test_持久化失败返回500且不产生半状态(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """应用库写失败时返回 500，且后续 GET 仍可读取（未产生半状态）。"""
    from sqlalchemy.exc import SQLAlchemyError

    monkeypatch.setattr(
        "src.infrastructure.persistence.app_settings_repository.SqlAlchemyAppSettingsRepository.set",
        lambda _self, _key, _value: (_ for _ in ()).throw(SQLAlchemyError("磁盘写失败")),
    )

    response = _put_mode(api_client, "real")
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "MODEL_MODE_PERSISTENCE_FAILED"

    after = api_client.get("/api/v1/model/config")
    assert after.status_code == 200
    assert after.json()["config"]["mode"] == "mock"
