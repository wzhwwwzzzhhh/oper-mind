"""P8 审计活动的 SQLAlchemy 只读查询：双源有界归并 + 统一键集游标。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import RowMapping, Select, and_, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from src.domain.audit import (
    APPROVAL_ACTOR_UNRECORDED,
    AUDIT_ACTION_TYPES,
    AUDIT_RUN_TYPES,
    AuditActivityCursor,
    AuditActivityData,
    AuditActivityKind,
    AuditActivityType,
    AuditOutcome,
    action_audit_type,
    action_filter_for_outcome,
    action_outcome,
    audit_run_type,
    run_outcome,
    run_status_for_type,
    run_statuses_for_outcome,
)
from src.domain.records import RepositoryPage
from src.infrastructure.persistence.models import (
    ActionEventRecord,
    ActionExecutionRecord,
    ActionProposalRecord,
    ActionVerificationRecord,
    DiagnosisResultRecord,
    DiagnosisRunRecord,
    SessionRecord,
)
from src.infrastructure.persistence.service_repositories import (
    _as_optional_float,
    _as_optional_text,
    _as_text,
    _as_utc,
    _as_uuid,
)


class SqlAlchemyAuditActivityRepository:
    """双源（runs + action_events）键集分页的安全摘要查询。

    每页两侧各取 limit+1 行，按 (time desc, id desc) 归并取前 limit；
    has_more ⟺ 归并后行数 > limit（每侧取 min(侧剩余行数, limit+1)，
    两侧之和 > limit 当且仅当剩余总量 > limit）。
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    def close(self) -> None:
        """释放本次调用持有的数据库会话。"""
        self._session.close()

    def list_activities(
        self,
        cursor: AuditActivityCursor | None,
        limit: int,
        *,
        from_at: datetime | None = None,
        to_at: datetime | None = None,
        service_id: str | None = None,
        action_type: AuditActivityType | None = None,
        outcome: AuditOutcome | None = None,
    ) -> RepositoryPage[AuditActivityData, AuditActivityCursor]:
        _validate_limit(limit)
        run_items = self._list_run_items(
            limit, cursor, from_at=from_at, to_at=to_at, service_id=service_id,
            action_type=action_type, outcome=outcome,
        )
        action_items = self._list_action_items(
            limit, cursor, from_at=from_at, to_at=to_at, service_id=service_id,
            action_type=action_type, outcome=outcome,
        )
        merged = sorted(
            run_items + action_items,
            key=lambda item: (item.occurred_at, item.id),
            reverse=True,
        )
        has_more = len(merged) > limit
        visible = merged[:limit]
        next_cursor = None
        if has_more and visible:
            last = visible[-1]
            next_cursor = AuditActivityCursor(created_at=last.occurred_at, id=last.id)
        return RepositoryPage(items=visible, next_cursor=next_cursor, has_more=has_more)

    def _list_run_items(
        self,
        limit: int,
        cursor: AuditActivityCursor | None,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        service_id: str | None,
        action_type: AuditActivityType | None,
        outcome: AuditOutcome | None,
    ) -> list[AuditActivityData]:
        if action_type is not None and action_type not in AUDIT_RUN_TYPES:
            return []
        statuses: frozenset[str] | None = None
        if outcome is not None:
            statuses = run_statuses_for_outcome(outcome)
            if not statuses:
                return []
        statement = _run_select()
        filters: list[ColumnElement[bool]] = []
        if from_at is not None:
            filters.append(DiagnosisRunRecord.created_at >= from_at)
        if to_at is not None:
            filters.append(DiagnosisRunRecord.created_at <= to_at)
        if service_id is not None:
            filters.append(DiagnosisRunRecord.service_id == service_id)
        if action_type is not None:
            filters.append(DiagnosisRunRecord.status == run_status_for_type(action_type))
        if statuses is not None:
            filters.append(DiagnosisRunRecord.status.in_(statuses))
        if cursor is not None:
            filters.append(
                or_(
                    DiagnosisRunRecord.created_at < cursor.created_at,
                    and_(
                        DiagnosisRunRecord.created_at == cursor.created_at,
                        DiagnosisRunRecord.id < cursor.id,
                    ),
                )
            )
        if filters:
            statement = statement.where(*filters)
        rows = list(
            self._session.execute(
                statement.order_by(DiagnosisRunRecord.created_at.desc(), DiagnosisRunRecord.id.desc()).limit(limit + 1)
            ).mappings()
        )
        return [_run_activity(row) for row in rows]

    def _list_action_items(
        self,
        limit: int,
        cursor: AuditActivityCursor | None,
        *,
        from_at: datetime | None,
        to_at: datetime | None,
        service_id: str | None,
        action_type: AuditActivityType | None,
        outcome: AuditOutcome | None,
    ) -> list[AuditActivityData]:
        event_type: AuditActivityType | None = None
        data_status: str | None = None
        if outcome is not None:
            candidate, required_status = action_filter_for_outcome(outcome)
            if candidate is None:
                return []
            if action_type is not None and action_type is not candidate:
                # 显式类型过滤与结果过滤无交集：与 Run 侧同参数交集语义一致。
                return []
            event_type = candidate
            data_status = required_status
        else:
            event_type = action_type
        if event_type is not None and event_type not in AUDIT_ACTION_TYPES:
            return []
        statement = _action_select()
        filters: list[ColumnElement[bool]] = [
            ActionEventRecord.type.in_([item.value for item in AUDIT_ACTION_TYPES])
        ]
        if from_at is not None:
            filters.append(ActionEventRecord.occurred_at >= from_at)
        if to_at is not None:
            filters.append(ActionEventRecord.occurred_at <= to_at)
        if service_id is not None:
            filters.append(DiagnosisRunRecord.service_id == service_id)
        if event_type is not None:
            filters.append(ActionEventRecord.type == event_type.value)
        if data_status is not None:
            filters.append(ActionEventRecord.data["status"].as_string() == data_status)
        if cursor is not None:
            filters.append(
                or_(
                    ActionEventRecord.occurred_at < cursor.created_at,
                    and_(
                        ActionEventRecord.occurred_at == cursor.created_at,
                        ActionEventRecord.id < cursor.id,
                    ),
                )
            )
        statement = statement.where(*filters)
        rows = list(
            self._session.execute(
                statement.order_by(ActionEventRecord.occurred_at.desc(), ActionEventRecord.id.desc()).limit(limit + 1)
            ).mappings()
        )
        return [_action_activity(row) for row in rows]


