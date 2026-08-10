"""P6 模型 Provider 配置的 SQLAlchemy 仓储。

API Key 以密文流转：仓储只读写 ``api_key_encrypted`` / ``api_key_nonce``，
从不接触明文；明文只存在于应用层的加密/掩码瞬间。
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from src.domain.model_provider import (
    ModelProviderData,
    ModelProviderIdempotencyKeyData,
    ProviderEndpoint,
    VerifyStatus,
)
from src.infrastructure.persistence.models import (
    ModelProviderIdempotencyKeyRecord,
    ModelProviderRecord,
)


class SqlAlchemyModelProviderRepository:
    """读写 Provider 配置；API Key 以密文流转。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> list[ModelProviderData]:
        """按创建顺序读取全部 Provider 配置。"""
        rows = self._session.scalars(
            select(ModelProviderRecord).order_by(
                ModelProviderRecord.created_at.asc(),
                ModelProviderRecord.id.asc(),
            )
        )
        return [_to_data(row) for row in rows]

    def get_by_id(self, provider_id: UUID) -> ModelProviderData | None:
        """按 ID 读取 Provider 配置；不存在返回 None。"""
        row = self._session.get(ModelProviderRecord, provider_id)
        return _to_data(row) if row is not None else None

    def add(self, data: ModelProviderData) -> ModelProviderData:
        """在调用方事务内新增 Provider 配置并 flush 回填 ID。"""
        row = ModelProviderRecord(
            name=data.name,
            base_url=data.base_url,
            model=data.model,
            api_key_encrypted=data.api_key_encrypted,
            api_key_nonce=data.api_key_nonce,
            active_endpoint=data.active_endpoint.value if data.active_endpoint is not None else None,
            verify_status=data.verify_status.value,
            last_verified_at=data.last_verified_at,
            verify_error_code=data.verify_error_code,
        )
        self._session.add(row)
        self._session.flush()
        return _to_data(row)

    def update(self, data: ModelProviderData) -> ModelProviderData | None:
        """按 ID 更新名称 / Base URL / 模型与 API Key 密文，并重置验证状态；不存在返回 None。"""
        row = self._session.get(ModelProviderRecord, data.id)
        if row is None:
            return None
        row.name = data.name
        row.base_url = data.base_url
        row.model = data.model
        row.api_key_encrypted = data.api_key_encrypted
        row.api_key_nonce = data.api_key_nonce
        row.verify_status = data.verify_status.value
        row.last_verified_at = data.last_verified_at
        row.verify_error_code = data.verify_error_code
        self._session.flush()
        return _to_data(row)

    def activate(self, provider_id: UUID, endpoint: ProviderEndpoint) -> ModelProviderData | None:
        """在同一事务内原子替换激活：先解除同端点旧激活，再激活目标 Provider。"""
        self._session.execute(
            update(ModelProviderRecord)
            .where(ModelProviderRecord.active_endpoint == endpoint.value)
            .values(active_endpoint=None)
        )
        row = self._session.get(ModelProviderRecord, provider_id)
        if row is None:
            return None
        row.active_endpoint = endpoint.value
        self._session.flush()
        return _to_data(row)

    def update_verify(
        self,
        provider_id: UUID,
        status: VerifyStatus,
        verified_at: datetime,
        error_code: str | None,
    ) -> ModelProviderData | None:
        """写入连接验证的脱敏结果；不存在返回 None。"""
        row = self._session.get(ModelProviderRecord, provider_id)
        if row is None:
            return None
        row.verify_status = status.value
        row.last_verified_at = verified_at
        row.verify_error_code = error_code
        self._session.flush()
        return _to_data(row)

    def delete(self, provider_id: UUID) -> bool:
        """删除 Provider 及其幂等键记录；返回是否存在。"""
        row = self._session.get(ModelProviderRecord, provider_id)
        if row is None:
            return False
        self._session.execute(
            delete(ModelProviderIdempotencyKeyRecord).where(
                ModelProviderIdempotencyKeyRecord.provider_id == provider_id
            )
        )
        self._session.delete(row)
        self._session.flush()
        return True


class SqlAlchemyModelProviderIdempotencyRepository:
    """Provider 创建幂等键的读写。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_key(self, idempotency_key: UUID) -> ModelProviderIdempotencyKeyData | None:
        """按幂等键读取记录；不存在返回 None。"""
        row = self._session.get(ModelProviderIdempotencyKeyRecord, idempotency_key)
        if row is None:
            return None
        return ModelProviderIdempotencyKeyData(
            idempotency_key=row.idempotency_key,
            provider_id=row.provider_id,
            request_fingerprint=row.request_fingerprint,
            expires_at=_as_utc(row.expires_at),
            created_at=_as_utc(row.created_at),
        )

    def add(self, data: ModelProviderIdempotencyKeyData) -> None:
        """在调用方事务内新增幂等键记录。"""
        self._session.add(
            ModelProviderIdempotencyKeyRecord(
                idempotency_key=data.idempotency_key,
                provider_id=data.provider_id,
                request_fingerprint=data.request_fingerprint,
                expires_at=data.expires_at,
                created_at=data.created_at,
            )
        )

    def delete(self, idempotency_key: UUID) -> None:
        """删除一条幂等键记录（用于过期后允许同一键重新创建）。"""
        row = self._session.get(ModelProviderIdempotencyKeyRecord, idempotency_key)
        if row is not None:
            self._session.delete(row)


def _to_data(row: ModelProviderRecord) -> ModelProviderData:
    """把 ORM 行收敛为领域数据，阻止数据库字段向外泄露。"""
    return ModelProviderData(
        id=row.id,
        name=row.name,
        base_url=row.base_url,
        model=row.model,
        api_key_encrypted=row.api_key_encrypted,
        api_key_nonce=row.api_key_nonce,
        has_api_key=row.api_key_encrypted is not None,
        masked_tail=None,
        active_endpoint=ProviderEndpoint(row.active_endpoint) if row.active_endpoint is not None else None,
        verify_status=VerifyStatus(row.verify_status),
        last_verified_at=_as_utc(row.last_verified_at) if row.last_verified_at is not None else None,
        verify_error_code=row.verify_error_code,
        created_at=_as_utc(row.created_at) if row.created_at is not None else None,
        updated_at=_as_utc(row.updated_at) if row.updated_at is not None else None,
    )


def _as_utc(value: datetime) -> datetime:
    """统一为 UTC aware datetime。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
