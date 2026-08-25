"""P6 模型 Provider 配置与 API Key 加密 API 测试。"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from src.api.v1.dependencies import V1Services
from src.application.services import RunApplicationService, SessionApplicationService
from src.infrastructure.persistence.database import Base, create_persistence_runtime

MASTER_MATERIAL = "test-secret-key-0123456789abcdef0123456789abcdef"
PLAINTEXT_VALUE = "sk-test-provider-secret-1234"
REPLACEMENT_VALUE = "sk-replacement-secret-5678"


class _NoopExecutor:
    """Provider 测试不触发的确定性执行器占位。"""

    def stream(self, _query: str, _service_id: str | None = None):
        yield from ()
        return None


class _StubAssembler:
    """Provider 测试不触发的结果组装占位。"""

    def assemble(self, run: object, result: object) -> object:
        """Provider 测试不应触发 Run 完成。"""
        raise AssertionError("Provider 测试不应触发 Run 完成。")


@pytest.fixture
def api_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[TestClient]:
    """以临时 SQLite 与加密主密钥构建 v1 API 客户端。"""
    monkeypatch.setenv("OPERMIND_API_KEY", "mock")
    monkeypatch.setenv("OPERMIND_BASE_URL", "http://mock")
    monkeypatch.setenv("OPERMIND_MODEL", "mock")
    monkeypatch.setenv("OPERMIND_SECRET_KEY", MASTER_MATERIAL)

    database_path = tmp_path / "provider-api.sqlite3"
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


def _idempotent_headers() -> dict[str, str]:
    """为每个创建请求生成独立 UUID 幂等键。"""
    return {"Idempotency-Key": str(uuid4())}


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
    }
    payload.update(overrides)
    return payload


def _create_provider(client: TestClient, **overrides: object) -> dict[str, object]:
    response = client.post("/api/v1/model/providers", json=_payload(**overrides), headers=_idempotent_headers())
    assert response.status_code == 201, response.text
    return response.json()["provider"]


def test_创建Provider保存APIKey并掩码展示(api_client: TestClient) -> None:
    """创建带 API Key 的 Provider：掩码展示、响应无明文。"""
    response = api_client.post(
        "/api/v1/model/providers",
        json=_payload(api_key=PLAINTEXT_VALUE),
        headers=_idempotent_headers(),
    )

    assert response.status_code == 201, response.text
    provider = response.json()["provider"]
    assert provider["has_api_key"] is True
    assert provider["masked_tail"] == PLAINTEXT_VALUE[-4:]
    assert PLAINTEXT_VALUE not in response.text
    assert "api_key_encrypted" not in response.text


def test_创建无Key的Provider诚实空态(api_client: TestClient) -> None:
    """不带 API Key 创建 Provider：has_api_key 为 False。"""
    provider = _create_provider(api_client)

    assert provider["has_api_key"] is False
    assert provider["masked_tail"] is None
    assert provider["verify_status"] == "unknown"


def test_主密钥未配置时保存Key被拒绝(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """未配置 OPERMIND_SECRET_KEY 时禁止保存 API Key，但允许保存元数据。"""
    monkeypatch.delenv("OPERMIND_SECRET_KEY", raising=False)

    rejected = api_client.post(
        "/api/v1/model/providers",
        json=_payload(api_key=PLAINTEXT_VALUE),
        headers=_idempotent_headers(),
    )
    assert rejected.status_code == 409, rejected.text
    assert rejected.json()["error"]["code"] == "SECRET_KEY_NOT_CONFIGURED"

    allowed = api_client.post(
        "/api/v1/model/providers",
        json=_payload(),
        headers=_idempotent_headers(),
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["provider"]["has_api_key"] is False


def test_读取列表不泄露明文(api_client: TestClient) -> None:
    """创建后读取列表，任何响应字段都不得含明文 Key。"""
    _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.get("/api/v1/model/providers")

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    assert body["items"][0]["masked_tail"] == PLAINTEXT_VALUE[-4:]
    assert PLAINTEXT_VALUE not in response.text
    assert "api_key_encrypted" not in response.text


def test_编辑Provider更新名称并重加密(api_client: TestClient) -> None:
    """PUT 应更新名称并在提供新 Key 时重新加密。"""
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    updated = api_client.put(
        f"/api/v1/model/providers/{provider['id']}",
        json=_payload(name="DeepSeek 备用", api_key=REPLACEMENT_VALUE),
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()["provider"]
    assert body["name"] == "DeepSeek 备用"
    assert body["has_api_key"] is True
    assert body["masked_tail"] == REPLACEMENT_VALUE[-4:]
    assert PLAINTEXT_VALUE not in updated.text
    assert REPLACEMENT_VALUE not in updated.text


def test_编辑Provider显式空串清空Key(api_client: TestClient) -> None:
    """api_key 传空串应清空已存 Key。"""
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    cleared = api_client.put(f"/api/v1/model/providers/{provider['id']}", json=_payload(api_key=""))
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["provider"]["has_api_key"] is False


def test_编辑Provider不传Key保留原Key(api_client: TestClient) -> None:
    """api_key 不传应保留已存 Key。"""
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    kept = api_client.put(f"/api/v1/model/providers/{provider['id']}", json=_payload())
    assert kept.status_code == 200, kept.text
    assert kept.json()["provider"]["has_api_key"] is True
    assert kept.json()["provider"]["masked_tail"] == PLAINTEXT_VALUE[-4:]


def test_编辑Provider后重置验证状态(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """编辑 Provider（改 Base URL / Key / 名称）后应重置验证状态，避免展示过期结果。"""
    _stub_verify(monkeypatch, "ok")
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)
    verified = api_client.post(f"/api/v1/model/providers/{provider['id']}/verify")
    assert verified.json()["provider"]["verify_status"] == "ok"

    updated = api_client.put(f"/api/v1/model/providers/{provider['id']}", json=_payload(name="改名"))
    assert updated.status_code == 200, updated.text
    body = updated.json()["provider"]
    assert body["verify_status"] == "unknown"
    assert body["last_verified_at"] is None
    assert body["verify_error_code"] is None


def test_激活Provider单事务原子替换(api_client: TestClient) -> None:
    """同端点激活应只保留最新 Provider。"""
    first = _create_provider(api_client, name="第一")
    second = _create_provider(api_client, name="第二")

    activate_first = api_client.post(
        f"/api/v1/model/providers/{first['id']}/activate",
        json={"endpoint": "diagnostic"},
    )
    assert activate_first.status_code == 200, activate_first.text
    assert activate_first.json()["provider"]["active_endpoint"] == "diagnostic"

    activate_second = api_client.post(
        f"/api/v1/model/providers/{second['id']}/activate",
        json={"endpoint": "diagnostic"},
    )
    assert activate_second.status_code == 200, activate_second.text

    items = api_client.get("/api/v1/model/providers").json()["items"]
    by_id = {item["id"]: item for item in items}
    assert by_id[first["id"]]["active_endpoint"] is None
    assert by_id[second["id"]]["active_endpoint"] == "diagnostic"


def test_删除Provider后列表为空(api_client: TestClient) -> None:
    """DELETE 应删除 Provider。"""
    provider = _create_provider(api_client)

    deleted = api_client.delete(f"/api/v1/model/providers/{provider['id']}")
    assert deleted.status_code == 204

    assert api_client.get("/api/v1/model/providers").json()["items"] == []


def test_幂等键同载荷重放(api_client: TestClient) -> None:
    """同幂等键同载荷应重放同一 Provider，不产生重复。"""
    headers = _idempotent_headers()

    first = api_client.post("/api/v1/model/providers", json=_payload(api_key=PLAINTEXT_VALUE), headers=headers)
    second = api_client.post("/api/v1/model/providers", json=_payload(api_key=PLAINTEXT_VALUE), headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["provider"]["id"] == second.json()["provider"]["id"]
    assert len(api_client.get("/api/v1/model/providers").json()["items"]) == 1


def test_幂等键不同载荷冲突(api_client: TestClient) -> None:
    """同幂等键不同载荷应返回 409 冲突。"""
    headers = _idempotent_headers()

    first = api_client.post("/api/v1/model/providers", json=_payload(name="A"), headers=headers)
    second = api_client.post("/api/v1/model/providers", json=_payload(name="B"), headers=headers)

    assert first.status_code == 201, first.text
    assert second.status_code == 409, second.text
    assert second.json()["error"]["code"] == "PROVIDER_IDEMPOTENCY_REUSED"


def test_创建时校验BaseURL防SSRF(api_client: TestClient) -> None:
    """私有地址段与非 https 应被拒绝，localhost 放行。"""
    private = api_client.post(
        "/api/v1/model/providers",
        json=_payload(base_url="https://192.168.1.1/v1"),
        headers=_idempotent_headers(),
    )
    assert private.status_code == 422, private.text

    http_public = api_client.post(
        "/api/v1/model/providers",
        json=_payload(base_url="http://api.example.com/v1"),
        headers=_idempotent_headers(),
    )
    assert http_public.status_code == 422, http_public.text

    localhost = api_client.post(
        "/api/v1/model/providers",
        json=_payload(base_url="http://localhost:11434/v1"),
        headers=_idempotent_headers(),
    )
    assert localhost.status_code == 201, localhost.text


def test_创建时校验APIKey最小长度(api_client: TestClient) -> None:
    """过短的 API Key 应被拒绝，避免掩码规则完整暴露。"""
    response = api_client.post(
        "/api/v1/model/providers",
        json=_payload(api_key="short"),
        headers=_idempotent_headers(),
    )
    assert response.status_code == 422, response.text


def test_操作不存在Provider返回404(api_client: TestClient) -> None:
    """对不存在的 Provider 更新/激活/删除应返回 404。"""
    missing = str(uuid4())

    assert api_client.put(f"/api/v1/model/providers/{missing}", json=_payload()).status_code == 404
    assert (
        api_client.post(
            f"/api/v1/model/providers/{missing}/activate",
            json={"endpoint": "diagnostic"},
        ).status_code
        == 404
    )
    assert api_client.delete(f"/api/v1/model/providers/{missing}").status_code == 404


def test_激活judge端点被拒绝(api_client: TestClient) -> None:
    """独立裁判端点已收口为未启用（issue #104）：激活 judge 应返回 400 而非生效。"""
    provider = _create_provider(api_client)

    response = api_client.post(
        f"/api/v1/model/providers/{provider['id']}/activate",
        json={"endpoint": "judge"},
    )

    assert response.status_code == 400, response.text
    body = response.json()
    assert body["error"]["code"] == "JUDGE_ENDPOINT_NOT_ENABLED"
    assert "未启用" in body["error"]["message"]


