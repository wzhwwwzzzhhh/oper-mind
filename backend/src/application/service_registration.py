"""P8 服务注册应用服务：动态接入、管理与连接测试。

明文 DSN 只在本服务内的加密/掩码瞬间出现，绝不进入日志 / Trace / 接口响应。
连接测试复用 P4 ``health_snapshot()`` 只读机制，只做探活，不执行任意查询。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from inspect import signature
from typing import TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.errors import (
    SecretKeyNotConfiguredError,
    ServiceInstanceConflictError,
    ServiceNotFoundError,
    ServiceRegistrationNotFoundError,
)
from src.domain.services import (
    SERVICE_KINDS,
    BindingOrigin,
    ServiceAvailability,
    ServiceConnector,
    ServiceRegistrationData,
    ServiceRegistry,
    ServiceSnapshotData,
    validate_service_instance_id,
)
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.service_registry_repository import (
    SqlAlchemyServiceRegistryRepository,
)
from src.infrastructure.secrets import MIN_API_KEY_LENGTH, decrypt_dsn, encrypt_dsn

TransactionT = TypeVar("TransactionT")

ALLOWED_KINDS = SERVICE_KINDS

ConnectorFactory = Callable[..., ServiceConnector]


class RegisterServiceCommand(BaseModel):
    """注册服务命令。"""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(min_length=1, max_length=80)
    instance_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    dsn: str = Field(min_length=1, max_length=2000)

    @field_validator("kind")
    @classmethod
    def validate_kind(cls, value: str) -> str:
        """只接受有真实 Connector 的服务类型。"""
        normalized = value.strip().lower()
        if normalized not in ALLOWED_KINDS:
            raise ValueError("暂不支持该服务类型，仅支持 postgres / redis / mysql。")
        return normalized

    @field_validator("instance_id")
    @classmethod
    def validate_instance_id(cls, value: str) -> str:
        """实例 ID 只允许小写字母/数字/点/下划线/连字符。"""
        return validate_service_instance_id(value)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """去除标题首尾空白。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("标题不能为空。")
        return normalized

    @field_validator("dsn")
    @classmethod
    def validate_dsn_length(cls, value: str) -> str:
        """DSN 至少达到最小长度，避免掩码规则完整暴露。"""
        normalized = value.strip()
        if len(normalized) < MIN_API_KEY_LENGTH:
            raise ValueError(f"DSN 长度至少需要 {MIN_API_KEY_LENGTH} 字符。")
        return normalized


