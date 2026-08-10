"""应用库通用键值运行时设置的 SQLAlchemy 仓储。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.infrastructure.persistence.models import AppSettingRecord


def _utc_now() -> datetime:
    """返回应用仓储使用的 UTC aware 当前时间。"""
    return datetime.now(UTC)


class SqlAlchemyAppSettingsRepository:
    """读写应用库键值设置；不存在时 get 返回 None，set 负责 upsert。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, key: str) -> str | None:
        """按键读取设置值；不存在返回 None。"""
        row = self._session.get(AppSettingRecord, key)
        if row is None:
            return None
        return row.value

    def set(self, key: str, value: str) -> None:
        """按键写入设置值；同键覆盖，行存在则更新 updated_at。"""
        row = self._session.get(AppSettingRecord, key)
        if row is None:
            self._session.add(
                AppSettingRecord(
                    key=key,
                    value=value,
                    updated_at=_utc_now(),
                )
            )
        else:
            row.value = value
            row.updated_at = _utc_now()
        self._session.flush()

    def delete(self, key: str) -> None:
        """按键删除设置；不存在时静默返回。"""
        row = self._session.get(AppSettingRecord, key)
        if row is not None:
            self._session.delete(row)
            self._session.flush()
