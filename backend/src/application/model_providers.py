"""P6 模型 Provider 配置应用服务：读写 / 激活 / 生效配置解析。

明文 API Key 只在本服务内的加密/掩码瞬间出现，绝不进入日志 / Trace / 接口响应。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import TypeVar
from uuid import UUID

from cryptography.exceptions import InvalidTag
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from src.application.errors import (
    ProviderIdempotencyReusedError,
    ProviderNotFoundError,
    SecretKeyNotConfiguredError,
)
from src.config import load_config
from src.domain.model_provider import (
    ModelProviderData,
    ModelProviderIdempotencyKeyData,
    ProviderEndpoint,
    VerifyStatus,
    validate_provider_base_url,
)
from src.infrastructure.model_provider_verify import ProviderVerifyOutcome, verify_provider_connection
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.model_provider_repository import (
    SqlAlchemyModelProviderIdempotencyRepository,
    SqlAlchemyModelProviderRepository,
)
from src.infrastructure.secrets import MIN_API_KEY_LENGTH, decrypt_api_key, encrypt_api_key

IDEMPOTENCY_RETENTION = timedelta(hours=24)
TransactionT = TypeVar("TransactionT")


class CreateModelProviderCommand(BaseModel):
    """新增 Provider 命令。"""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    api_key: str | None = None
    idempotency_key: UUID
    request_fingerprint: str = Field(min_length=1, max_length=64)

    @field_validator("base_url")
    @classmethod
    def validate_base_url_field(cls, value: str) -> str:
        """拒绝协议/主机不合法的 Base URL。"""
        return validate_provider_base_url(value)

    @field_validator("api_key")
    @classmethod
    def validate_api_key_length(cls, value: str | None) -> str | None:
        """API Key 若提供则必须达到最小长度，避免掩码规则完整暴露。"""
        if value is not None and value != "" and len(value) < MIN_API_KEY_LENGTH:
            raise ValueError(f"API Key 长度至少需要 {MIN_API_KEY_LENGTH} 字符。")
        return value


class UpdateModelProviderCommand(BaseModel):
    """编辑 Provider 命令；api_key 为 None=不改，空串=清空。"""

    model_config = ConfigDict(extra="forbid")

    provider_id: UUID
    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    api_key: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url_field(cls, value: str) -> str:
        """拒绝协议/主机不合法的 Base URL。"""
        return validate_provider_base_url(value)

    @field_validator("api_key")
    @classmethod
    def validate_api_key_length(cls, value: str | None) -> str | None:
        """非空 API Key 必须达到最小长度。"""
        if value is not None and value != "" and len(value) < MIN_API_KEY_LENGTH:
            raise ValueError(f"API Key 长度至少需要 {MIN_API_KEY_LENGTH} 字符。")
        return value


class ActivateModelProviderCommand(BaseModel):
    """激活 Provider 为指定端点生效配置。"""

    model_config = ConfigDict(extra="forbid")

    provider_id: UUID
    endpoint: ProviderEndpoint


class ModelProviderApplicationService:
    """Provider 配置用例；明文只在加密/掩码瞬间出现。"""

    def __init__(self, session_factory: SessionFactory, secret_key: bytes | None) -> None:
        self._session_factory = session_factory
        self._secret_key = secret_key

    def list(self) -> list[ModelProviderData]:
        """读取全部 Provider 的安全视图。"""
        session = self._session_factory()
        try:
            return [_with_mask(item, self._secret_key) for item in SqlAlchemyModelProviderRepository(session).list()]
        finally:
            session.close()

    def get(self, provider_id: UUID) -> ModelProviderData:
        """按 ID 读取单个 Provider 的安全视图。"""
        session = self._session_factory()
        try:
            item = SqlAlchemyModelProviderRepository(session).get_by_id(provider_id)
        finally:
            session.close()
        if item is None:
            raise ProviderNotFoundError()
        return _with_mask(item, self._secret_key)

    def create(self, command: CreateModelProviderCommand) -> ModelProviderData:
        """新增 Provider；API Key 加密后落库，同幂等键同载荷重放。"""
        encrypted, nonce = self._encrypt_or_none(command.api_key)
        now = _utc_now()

        def operation(session: Session) -> ModelProviderData:
            repository = SqlAlchemyModelProviderRepository(session)
            idempotency_repository = SqlAlchemyModelProviderIdempotencyRepository(session)
            existing = idempotency_repository.get_by_key(command.idempotency_key)
            if existing is not None:
                if existing.request_fingerprint != command.request_fingerprint:
                    raise ProviderIdempotencyReusedError()
                if existing.expires_at <= now:
                    # 幂等键已过期：删除旧记录，按新创建继续（保留 24h 语义）。
                    idempotency_repository.delete(command.idempotency_key)
                else:
                    created = repository.get_by_id(existing.provider_id)
                    if created is None:
                        raise ProviderNotFoundError()
                    return created
            created = repository.add(
                ModelProviderData(
                    name=command.name,
                    base_url=command.base_url,
                    model=command.model,
                    api_key_encrypted=encrypted,
                    api_key_nonce=nonce,
                    has_api_key=encrypted is not None,
                )
            )
            idempotency_repository.add(
                ModelProviderIdempotencyKeyData(
                    idempotency_key=command.idempotency_key,
                    provider_id=created.id,
                    request_fingerprint=command.request_fingerprint,
                    expires_at=now + IDEMPOTENCY_RETENTION,
                    created_at=now,
                )
            )
            return created

        return _with_mask(_in_transaction(self._session_factory, operation), self._secret_key)

    def update(self, command: UpdateModelProviderCommand) -> ModelProviderData:
        """编辑 Provider；api_key 不传=保留，空串=清空，否则重新加密。"""

        def operation(session: Session) -> ModelProviderData:
            repository = SqlAlchemyModelProviderRepository(session)
            current = repository.get_by_id(command.provider_id)
            if current is None:
                raise ProviderNotFoundError()
            if command.api_key is None:
                encrypted, nonce = current.api_key_encrypted, current.api_key_nonce
            elif command.api_key == "":
                encrypted, nonce = None, None
            else:
                encrypted, nonce = self._encrypt_or_none(command.api_key)
            updated = repository.update(
                current.model_copy(
                    update={
                        "name": command.name,
                        "base_url": command.base_url,
                        "model": command.model,
                        "api_key_encrypted": encrypted,
                        "api_key_nonce": nonce,
                        "has_api_key": encrypted is not None,
                        "verify_status": VerifyStatus.UNKNOWN,
                        "last_verified_at": None,
                        "verify_error_code": None,
                    }
                )
            )
            if updated is None:
                raise ProviderNotFoundError()
            return updated

        return _with_mask(_in_transaction(self._session_factory, operation), self._secret_key)

    def activate(self, command: ActivateModelProviderCommand) -> ModelProviderData:
        """单事务原子替换：目标端点只保留当前激活 Provider。"""

        def operation(session: Session) -> ModelProviderData:
            activated = SqlAlchemyModelProviderRepository(session).activate(command.provider_id, command.endpoint)
            if activated is None:
                raise ProviderNotFoundError()
            return activated

        return _with_mask(_in_transaction(self._session_factory, operation), self._secret_key)

    def verify(self, provider_id: UUID) -> ModelProviderData:
        """受控、限时验证 Provider 连通并写入脱敏结果；无 Key 时诚实失败。"""

        def operation(session: Session) -> ModelProviderData:
            repository = SqlAlchemyModelProviderRepository(session)
            current = repository.get_by_id(provider_id)
            if current is None:
                raise ProviderNotFoundError()
            outcome = self._verify_against(current)
            updated = repository.update_verify(
                provider_id,
                status=outcome.status,
                verified_at=_utc_now(),
                error_code=outcome.error_code,
            )
            if updated is None:
                raise ProviderNotFoundError()
            return updated

        return _with_mask(_in_transaction(self._session_factory, operation), self._secret_key)

    def _verify_against(self, data: ModelProviderData) -> ProviderVerifyOutcome:
        """对单个 Provider 执行受控验证；解密失败或无 Key / 主密钥缺失时诚实分类。"""
        if not data.has_api_key or data.api_key_encrypted is None or data.api_key_nonce is None:
            return ProviderVerifyOutcome(status=VerifyStatus.FAILED, error_code="NO_API_KEY")
        if self._secret_key is None:
            return ProviderVerifyOutcome(status=VerifyStatus.FAILED, error_code="SECRET_KEY_NOT_CONFIGURED")
        try:
            plaintext = decrypt_api_key(data.api_key_encrypted, data.api_key_nonce, self._secret_key)
        except (InvalidTag, ValueError):
            return ProviderVerifyOutcome(status=VerifyStatus.FAILED, error_code="KEY_DECRYPT_FAILED")
        return verify_provider_connection(data.base_url, plaintext)

    def delete(self, provider_id: UUID) -> None:
        """删除 Provider；不存在时抛 ProviderNotFoundError。"""

        def operation(session: Session) -> None:
            deleted = SqlAlchemyModelProviderRepository(session).delete(provider_id)
            if not deleted:
                raise ProviderNotFoundError()

        _in_transaction(self._session_factory, operation)

    def effective_config(self) -> dict[str, dict[str, str]]:
        """返回当前生效模型配置（DB 激活 Provider 优先，env/YAML 兜底）。"""
        return resolve_model_config(self._session_factory, self._secret_key)

    def _encrypt_or_none(self, api_key: str | None) -> tuple[str | None, str | None]:
        """加密 API Key；未提供或空串返回空，主密钥缺失时诚实拒绝。"""
        if api_key is None or api_key == "":
            return None, None
        if self._secret_key is None:
            raise SecretKeyNotConfiguredError()
        return encrypt_api_key(api_key, self._secret_key)


def provider_create_fingerprint(name: str, base_url: str, model: str, api_key: str | None) -> str:
    """计算 Provider 创建请求的稳定 SHA-256 语义指纹（不反向暴露明文 Key）。"""
    from hashlib import sha256

    payload = "\n".join((name.strip(), base_url.strip(), model.strip(), (api_key or "").strip()))
    return sha256(payload.encode("utf-8")).hexdigest()


def resolve_model_config(
    session_factory: SessionFactory,
    secret_key: bytes | None,
) -> dict[str, dict[str, str]]:
    """解析生效模型配置：DB 激活 Provider 优先，未激活时回退 env/YAML；永不 raise。

    返回结构与 ``load_config()`` 一致（``llm`` / ``judge_llm`` 段），供会话链路与
    ``GET /model/config`` 使用；配置缺失或应用库不可用时不抛错，由消费方诚实降级。
    """
    try:
        config = load_config()
    except ValueError:
        config = {}
    if not isinstance(config.get("llm"), dict):
        config["llm"] = {}
    try:
        session = session_factory()
        try:
            providers = SqlAlchemyModelProviderRepository(session).list()
        finally:
            session.close()
    except SQLAlchemyError:
        providers = ()
    for endpoint, section in (("diagnostic", "llm"), ("judge", "judge_llm")):
        provider = next(
            (provider for provider in providers if provider.active_endpoint is ProviderEndpoint(endpoint)),
            None,
        )
        overlay = _resolved_provider_config(provider, secret_key)
        if overlay is not None:
            config[section] = overlay
    return config


def _resolved_provider_config(
    provider: ModelProviderData | None,
    secret_key: bytes | None,
) -> dict[str, str] | None:
    """把激活 Provider 收敛为可用的模型配置；无 Key / 主密钥缺失 / 解密失败时回退 env/YAML。"""
    if (
        provider is None
        or not provider.has_api_key
        or provider.api_key_encrypted is None
        or provider.api_key_nonce is None
    ):
        return None
    if secret_key is None:
        return None
    try:
        plaintext = decrypt_api_key(provider.api_key_encrypted, provider.api_key_nonce, secret_key)
    except (InvalidTag, ValueError):
        return None
    return {"api_key": plaintext, "base_url": provider.base_url, "model": provider.model}


def _with_mask(data: ModelProviderData, secret_key: bytes | None) -> ModelProviderData:
    """为 Provider 安全视图计算掩码尾（末 4 位）；主密钥缺失或密文不可解时诚实返回 None。

    前端以 `••••••••` + 末 4 位 组合展示；短于最小长度的 Key 整体打码（tail=None）。
    """
    if not data.has_api_key or data.api_key_encrypted is None or data.api_key_nonce is None:
        return data
    if secret_key is None:
        return data.model_copy(update={"masked_tail": None})
    try:
        plaintext = decrypt_api_key(data.api_key_encrypted, data.api_key_nonce, secret_key)
    except (InvalidTag, ValueError):
        return data.model_copy(update={"masked_tail": None})
    if len(plaintext) < MIN_API_KEY_LENGTH:
        return data.model_copy(update={"masked_tail": None})
    return data.model_copy(update={"masked_tail": plaintext[-4:]})


def _in_transaction(session_factory: SessionFactory, operation: Callable[[Session], TransactionT]) -> TransactionT:
    """创建短生命周期 Session 并由 Application Service 统一控制事务。"""
    session = session_factory()
    try:
        result = operation(session)
        session.commit()
        return result
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _utc_now() -> datetime:
    """返回应用服务使用的 UTC aware 当前时间。"""
    return datetime.now(UTC)
