"""P8 动态注册服务的 SQLAlchemy 仓储。

DSN 以密文流转：仓储只读写 ``dsn_encrypted`` / ``dsn_nonce`` / ``dsn_masked_tail``，
从不接触明文；明文只存在于应用层的加密/掩码瞬间。
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.services import ServiceRegistrationData
from src.infrastructure.persistence.models import ServiceRegistryRecord


class SqlAlchemyServiceRegistryRepository:
    """读写 service_registry；DSN 以密文流转。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> list[ServiceRegistrationData]:
        """按创建顺序读取全部动态注册服务。"""
        rows = self._session.scalars(
            select(ServiceRegistryRecord).order_by(
                ServiceRegistryRecord.created_at.asc(),
                ServiceRegistryRecord.instance_id.asc(),
            )
        )
        return [_to_data(row) for row in rows]

    def get_by_instance_id(self, instance_id: str) -> ServiceRegistrationData | None:
        """按实例 ID 读取动态注册服务；不存在返回 None。"""
        row = self._session.scalars(
            select(ServiceRegistryRecord).where(ServiceRegistryRecord.instance_id == instance_id)
        ).first()
        return _to_data(row) if row is not None else None

    def add(self, data: ServiceRegistrationData) -> ServiceRegistrationData:
        """在调用方事务内新增动态注册服务并 flush 回填时间戳。"""
        row = ServiceRegistryRecord(
            instance_id=data.instance_id,
            kind=data.kind,
            title=data.title,
            dsn_encrypted=data.dsn_encrypted,
            dsn_nonce=data.dsn_nonce,
            dsn_masked_tail=data.dsn_masked_tail,
        )
        self._session.add(row)
        self._session.flush()
        return _to_data(row)

    def update(self, data: ServiceRegistrationData) -> ServiceRegistrationData | None:
        """按实例 ID 更新标题与 DSN 密文；不存在返回 None。"""
        row = self._session.scalars(
            select(ServiceRegistryRecord).where(ServiceRegistryRecord.instance_id == data.instance_id)
        ).first()
        if row is None:
            return None
        row.title = data.title
        row.kind = data.kind
        row.dsn_encrypted = data.dsn_encrypted
        row.dsn_nonce = data.dsn_nonce
        row.dsn_masked_tail = data.dsn_masked_tail
        self._session.flush()
        return _to_data(row)

    def delete(self, instance_id: str) -> bool:
        """按实例 ID 删除动态注册服务与加密凭据；不存在返回 False。"""
        row = self._session.scalars(
            select(ServiceRegistryRecord).where(ServiceRegistryRecord.instance_id == instance_id)
        ).first()
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True


def _to_data(row: ServiceRegistryRecord) -> ServiceRegistrationData:
    """把 ORM 行收敛为领域数据，阻止数据库字段向外泄露。"""
    return ServiceRegistrationData(
        instance_id=row.instance_id,
        kind=row.kind,
        title=row.title,
        dsn_encrypted=row.dsn_encrypted,
        dsn_nonce=row.dsn_nonce,
        has_dsn=row.dsn_encrypted is not None,
        dsn_masked_tail=row.dsn_masked_tail,
        created_at=_as_utc(row.created_at) if row.created_at is not None else None,
        updated_at=_as_utc(row.updated_at) if row.updated_at is not None else None,
    )


def _as_utc(value: datetime) -> datetime:
    """统一为 UTC aware datetime。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
