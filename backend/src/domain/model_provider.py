"""P6 模型 Provider 配置的跨层领域模型。

API Key 明文绝不进入本模型之外的任何层；``api_key_encrypted`` / ``api_key_nonce``
仅为应用层与仓储之间的密文流转，对外资源映射只取 ``has_api_key`` 与 ``masked_tail``。
"""

from __future__ import annotations

import ipaddress
from datetime import UTC, datetime
from enum import Enum
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def validate_provider_base_url(value: str) -> str:
    """校验 Provider Base URL：http(s) 协议、非 localhost 强制 https、拒绝私有/保留地址段。

    仅做静态校验；域名解析后的目标 IP 校验在 verify 时执行（见连接验证 Connector）。
    """
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("Base URL 必须使用 http 或 https 协议。")
    host = parsed.hostname
    if not host:
        raise ValueError("Base URL 缺少有效主机名。")
    normalized = host.rstrip(".").lower()
    is_localhost = normalized in {"localhost", "127.0.0.1", "::1"}
    if not is_localhost:
        if parsed.scheme != "https":
            raise ValueError("非 localhost 的 Base URL 必须使用 https。")
        if _is_private_or_reserved_ip(normalized):
            raise ValueError("Base URL 不允许指向私有、链路本地或保留地址段。")
    return value


def _is_private_or_reserved_ip(host: str) -> bool:
    """仅对字面 IP 做静态判定；域名返回 False，交由 verify 时解析校验。"""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return not ip.is_global


class ModelProviderDomainModel(BaseModel):
    """模型 Provider 跨层模型基类，拒绝未约定字段。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderEndpoint(str, Enum):
    """Provider 可被激活的服务端点。"""

    DIAGNOSTIC = "diagnostic"
    JUDGE = "judge"


class VerifyStatus(str, Enum):
    """连接验证的诚实状态。"""

    UNKNOWN = "unknown"
    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"


class ModelProviderData(ModelProviderDomainModel):
    """一条 Provider 配置；API Key 仅以密文流转。"""

    id: UUID | None = None
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    api_key_encrypted: str | None = None
    api_key_nonce: str | None = None
    has_api_key: bool = False
    masked_tail: str | None = None
    active_endpoint: ProviderEndpoint | None = None
    verify_status: VerifyStatus = VerifyStatus.UNKNOWN
    last_verified_at: datetime | None = None
    verify_error_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @field_validator("last_verified_at")
    @classmethod
    def validate_last_verified_at(cls, value: datetime | None) -> datetime | None:
        """验证时间必须为 UTC aware datetime。"""
        if value is not None and (value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value)):
            raise ValueError("last_verified_at 必须是 UTC aware datetime。")
        return value


class ModelProviderIdempotencyKeyData(ModelProviderDomainModel):
    """Provider 创建请求的幂等语义记录。"""

    idempotency_key: UUID
    provider_id: UUID
    request_fingerprint: str = Field(min_length=1, max_length=64)
    expires_at: datetime
    created_at: datetime


class ModelProviderModelsData(ModelProviderDomainModel):
    """Provider 模型枚举的跨层结果；模型名列表或脱敏失败分类。"""

    provider_id: UUID | None = None
    status: VerifyStatus
    models: list[str] | None = None
    error_code: str | None = None