def _run_select() -> Select[tuple[object, ...]]:
    """构造 Run 侧查询：只取安全摘要字段，不含证据、事件或未脱敏内容。"""
    return (
        select(
            SessionRecord.id.label("session_id"),
            SessionRecord.title.label("session_title"),
            DiagnosisRunRecord.id.label("run_id"),
            DiagnosisRunRecord.status.label("run_status"),
            DiagnosisRunRecord.service_id.label("service_id"),
            DiagnosisRunRecord.created_at.label("occurred_at"),
            DiagnosisResultRecord.summary.label("summary"),
            DiagnosisResultRecord.severity.label("severity"),
            DiagnosisResultRecord.confidence.label("confidence"),
            ActionProposalRecord.status.label("proposal_status"),
            ActionVerificationRecord.status.label("verification_status"),
        )
        .select_from(DiagnosisRunRecord)
        .join(SessionRecord, SessionRecord.id == DiagnosisRunRecord.session_id)
        .outerjoin(DiagnosisResultRecord, DiagnosisResultRecord.run_id == DiagnosisRunRecord.id)
        .outerjoin(ActionProposalRecord, ActionProposalRecord.source_run_id == DiagnosisRunRecord.id)
        .outerjoin(ActionExecutionRecord, ActionExecutionRecord.proposal_id == ActionProposalRecord.id)
        .outerjoin(ActionVerificationRecord, ActionVerificationRecord.execution_id == ActionExecutionRecord.id)
    )


