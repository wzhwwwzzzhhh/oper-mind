"""P14 角色→Provider 模型装配的 SQLAlchemy 仓储。"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.model_provider import ModelRoleAssignmentData
from src.infrastructure.persistence.models import ModelRoleAssignmentRecord


class SqlAlchemyModelRoleAssignmentRepository:
    """读写角色模型装配；单行即单角色（role 主键），模型覆盖可选。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> dict[str, ModelRoleAssignmentData]:
        """读取全部装配，按 role 建索引。"""
        rows = self._session.scalars(select(ModelRoleAssignmentRecord))
        return {row.role: _to_data(row) for row in rows}

    def get(self, role: str) -> ModelRoleAssignmentData | None:
        """按角色读取装配；不存在返回 None。"""
        row = self._session.get(ModelRoleAssignmentRecord, role)
        return _to_data(row) if row is not None else None

    def upsert(self, data: ModelRoleAssignmentData) -> ModelRoleAssignmentData:
        """在调用方事务内写入或覆盖一条角色装配。"""
        row = self._session.get(ModelRoleAssignmentRecord, data.role)
        now = datetime.now(UTC)
        if row is None:
            row = ModelRoleAssignmentRecord(
                role=data.role,
                provider_id=data.provider_id,
                model=data.model,
                created_at=now,
                updated_at=now,
            )
            self._session.add(row)
        else:
            row.provider_id = data.provider_id
            row.model = data.model
            row.updated_at = now
        self._session.flush()
        return _to_data(row)

    def delete(self, role: str) -> bool:
        """删除一条装配；不存在返回 False。"""
        row = self._session.get(ModelRoleAssignmentRecord, role)
        if row is None:
            return False
        self._session.delete(row)
        self._session.flush()
        return True

    def delete_for_provider(self, provider_id: UUID) -> None:
        """删除某 Provider 的全部装配（Provider 删除时清理，避免悬挂引用）。"""
        self._session.execute(
            delete(ModelRoleAssignmentRecord).where(ModelRoleAssignmentRecord.provider_id == provider_id)
        )


def _to_data(row: ModelRoleAssignmentRecord) -> ModelRoleAssignmentData:
    """把 ORM 行收敛为领域数据。"""
    return ModelRoleAssignmentData(
        role=row.role,
        provider_id=row.provider_id,
        model=row.model,
        created_at=_as_utc(row.created_at),
        updated_at=_as_utc(row.updated_at),
    )


def _as_utc(value: datetime) -> datetime:
    """统一为 UTC aware datetime。"""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