def test_未提供幂等键创建被拒绝(api_client: TestClient) -> None:
    """创建 Provider 必须携带 Idempotency-Key。"""
    response = api_client.post("/api/v1/model/providers", json=_payload())
    assert response.status_code == 422, response.text


def test_创建返回的ProviderID为UUID(api_client: TestClient) -> None:
    """创建返回的 id 应为合法 UUID。"""
    provider = _create_provider(api_client)
    UUID(provider["id"])


def _stub_verify(monkeypatch: pytest.MonkeyPatch, status: str, error_code: str | None = None) -> None:
    """以确定性结果替换真实连接验证，避免测试发真实请求。"""
    from src.domain.model_provider import VerifyStatus
    from src.infrastructure.model_provider_verify import ProviderVerifyOutcome

    monkeypatch.setattr(
        "src.application.model_providers.verify_provider_connection",
        lambda _base_url, _api_key: ProviderVerifyOutcome(status=VerifyStatus(status), error_code=error_code),
    )


def test_验证成功更新为ok(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider 可连通时 verify_status 应更新为 ok。"""
    _stub_verify(monkeypatch, "ok")
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.post(f"/api/v1/model/providers/{provider['id']}/verify")

    assert response.status_code == 200, response.text
    body = response.json()["provider"]
    assert body["verify_status"] == "ok"
    assert body["last_verified_at"] is not None
    assert PLAINTEXT_VALUE not in response.text


def test_验证失败返回脱敏状态(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider 失败时 verify_status 应更新为 failed 并带脱敏分类码。"""
    _stub_verify(monkeypatch, "failed", error_code="HTTP_401")
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.post(f"/api/v1/model/providers/{provider['id']}/verify")

    assert response.status_code == 200, response.text
    body = response.json()["provider"]
    assert body["verify_status"] == "failed"
    assert body["verify_error_code"] == "HTTP_401"


def test_验证超时更新为timeout(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider 超时时 verify_status 应更新为 timeout。"""
    _stub_verify(monkeypatch, "timeout", error_code="TIMEOUT")
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.post(f"/api/v1/model/providers/{provider['id']}/verify")

    assert response.status_code == 200, response.text
    assert response.json()["provider"]["verify_status"] == "timeout"


def test_无Key的Provider验证诚实失败(api_client: TestClient) -> None:
    """未配置 API Key 的 Provider 无法验证连通，应诚实标记失败。"""
    provider = _create_provider(api_client)

    response = api_client.post(f"/api/v1/model/providers/{provider['id']}/verify")

    assert response.status_code == 200, response.text
    body = response.json()["provider"]
    assert body["verify_status"] == "failed"
    assert body["verify_error_code"] == "NO_API_KEY"


def test_主密钥缺失时验证诚实失败(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """主密钥缺失时无法解密 Key，应诚实标记失败而不泄露。"""
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)
    monkeypatch.delenv("OPERMIND_SECRET_KEY", raising=False)

    response = api_client.post(f"/api/v1/model/providers/{provider['id']}/verify")

    assert response.status_code == 200, response.text
    body = response.json()["provider"]
    assert body["verify_status"] == "failed"
    assert body["verify_error_code"] == "SECRET_KEY_NOT_CONFIGURED"


def test_验证不存在的Provider返回404(api_client: TestClient) -> None:
    """验证不存在的 Provider 应返回 404。"""
    response = api_client.post(f"/api/v1/model/providers/{uuid4()}/verify")
    assert response.status_code == 404, response.text


def test_激活Provider后生效配置反映DB(api_client: TestClient) -> None:
    """激活带 Key 的 Provider 后，GET /model/config 应反映 DB 生效配置且无明文。"""
    provider = _create_provider(
        api_client,
        name="生效 Provider",
        base_url="https://api.deepseek.com/v1",
        model="deepseek-chat",
        api_key=PLAINTEXT_VALUE,
    )
    activated = api_client.post(
        f"/api/v1/model/providers/{provider['id']}/activate",
        json={"endpoint": "diagnostic"},
    )
    assert activated.status_code == 200, activated.text

    response = api_client.get("/api/v1/model/config")

    assert response.status_code == 200, response.text
    config = response.json()["config"]
    assert config["mode"] == "real"
    assert config["diagnostic_model"]["model"] == "deepseek-chat"
    assert config["diagnostic_model"]["provider"] == "api.deepseek.com"
    assert PLAINTEXT_VALUE not in response.text


def test_未激活Provider时配置回退env(api_client: TestClient) -> None:
    """无激活 Provider 时 GET /model/config 应展示 env/YAML 生效配置。"""
    response = api_client.get("/api/v1/model/config")

    assert response.status_code == 200, response.text
    config = response.json()["config"]
    # fixture 设置 env mock → mode mock
    assert config["mode"] == "mock"


def _stub_list_models(
    monkeypatch: pytest.MonkeyPatch, status: str, models: list[str] | None = None, error_code: str | None = None
) -> None:
    """以确定性结果替换模型枚举，避免测试发真实请求。"""
    from src.domain.model_provider import VerifyStatus
    from src.infrastructure.model_provider_verify import ProviderModelsOutcome

    monkeypatch.setattr(
        "src.application.model_providers.fetch_provider_models",
        lambda _base_url, _api_key: ProviderModelsOutcome(
            status=VerifyStatus(status), models=models, error_code=error_code
        ),
    )


def test_枚举成功返回模型列表(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Provider 可连通时枚举应返回可用模型名列表（AC1）。"""
    _stub_list_models(monkeypatch, "ok", models=["deepseek-chat", "deepseek-reasoner"])
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.get(f"/api/v1/model/providers/{provider['id']}/models")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["provider_id"] == provider["id"]
    assert body["status"] == "ok"
    assert body["models"] == ["deepseek-chat", "deepseek-reasoner"]
    assert body["error_code"] is None


def test_枚举失败返回脱敏状态不暴露响应体(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """枚举失败应返回脱敏状态码，不暴露响应体或凭据（AC2/AC4）。"""
    _stub_list_models(monkeypatch, "failed", error_code="HTTP_401")
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.get(f"/api/v1/model/providers/{provider['id']}/models")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["models"] is None
    assert body["error_code"] == "HTTP_401"
    assert PLAINTEXT_VALUE not in response.text


def test_枚举超时返回timeout(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """枚举超时应返回 timeout 状态（AC6）。"""
    _stub_list_models(monkeypatch, "timeout", error_code="TIMEOUT")
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.get(f"/api/v1/model/providers/{provider['id']}/models")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "timeout"
    assert body["error_code"] == "TIMEOUT"


def test_枚举无Key的Provider诚实失败(api_client: TestClient) -> None:
    """未配置 API Key 的 Provider 无法枚举，应诚实标记失败（AC3）。"""
    provider = _create_provider(api_client)

    response = api_client.get(f"/api/v1/model/providers/{provider['id']}/models")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_code"] == "NO_API_KEY"


def test_枚举主密钥缺失诚实失败(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """主密钥缺失时无法解密 Key，应诚实标记失败。"""
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)
    monkeypatch.delenv("OPERMIND_SECRET_KEY", raising=False)

    response = api_client.get(f"/api/v1/model/providers/{provider['id']}/models")

    assert response.status_code == 200, response.text
    assert response.json()["error_code"] == "SECRET_KEY_NOT_CONFIGURED"


def test_枚举不存在的Provider返回404(api_client: TestClient) -> None:
    """枚举不存在的 Provider 应返回 404。"""
    response = api_client.get(f"/api/v1/model/providers/{uuid4()}/models")
    assert response.status_code == 404, response.text


def test_枚举为无副作用只读探测(api_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """枚举不应改动 verify_status（Design：无副作用、不落库）。"""
    _stub_list_models(monkeypatch, "ok", models=["deepseek-chat"])
    provider = _create_provider(api_client, api_key=PLAINTEXT_VALUE)

    response = api_client.get(f"/api/v1/model/providers/{provider['id']}/models")

    assert response.json()["status"] == "ok"
    listed = api_client.get("/api/v1/model/providers").json()["items"][0]
    assert listed["verify_status"] == "unknown"
    assert listed["last_verified_at"] is None


def test_存量judge激活Provider公开投影为未启用() -> None:
    """存量 judge 激活行保留，但公开投影值收口为 null（issue #104，Design D7）。"""
    from src.api.v1.resources import provider_resource
    from src.domain.model_provider import ModelProviderData, ProviderEndpoint, VerifyStatus

    legacy = ModelProviderData(
        id=uuid4(),
        name="Legacy Judge",
        base_url="https://api.example.com/v1",
        model="judge-model",
        active_endpoint=ProviderEndpoint.JUDGE,
        verify_status=VerifyStatus.UNKNOWN,
    )
    resource = provider_resource(legacy)

    assert resource.active_endpoint is None

    diagnostic = ModelProviderData(
        id=uuid4(),
        name="Diagnostic",
        base_url="https://api.example.com/v1",
        model="diag-model",
        active_endpoint=ProviderEndpoint.DIAGNOSTIC,
        verify_status=VerifyStatus.UNKNOWN,
    )
    assert provider_resource(diagnostic).active_endpoint == "diagnostic"