def _action_select() -> Select[tuple[object, ...]]:
    """构造 action 事件侧查询：事件 data 只取白名单字段，由行转换二次校验。"""
    return (
        select(
            ActionEventRecord.id.label("event_id"),
            ActionEventRecord.type.label("event_type"),
            ActionEventRecord.occurred_at.label("occurred_at"),
            ActionEventRecord.data.label("event_data"),
            ActionProposalRecord.id.label("proposal_id"),
            DiagnosisRunRecord.service_id.label("service_id"),
            SessionRecord.id.label("session_id"),
            SessionRecord.title.label("session_title"),
        )
        .select_from(ActionEventRecord)
        .join(ActionProposalRecord, ActionProposalRecord.id == ActionEventRecord.proposal_id)
        .join(DiagnosisRunRecord, DiagnosisRunRecord.id == ActionProposalRecord.source_run_id)
        .join(SessionRecord, SessionRecord.id == DiagnosisRunRecord.session_id)
    )


def _run_activity(row: RowMapping) -> AuditActivityData:
    """把 Run 侧 ORM 行收敛为公开安全标量。"""
    values = dict(row)
    run_id = _as_uuid(values["run_id"])
    run_status = _as_text(values["run_status"])
    run_type = audit_run_type(run_status)
    if run_type is None:
        raise ValueError(f"未知 Run 状态：{run_status}")
    return AuditActivityData(
        id=run_id,
        kind=AuditActivityKind.RUN,
        type=run_type,
        occurred_at=_as_utc(values["occurred_at"]),
        service_id=_as_optional_text(values.get("service_id")),
        session_id=_as_uuid(values["session_id"]),
        session_title=_as_text(values["session_title"]),
        outcome=run_outcome(run_type),
        summary=_as_optional_text(values.get("summary")),
        run_id=run_id,
        severity=_as_optional_text(values.get("severity")),
        confidence=_as_optional_float(values.get("confidence")),
        proposal_status=_as_optional_text(values.get("proposal_status")),
        verification_status=_as_optional_text(values.get("verification_status")),
    )


def _action_activity(row: RowMapping) -> AuditActivityData:
    """把 action 事件侧 ORM 行收敛为公开安全标量：data 只提取白名单字段。"""
    values = dict(row)
    event_type = action_audit_type(_as_text(values["event_type"]))
    if event_type is None:
        raise ValueError(f"未知 action 事件类型：{values.get('event_type')}")
    event_data = values["event_data"]
    if not isinstance(event_data, dict):
        raise ValueError("action 事件数据无效。")
    summary = event_data.get("summary")
    if not isinstance(summary, str) or len(summary) > 500:
        summary = None
    # action_id / mode 只从事件 data 白名单提取：事件不携带即诚实置空，不从提案表补造。
    action_id = event_data.get("action_id")
    if not isinstance(action_id, str) or len(action_id) > 120:
        action_id = None
    mode = event_data.get("mode")
    if mode not in {"mock", "target"}:
        mode = None
    return AuditActivityData(
        id=_as_uuid(values["event_id"]),
        kind=AuditActivityKind.ACTION,
        type=event_type,
        occurred_at=_as_utc(values["occurred_at"]),
        service_id=_as_optional_text(values.get("service_id")),
        session_id=_as_uuid(values["session_id"]),
        session_title=_as_text(values["session_title"]),
        outcome=action_outcome(event_type, event_data),
        summary=summary,
        proposal_id=_as_uuid(values["proposal_id"]),
        action_id=action_id,
        mode=mode,
        approval_actor=APPROVAL_ACTOR_UNRECORDED if event_type is AuditActivityType.APPROVAL_RECORDED else None,
    )


def _validate_limit(limit: int) -> None:
    """与既有 Repository 保持同一分页边界。"""
    if limit < 1 or limit > 100:
        raise ValueError("分页大小超出允许范围。")
