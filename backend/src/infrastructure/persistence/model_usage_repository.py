"""P8 模型用量仓储：采集写入与统计聚合查询。"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from src.domain.model_usage import (
    MODEL_PRICES_KEY,
    ModelPrice,
    ModelUsageReader,
    ModelUsageStatsRow,
    PriceOverridesReader,
    UsageRecord,
    decode_prices,
)
from src.infrastructure.persistence.app_settings_repository import SqlAlchemyAppSettingsRepository
from src.infrastructure.persistence.database import SessionFactory
from src.infrastructure.persistence.models import ModelUsageRecord


def _utc_now() -> datetime:
    """返回应用仓储使用的 UTC aware 当前时间。"""
    return datetime.now(UTC)


class SqlAlchemyUsageRecorder:
    """把单次真实调用用量写入应用库；短生命周期 Session，失败抛 SQLAlchemyError。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record(self, record: UsageRecord) -> None:
        """写入一次用量事实并提交；失败抛异常由调用方降级。"""
        session = self._session_factory()
        try:
            session.add(
                ModelUsageRecord(
                    model=record["model"],
                    input_tokens=record["input_tokens"],
                    output_tokens=record["output_tokens"],
                    total_tokens=record["total_tokens"],
                    created_at=record["occurred_at"],
                )
            )
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()


class SqlAlchemyModelUsageReader(ModelUsageReader):
    """用量统计的库内聚合查询；短生命周期 Session，失败抛 SQLAlchemyError。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def stats(
        self,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        model: str | None = None,
    ) -> list[ModelUsageStatsRow]:
        """按时间窗/模型过滤，按模型分组聚合 token 用量；无记录返回空列表。"""
        session = self._session_factory()
        try:
            statement = (
                select(
                    ModelUsageRecord.model,
                    func.sum(ModelUsageRecord.input_tokens),
                    func.sum(ModelUsageRecord.output_tokens),
                    func.sum(ModelUsageRecord.total_tokens),
                )
                .group_by(ModelUsageRecord.model)
                .order_by(ModelUsageRecord.model)
            )
            if model is not None:
                statement = statement.where(ModelUsageRecord.model == model)
            if from_at is not None:
                statement = statement.where(ModelUsageRecord.created_at >= from_at)
            if to_at is not None:
                statement = statement.where(ModelUsageRecord.created_at <= to_at)
            rows = session.execute(statement).all()
            return [
                ModelUsageStatsRow(
                    model=str(row[0]),
                    input_tokens=int(row[1] or 0),
                    output_tokens=int(row[2] or 0),
                    total_tokens=int(row[3] or 0),
                )
                for row in rows
            ]
        finally:
            session.close()


class SqlAlchemyPriceOverridesReader(PriceOverridesReader):
    """从应用库 app_settings 读取单价覆盖；缺失/损坏时诚实降级为空覆盖。"""

    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def read(self) -> dict[str, ModelPrice]:
        """读取 ``model.prices`` 键；缺失/损坏/应用库不可用时返回空覆盖。"""
        session = self._session_factory()
        try:
            raw = SqlAlchemyAppSettingsRepository(session).get(MODEL_PRICES_KEY)
        finally:
            session.close()
        return decode_prices(raw)