class UpdateServiceCommand(BaseModel):
    """编辑服务命令；dsn 为 None=不改。"""

    model_config = ConfigDict(extra="forbid")

    instance_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    dsn: str | None = None

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        """去除标题首尾空白。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("标题不能为空。")
        return normalized

    @field_validator("dsn")
    @classmethod
    def validate_dsn_length(cls, value: str | None) -> str | None:
        """非空 DSN 必须达到最小长度。"""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("DSN 不能为空字符串。")
        if len(normalized) < MIN_API_KEY_LENGTH:
            raise ValueError(f"DSN 长度至少需要 {MIN_API_KEY_LENGTH} 字符。")
        return normalized


class ConnectionTestResult:
    """显式连接测试的安全结果。"""

    def __init__(self, availability: ServiceAvailability, error_code: str | None) -> None:
        self.availability = availability
        self.error_code = error_code


class ServiceRegistrationApplicationService:
    """动态注册服务用例；明文 DSN 只在加密/掩码瞬间出现。"""

    def __init__(
        self,
        session_factory: SessionFactory,
        registry: ServiceRegistry,
        secret_key: bytes | None,
        connector_factory: ConnectorFactory | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._registry = registry
        self._secret_key = secret_key
        self._connector_factory = connector_factory or _default_connector_factory

    def list_registered(self) -> list[ServiceRegistrationData]:
        """读取全部动态注册服务的安全视图。"""
        session = self._session_factory()
        try:
            return SqlAlchemyServiceRegistryRepository(session).list()
        finally:
            session.close()

    def create(self, command: RegisterServiceCommand) -> ServiceRegistrationData:
        """注册服务：DSN 加密落库并注册进运行时 registry；主密钥缺失拒绝创建。"""
        encrypted, nonce, masked_tail = self._encrypt_or_none(command.dsn)
        try:
            candidate = _build_connector(
                self._connector_factory,
                command.kind,
                command.dsn,
                command.instance_id,
                command.title,
                masked_tail,
                BindingOrigin.from_reference(f"registry:{command.instance_id}"),
            )
        except ValueError as error:
            raise ServiceInstanceConflictError() from error

        def operation(session: Session) -> ServiceRegistrationData:
            repository = SqlAlchemyServiceRegistryRepository(session)
            if self._registry.get_connector(command.instance_id) is not None:
                raise ServiceInstanceConflictError()
            if repository.get_by_instance_id(command.instance_id) is not None:
                raise ServiceInstanceConflictError()
            return repository.add(
                ServiceRegistrationData(
                    instance_id=command.instance_id,
                    kind=command.kind,
                    title=command.title,
                    dsn_encrypted=encrypted,
                    dsn_nonce=nonce,
                    has_dsn=encrypted is not None,
                    dsn_masked_tail=masked_tail,
                )
            )

        with self._registry.mutation_guard(command.instance_id):
            if self._registry.get_connector(command.instance_id) is not None:
                raise ServiceInstanceConflictError()
            try:
                created = _in_transaction(self._session_factory, operation)
                self._registry.register(candidate)
            except IntegrityError as error:
                raise ServiceInstanceConflictError() from error
            except ValueError as error:
                self._registry.poison(command.instance_id)
                raise ServiceInstanceConflictError() from error
            return created

    def update(self, command: UpdateServiceCommand) -> ServiceRegistrationData:
        """编辑服务标题/DSN；DSN 更新走同加密纪律，更新后连接状态重置为未验证。"""

        def operation(session: Session) -> tuple[ServiceRegistrationData, ServiceConnector]:
            repository = SqlAlchemyServiceRegistryRepository(session)
            current = repository.get_by_instance_id(command.instance_id)
            if current is None:
                raise ServiceRegistrationNotFoundError()
            if command.dsn is None:
                encrypted, nonce, masked_tail = (
                    current.dsn_encrypted,
                    current.dsn_nonce,
                    current.dsn_masked_tail,
                )
            else:
                encrypted, nonce, masked_tail = self._encrypt_or_none(command.dsn)
            updated = repository.update(
                current.model_copy(
                    update={
                        "title": command.title,
                        "kind": current.kind,
                        "dsn_encrypted": encrypted,
                        "dsn_nonce": nonce,
                        "has_dsn": encrypted is not None,
                        "dsn_masked_tail": masked_tail,
                    }
                )
            )
            if updated is None:
                raise ServiceRegistrationNotFoundError()
            resolved_dsn = command.dsn if command.dsn is not None else self._resolve_dsn(encrypted, nonce)
            candidate = _build_connector(
                self._connector_factory,
                updated.kind,
                resolved_dsn,
                command.instance_id,
                command.title,
                updated.dsn_masked_tail,
                BindingOrigin.from_reference(f"registry:{command.instance_id}"),
            )
            return updated, candidate

        with self._registry.mutation_guard(command.instance_id):
            current = self._registry.get_connector(command.instance_id)
            if current is None:
                raise ServiceRegistrationNotFoundError()
            updated, candidate = _in_transaction(self._session_factory, operation)
            if not self._registry.replace(candidate, expected=current):
                self._registry.poison(command.instance_id)
                raise ServiceRegistrationNotFoundError()
            return updated

    def delete(self, instance_id: str) -> None:
        """移除已落库动态服务：删除加密凭据并从运行时 registry 移除；不存在仍幂等。

        只操作「已落库动态服务」：对 env DSN 硬编码实例（无 DB 行）不做任何 registry
        变更，保证既有硬编码实例在进程内始终可读（对齐 AC11 兼容边界）。
        """

        def operation(session: Session) -> bool:
            repository = SqlAlchemyServiceRegistryRepository(session)
            return repository.delete(instance_id)

        with self._registry.mutation_guard(instance_id):
            current = self._registry.get_connector(instance_id)
            removed_row = _in_transaction(self._session_factory, operation)
            if removed_row and not self._registry.remove(instance_id, expected=current):
                self._registry.poison(instance_id)

    def test_connection(self, instance_id: str) -> ConnectionTestResult:
        """对目标服务发起显式只读连接测试；返回当前状态与安全分类码。"""
        connector = self._registry.get_connector(instance_id)
        if connector is None:
            raise ServiceNotFoundError()
        snapshot = connector.health_snapshot()
        return _classify_test_result(snapshot)

    def _encrypt_or_none(self, dsn: str) -> tuple[str | None, str | None, str | None]:
        """加密 DSN 并计算掩码尾号；主密钥缺失时诚实拒绝。"""
        if self._secret_key is None:
            raise SecretKeyNotConfiguredError()
        encrypted, nonce = encrypt_dsn(dsn, self._secret_key)
        return encrypted, nonce, dsn[-4:]

    def _resolve_dsn(self, encrypted: str | None, nonce: str | None) -> str | None:
        """把密文解析为明文 DSN；主密钥缺失或不可解时诚实返回 None。"""
        if encrypted is None or nonce is None:
            return None
        if self._secret_key is None:
            return None
        try:
            return decrypt_dsn(encrypted, nonce, self._secret_key)
        except Exception:
            return None

def _default_connector_factory(
    kind: str,
    dsn: str | None,
    instance_id: str,
    title: str,
    masked_tail: str | None,
    binding_origin: BindingOrigin | None = None,
) -> ServiceConnector:
    """装配缺省时按服务类型派生受控只读 Connector（懒导入避免层级倒挂）。"""
    from src.infrastructure.services.service_connector_factory import build_service_connector

    return build_service_connector(kind, dsn, instance_id, title, masked_tail, binding_origin)


def _build_connector(
    factory: ConnectorFactory,
    kind: str,
    dsn: str | None,
    instance_id: str,
    title: str,
    masked_tail: str | None,
    binding_origin: BindingOrigin,
) -> ServiceConnector:
    """向 P12 factory 传 origin，同时兼容只用于旧测试的五参数 fake。"""
    if len(signature(factory).parameters) >= 6:
        return factory(kind, dsn, instance_id, title, masked_tail, binding_origin)
    return factory(kind, dsn, instance_id, title, masked_tail)


def _classify_test_result(snapshot: ServiceSnapshotData) -> ConnectionTestResult:
    """把只读快照收敛为显式连接测试结果（含脱敏分类码，不暴露异常详情）。"""
    if snapshot.availability is ServiceAvailability.HEALTHY:
        return ConnectionTestResult(ServiceAvailability.HEALTHY, None)
    if snapshot.availability is ServiceAvailability.NOT_CONFIGURED:
        return ConnectionTestResult(ServiceAvailability.NOT_CONFIGURED, "not_configured")
    return ConnectionTestResult(ServiceAvailability.UNAVAILABLE, "connection_failed")


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
