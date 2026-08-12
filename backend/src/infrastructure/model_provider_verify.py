"""P6/P8 模型 Provider 连接验证与模型枚举的确定性受控 Connector。

只发最小只读请求（OpenAI-compatible ``GET /models``），限时、脱敏、防 SSRF：
- 非 localhost 主机在连接前解析并校验，拒绝解析到私有 / 链路本地 / 保留地址段的 IP。
- 失败只返回脱敏分类码（如 ``TIMEOUT`` / ``CONNECTION_FAILED`` / ``HTTP_401``），绝不暴露响应体或凭据。
- ``fetch_provider_models`` 在成功响应上解析模型名列表（限长、去重、限项），响应体不落任何存储。
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from src.domain.model_provider import VerifyStatus

VERIFY_TIMEOUT_SECONDS = 5.0
MAX_MODELS = 100
MAX_MODEL_NAME_LENGTH = 200
MAX_RESPONSE_BYTES = 1024 * 1024
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class ProviderVerifyOutcome:
    """连接验证的脱敏结果。"""

    status: VerifyStatus
    error_code: str | None = None


@dataclass(frozen=True)
class ProviderModelsOutcome:
    """模型枚举的脱敏结果；成功时带模型名列表。"""

    status: VerifyStatus
    models: list[str] | None = None
    error_code: str | None = None


@dataclass(frozen=True)
class _ProviderRequestResult:
    """受控请求结果：状态分类 + 成功时的响应（供枚举解析）。"""

    status: VerifyStatus
    response: httpx.Response | None
    error_code: str | None = None


def verify_provider_connection(
    base_url: str,
    api_key: str,
    *,
    client: httpx.Client | None = None,
    timeout_seconds: float = VERIFY_TIMEOUT_SECONDS,
) -> ProviderVerifyOutcome:
    """受控、限时验证 Provider 连通；只发最小只读请求，失败返回脱敏分类码。"""
    result = _request_provider_models(base_url, api_key, client=client, timeout_seconds=timeout_seconds)
    return ProviderVerifyOutcome(status=result.status, error_code=result.error_code)


def fetch_provider_models(
    base_url: str,
    api_key: str,
    *,
    client: httpx.Client | None = None,
    timeout_seconds: float = VERIFY_TIMEOUT_SECONDS,
) -> ProviderModelsOutcome:
    """受控、限时枚举 Provider 可用模型名；成功解析 ``data[].id``，失败返回脱敏分类码。"""
    result = _request_provider_models(base_url, api_key, client=client, timeout_seconds=timeout_seconds)
    if result.response is None:
        return ProviderModelsOutcome(status=result.status, models=None, error_code=result.error_code)
    models = _parse_model_names(result.response)
    if models is None:
        return ProviderModelsOutcome(status=VerifyStatus.FAILED, models=None, error_code="MODELS_PARSE_FAILED")
    return ProviderModelsOutcome(status=VerifyStatus.OK, models=models, error_code=None)


def _request_provider_models(
    base_url: str,
    api_key: str,
    *,
    client: httpx.Client | None,
    timeout_seconds: float,
) -> _ProviderRequestResult:
    """对 Provider 发起受控只读 ``GET /models``；先校验主机，失败返回脱敏分类。"""
    host = (urlparse(base_url).hostname or "").rstrip(".").lower()
    host_error = _check_host_allowed(host)
    if host_error is not None:
        return _ProviderRequestResult(status=VerifyStatus.FAILED, response=None, error_code=host_error)

    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    owns_client = client is None
    request_client = client if client is not None else httpx.Client(timeout=timeout_seconds)
    try:
        response = request_client.get(url, headers=headers)
    except httpx.TimeoutException:
        return _ProviderRequestResult(status=VerifyStatus.TIMEOUT, response=None, error_code="TIMEOUT")
    except httpx.HTTPError:
        return _ProviderRequestResult(status=VerifyStatus.FAILED, response=None, error_code="CONNECTION_FAILED")
    finally:
        if owns_client:
            request_client.close()

    if response.status_code == 200:
        return _ProviderRequestResult(status=VerifyStatus.OK, response=response, error_code=None)
    return _ProviderRequestResult(status=VerifyStatus.FAILED, response=None, error_code=f"HTTP_{response.status_code}")


def _parse_model_names(response: httpx.Response) -> list[str] | None:
    """从 OpenAI-compatible 响应 ``data[].id`` 解析模型名；去重保序、限长限项。

    返回 None 表示响应结构非预期或超出大小上限（诚实失败，不伪造列表）；
    ``data`` 为空列表是合法空结果。
    """
    if len(response.content) > MAX_RESPONSE_BYTES:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        return None
    names: list[str] = []
    seen: set[str] = set()
    for entry in payload["data"]:
        if len(names) >= MAX_MODELS:
            break
        if not isinstance(entry, dict):
            continue
        name = entry.get("id")
        if not isinstance(name, str) or not name or len(name) > MAX_MODEL_NAME_LENGTH or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _check_host_allowed(host: str) -> str | None:
    """校验目标主机；返回错误分类码，或 None 表示允许。"""
    if host in _LOCAL_HOSTS:
        return None
    if not host:
        return "INVALID_URL"
    try:
        addresses = socket.getaddrinfo(host, None)
    except OSError:
        return "DNS_RESOLUTION_FAILED"
    if not addresses:
        return "DNS_RESOLUTION_FAILED"
    for address in addresses:
        try:
            ip = ipaddress.ip_address(address[4][0])
        except ValueError:
            continue
        if not ip.is_global:
            return "PRIVATE_ADDRESS_REJECTED"
    return None
