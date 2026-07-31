"""P4.3 服务关联活动的 SQLAlchemy 只读查询。"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, and_, or_, select
from sqlalchemy.orm import Session

from src.domain.records import DiagnosisRunCursor, RepositoryPage
from src.domain.service_repositories import ServiceActivityRepository
from src.domain.services import ServiceActivityData
from src.infrastructure.persistence.models import (
    ActionExecutionRecord,
    ActionProposalRecord,
    ActionVerificationRecord,
    DiagnosisResultRecord,
    DiagnosisRunRecord,
    SessionRecord,
)


class SqlAlchemyServiceActivityRepository(ServiceActivityRepository):
    """只在绑定 service_id 的 Session 范围读取最小活动摘要。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_by_service_id(
        self,
        service_id: str,
        cursor: DiagnosisRunCursor | None,
        limit: int,
    ) -> RepositoryPage[ServiceActivityData, DiagnosisRunCursor]:
        """按 Run 创建时间倒序分页，历史未绑定会话绝不参与结果。"""
        _validate_limit(limit)
        statement = _activity_select().where(SessionRecord.service_id == service_id)
        if cursor is not None:
            statement = statement.where(
                or_(
                    DiagnosisRunRecord.created_at < cursor.created_at,
                    and_(
                        DiagnosisRunRecord.created_at == cursor.created_at,
                        DiagnosisRunRecord.id < cursor.id,
                    ),
                )
            )
        rows = list(
            self._session.execute(
                statement.order_by(DiagnosisRunRecord.created_at.desc(), DiagnosisRunRecord.id.desc()).limit(limit + 1)
            ).mappings()
        )
        items = [_activity_data(row) for row in rows]
        has_more = len(items) > limit
        visible_items = items[:limit]
        next_cursor = None
        if has_more and visible_items:
            last_item = visible_items[-1]
            next_cursor = DiagnosisRunCursor(created_at=last_item.created_at, id=last_item.run_id)
        return RepositoryPage(items=visible_items, next_cursor=next_cursor, has_more=has_more)


def _activity_select() -> Select[tuple[object, ...]]:
    """构造固定关联查询，不返回证据、事件或未脱敏字段。"""
    return (
        select(
            SessionRecord.id.label("session_id"),
            SessionRecord.title.label("session_title"),
            DiagnosisRunRecord.id.label("run_id"),
            DiagnosisRunRecord.status.label("run_status"),
            DiagnosisRunRecord.created_at.label("created_at"),
            DiagnosisRunRecord.finished_at.label("finished_at"),
            DiagnosisResultRecord.summary.label("summary"),
            DiagnosisResultRecord.severity.label("severity"),
            DiagnosisResultRecord.confidence.label("confidence"),
            ActionProposalRecord.status.label("proposal_status"),
            ActionVerificationRecord.status.label("verification_status"),
        )
        .select_from(SessionRecord)
        .join(DiagnosisRunRecord, DiagnosisRunRecord.session_id == SessionRecord.id)
        .outerjoin(DiagnosisResultRecord, DiagnosisResultRecord.run_id == DiagnosisRunRecord.id)
        .outerjoin(ActionProposalRecord, ActionProposalRecord.source_run_id == DiagnosisRunRecord.id)
        .outerjoin(ActionExecutionRecord, ActionExecutionRecord.proposal_id == ActionProposalRecord.id)
        .outerjoin(ActionVerificationRecord, ActionVerificationRecord.execution_id == ActionExecutionRecord.id)
    )


def _activity_data(row: object) -> ServiceActivityData:
    """将 ORM 映射行收敛为公开活动所需的安全标量。"""
    values = dict(row)
    return ServiceActivityData(
        session_id=_as_uuid(values["session_id"]),
        session_title=_as_text(values["session_title"]),
        run_id=_as_uuid(values["run_id"]),
        run_status=_as_text(values["run_status"]),
        created_at=_as_utc(values["created_at"]),
        finished_at=_as_utc_or_none(values.get("finished_at")),
        summary=_as_optional_text(values.get("summary")),
        severity=_as_optional_text(values.get("severity")),
        confidence=_as_optional_float(values.get("confidence")),
        proposal_status=_as_optional_text(values.get("proposal_status")),
        verification_status=_as_optional_text(values.get("verification_status")),
    )


def _validate_limit(limit: int) -> None:
    """与既有 Repository 保持同一分页边界。"""
    if limit < 1 or limit > 100:
        raise ValueError("分页大小超出允许范围。")


def _as_uuid(value: object) -> UUID:
    """ORM 主键必须已由 schema 约束为 UUID。"""
    if not isinstance(value, UUID):
        raise ValueError("服务活动主键无效。")
    return value


def _as_text(value: object) -> str:
    """ORM 必填文本必须为字符串。"""
    if not isinstance(value, str):
        raise ValueError("服务活动文本无效。")
    return value


def _as_optional_text(value: object) -> str | None:
    """将 nullable 字段安全映射为文本或空值。"""
    return value if isinstance(value, str) else None


def _as_optional_float(value: object) -> float | None:
    """将可信数值映射为浮点数，不接受 bool。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _as_utc(value: object) -> datetime:
    """统一应用元数据的 UTC 时间表示。"""
    if not isinstance(value, datetime):
        raise ValueError("服务活动时间无效。")
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _as_utc_or_none(value: object) -> datetime | None:
    """映射可空完成时间。"""
    return None if value is None else _as_utc(value)
