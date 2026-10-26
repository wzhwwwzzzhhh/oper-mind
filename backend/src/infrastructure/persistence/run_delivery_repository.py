"""MainAgent typed 交付的 1:1 SQLAlchemy Repository。"""

from __future__ import annotations

from uuid import UUID

from pydantic import TypeAdapter, ValidationError
from sqlalchemy.orm import Session

from src.domain.main_agent import (
    MainAgentDeliveryUnavailableError,
    MainComparisonDeliveryV1,
    MainDeliveryV1,
)
from src.infrastructure.persistence.models import RunDeliveryRecord

_DELIVERY_ADAPTER: TypeAdapter[MainDeliveryV1] = TypeAdapter(MainDeliveryV1)


class SqlAlchemyRunDeliveryRepository:
    """只读严格解析交付；未知版本、损坏 JSON 或身份不一致均安全失败。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run_id: UUID, delivery: MainDeliveryV1) -> None:
        """将交付加入调用方事务，不提交；仅成功终态事务调用。"""
        payload = delivery.model_dump(mode="json")
        self._session.add(
            RunDeliveryRecord(
                run_id=run_id,
                schema_version=payload["schema_version"],
                kind=delivery.kind,
                payload=payload,
            )
        )

    def get_by_run_id(self, run_id: UUID) -> MainDeliveryV1 | None:
        """按 Run 唯一关联读取并严格解析交付。"""
        record = self._session.get(RunDeliveryRecord, run_id)
        if record is None:
            return None
        if record.schema_version != 1:
            raise MainAgentDeliveryUnavailableError()
        try:
            delivery = _DELIVERY_ADAPTER.validate_python(record.payload)
        except ValidationError:
            raise MainAgentDeliveryUnavailableError() from None
        if delivery.kind != record.kind:
            raise MainAgentDeliveryUnavailableError()
        if delivery.schema_version != record.schema_version:
            raise MainAgentDeliveryUnavailableError()
        if (
            isinstance(delivery, MainComparisonDeliveryV1)
            and delivery.comparison.run_id != run_id
        ):
            raise MainAgentDeliveryUnavailableError()
        return delivery
