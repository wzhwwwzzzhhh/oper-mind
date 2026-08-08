"""P6 模型 Provider 连接验证 Connector 测试（确定性 mock，不发真实请求）。"""

from __future__ import annotations

import httpx

from src.domain.model_provider import VerifyStatus
from src.infrastructure.model_provider_verify import verify_provider_connection


def _client(handler) -> httpx.Client:
    """用确定性 MockTransport 构建受控客户端。"""
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_验证成功返回OK() -> None:
    """200 应返回 ok，且只发最小只读请求到 /models。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        assert request.headers["Authorization"] == "Bearer sk-test-12345678"
        return httpx.Response(200, json={"data": []})

    outcome = verify_provider_connection("https://1.1.1.1/v1", "sk-test-12345678", client=_client(handler))

    assert outcome.status == VerifyStatus.OK
    assert outcome.error_code is None


def test_非200状态返回失败分类码() -> None:
    """401 应返回 HTTP_401 脱敏分类，不暴露响应体。"""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key: sk-test-secret"}})

    outcome = verify_provider_connection("https://1.1.1.1/v1", "bad-key", client=_client(handler))

    assert outcome.status == VerifyStatus.FAILED
    assert outcome.error_code == "HTTP_401"
    assert "invalid api key" not in str(outcome)


def test_超时返回TIMEOUT() -> None:
    """超时应返回 timeout 分类码。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout")

    outcome = verify_provider_connection("https://1.1.1.1/v1", "sk-test-12345678", client=_client(handler))

    assert outcome.status == VerifyStatus.TIMEOUT
    assert outcome.error_code == "TIMEOUT"


def test_连接失败返回CONNECTION_FAILED() -> None:
    """连接错误应返回脱敏的连接失败分类码。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    outcome = verify_provider_connection("https://1.1.1.1/v1", "sk-test-12345678", client=_client(handler))

    assert outcome.status == VerifyStatus.FAILED
    assert outcome.error_code == "CONNECTION_FAILED"


def test_私有地址被拒绝不发请求() -> None:
    """解析到私有地址应直接拒绝，不做任何 HTTP 请求。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("私有地址不应发出 HTTP 请求")

    outcome = verify_provider_connection("https://10.0.0.1/v1", "sk-test-12345678", client=_client(handler))

    assert outcome.status == VerifyStatus.FAILED
    assert outcome.error_code == "PRIVATE_ADDRESS_REJECTED"


def test_链路本地与保留地址被拒绝() -> None:
    """链路本地 / 保留地址段同样应被拒绝。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("保留地址不应发出 HTTP 请求")

    for base_url in ("https://169.254.1.1/v1", "https://192.168.1.1/v1", "https://0.0.0.0/v1"):
        outcome = verify_provider_connection(base_url, "sk-test-12345678", client=_client(handler))
        assert outcome.status == VerifyStatus.FAILED
        assert outcome.error_code == "PRIVATE_ADDRESS_REJECTED"


def test_localhost放行() -> None:
    """本地 Provider（如 Ollama）应被允许验证。"""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/models"
        return httpx.Response(200, json={"data": []})

    outcome = verify_provider_connection("http://localhost:11434/v1", "sk-test-12345678", client=_client(handler))

    assert outcome.status == VerifyStatus.OK


def test_无法解析主机返回DNS失败() -> None:
    """无法解析的主机应返回脱敏的 DNS 失败分类码，不做 HTTP 请求。"""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("无法解析的主机不应发出 HTTP 请求")

    outcome = verify_provider_connection("https://does-not-exist.invalid/v1", "sk-test-12345678", client=_client(handler))

    assert outcome.status == VerifyStatus.FAILED
    assert outcome.error_code == "DNS_RESOLUTION_FAILED"
