"""P8 模型参数配置 API 测试（不触发真实 LLM/网络）。"""

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
    """参数测试不触发的确定性执行器占位。"""

    def stream(self, _query: str, _service_id: str | None = None):
        yield from ()
        return None


class _StubAssembler:
    """参数测试不触发的结果组装占位。"""

    def assemble(self, run: object, result: object) -> object:
        """参数测试不应触发 Run 完成。"""
        raise AssertionError("参数测试不应触发 Run 完成。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以临时 SQLite 与加密主密钥构建 v1 API 客户端。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)

    database_path = tmp_path / "params-api.sqlite3"
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


def _params(client: TestClient) -> dict:
    """读取 GET /model/config 的已配置参数。"""
    return client.get("/api/v1/model/config").json()["config"]["params"]


def _defaults(client: TestClient) -> dict:
    """读取 GET /model/config 的参数默认值。"""
    return client.get("/api/v1/model/config").json()["config"]["params_defaults"]


def test_未配置时返回默认值并如实标注(api_client: TestClient) -> None:
    """AC2: 未配置参数时应返回后端默认值并如实标注。"""
    config = api_client.get("/api/v1/model/config").json()["config"]
    assert config["params"] == {"temperature": None, "max_tokens": None}
    assert config["params_defaults"] == {"temperature": 0.0, "max_tokens": None}


def test_保存参数后GET与PUT一致(api_client: TestClient) -> None:
    """AC1/AC5: 保存 temperature=0.5 后，配置展示应为 0.5（前后端一致）。"""
    response = api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
    assert response.status_code == 200, response.text
    put_params = response.json()["config"]["params"]
    assert put_params == {"temperature": 0.5, "max_tokens": 4096}
    assert _params(api_client) == put_params


def test_重启后参数保持(api_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """AC4: 参数持久化，重启后保持上次设置。"""
    api_client.put("/api/v1/model/params", json={"temperature": 0.7, "max_tokens": 2048})
    assert _params(api_client) == {"temperature": 0.7, "max_tokens": 2048}

    database_path = tmp_path / "params-api.sqlite3"
    runtime = create_persistence_runtime(f"sqlite:///{database_path.as_posix()}")
    services = V1Services(
        session_factory=runtime.session_factory,
        session_service=SessionApplicationService(runtime.session_factory),
        run_service=RunApplicationService(runtime.session_factory, _NoopExecutor(), _StubAssembler()),
    )

    from src import app as api_module

    monkeypatch.setattr(api_module.app.state, "v1_services", services)
    with TestClient(api_module.app, raise_server_exceptions=False) as client:
        assert _params(client) == {"temperature": 0.7, "max_tokens": 2048}
    runtime.engine.dispose()


def test_清除单项恢复默认(api_client: TestClient) -> None:
    """null=清除该项：只清 max_tokens，temperature 保留。"""
    api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
    response = api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": None})
    assert response.status_code == 200, response.text
    assert _params(api_client) == {"temperature": 0.5, "max_tokens": None}


def test_全部清除回到未配置(api_client: TestClient) -> None:
    """两项皆 null=清空全部，回到未配置默认。"""
    api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
    response = api_client.put("/api/v1/model/params", json={"temperature": None, "max_tokens": None})
    assert response.status_code == 200, response.text
    assert _params(api_client) == {"temperature": None, "max_tokens": None}


@pytest.mark.parametrize("payload", [
    {"temperature": 2.5},
    {"temperature": -0.1},
    {"max_tokens": 0},
    {"max_tokens": -5},
    {"max_tokens": 102401},
    {"max_tokens": 1.5},
    {"temperature": "热"},
])
def test_非法参数返回422(api_client: TestClient, payload: dict) -> None:
    """AC3: 参数非法（temperature 超范围 / max_tokens 非法）应拒绝保存。"""
    response = api_client.put("/api/v1/model/params", json=payload)
    assert response.status_code == 422, response.text
    assert _params(api_client) == {"temperature": None, "max_tokens": None}


@pytest.mark.parametrize("payload", [
    {"temperature": 0.0},
    {"temperature": 2.0},
    {"max_tokens": 1},
    {"max_tokens": 102400},
])
def test_边界值参数合法(api_client: TestClient, payload: dict) -> None:
    """temperature ∈ [0,2]、max_tokens ∈ [1,102400] 边界值应保存成功。"""
    response = api_client.put("/api/v1/model/params", json=payload)
    assert response.status_code == 200, response.text


def test_幂等重复设置返回相同结果(api_client: TestClient) -> None:
    """同值重复 PUT 应返回相同结果，无需 Idempotency-Key。"""
    first = api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
    second = api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["config"]["params"] == second.json()["config"]["params"]


def test_接口不暴露凭据(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC6: 参数接口响应不得包含 API Key 明文、完整 DSN 或 sk- 内容。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "sk-real-key-1234567890abcdef")
    response = api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
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

    response = api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
    assert response.status_code == 500, response.text
    assert response.json()["error"]["code"] == "MODEL_PARAMS_PERSISTENCE_FAILED"

    after = api_client.get("/api/v1/model/config")
    assert after.status_code == 200
    assert after.json()["config"]["params"] == {"temperature": None, "max_tokens": None}


def test_mock模式下参数保存成功且模式不变(api_client: TestClient) -> None:
    """AC8: mock 模式参数可保存，但模式与参数独立；mock 行为不变。"""
    response = api_client.put("/api/v1/model/params", json={"temperature": 0.5, "max_tokens": 4096})
    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["mode"] == "mock"
    assert config["params"] == {"temperature": 0.5, "max_tokens": 4096}
