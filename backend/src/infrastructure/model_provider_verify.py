"""P6 模型 Provider 连接验证的确定性受控 Connector。

只发最小只读请求（OpenAI-compatible ``GET /models``），限时、脱敏、防 SSRF：
- 非 localhost 主机在连接前解析并校验，拒绝解析到私有 / 链路本地 / 保留地址段的 IP。
- 失败只返回脱敏分类码（如 ``TIMEOUT`` / ``CONNECTION_FAILED`` / ``HTTP_401``），绝不暴露响应体或凭据。
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from src.domain.model_provider import VerifyStatus

VERIFY_TIMEOUT_SECONDS = 5.0
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


@dataclass(frozen=True)
class ProviderVerifyOutcome:
    """连接验证的脱敏结果。"""

    status: VerifyStatus
    error_code: str | None = None


def verify_provider_connection(
    base_url: str,
    api_key: str,
    *,
    client: httpx.Client | None = None,
    timeout_seconds: float = VERIFY_TIMEOUT_SECONDS,
) -> ProviderVerifyOutcome:
    """受控、限时验证 Provider 连通；只发最小只读请求，失败返回脱敏分类码。"""
    host = (urlparse(base_url).hostname or "").rstrip(".").lower()
    host_error = _check_host_allowed(host)
    if host_error is not None:
        return ProviderVerifyOutcome(status=VerifyStatus.FAILED, error_code=host_error)

    url = f"{base_url.rstrip('/')}/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    owns_client = client is None
    request_client = client if client is not None else httpx.Client(timeout=timeout_seconds)
    try:
        response = request_client.get(url, headers=headers)
    except httpx.TimeoutException:
        return ProviderVerifyOutcome(status=VerifyStatus.TIMEOUT, error_code="TIMEOUT")
    except httpx.HTTPError:
        return ProviderVerifyOutcome(status=VerifyStatus.FAILED, error_code="CONNECTION_FAILED")
    finally:
        if owns_client:
            request_client.close()

    if response.status_code == 200:
        return ProviderVerifyOutcome(status=VerifyStatus.OK, error_code=None)
    return ProviderVerifyOutcome(status=VerifyStatus.FAILED, error_code=f"HTTP_{response.status_code}")


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
