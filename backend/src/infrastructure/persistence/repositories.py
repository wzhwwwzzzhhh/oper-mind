"""P2 会话诊断闭环的 SQLAlchemy Repository 实现。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, TypeVar
from uuid import UUID

from sqlalchemy import Select, and_, or_, select, update
from sqlalchemy.orm import Session

from src.domain.diagnosis import DiagnosisSeverity, MessageRole, RunEventType, RunStatus, SessionStatus
from src.domain.records import (
    DiagnosisResultData,
    DiagnosisRunCursor,
    DiagnosisRunData,
    MessageCursor,
    MessageData,
    RepositoryPage,
    RunEventCursor,
    RunEventData,
    RunIdempotencyKeyData,
    SessionCursor,
    SessionData,
)
from src.infrastructure.persistence.models import (
    DiagnosisResultRecord,
    DiagnosisRunRecord,
    MessageRecord,
    RunEventRecord,
    RunIdempotencyKeyRecord,
    SessionRecord,
)


RecordT = TypeVar("RecordT")
CursorT = TypeVar("CursorT")


def _as_utc(value: datetime | None) -> datetime | None:
    """将 SQLite 读出的无时区时间按 UTC 存储约定归一化。"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _validate_limit(limit: int) -> None:
    """拒绝非正页大小，避免生成非预期 SQL 查询。"""
    if limit < 1:
        raise ValueError("limit 必须大于等于 1。")


def _page(
    records: list[RecordT],
    limit: int,
    cursor_factory: Callable[[RecordT], CursorT],
) -> RepositoryPage[RecordT, CursorT]:
    """从 limit + 1 的固定排序查询结果构造页片段。"""
    has_more = len(records) > limit
    items = records[:limit]
    next_cursor = cursor_factory(items[-1]) if has_more and items else None
    return RepositoryPage(items=items, next_cursor=next_cursor, has_more=has_more)


class SqlAlchemySessionRepository:
    """基于 SQLAlchemy 的 Session Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, session: SessionData) -> None:
        """将会话加入调用方事务，不提交。"""
        self._session.add(
            SessionRecord(
                id=session.id,
                title=session.title,
                status=session.status.value,
                environment_id=session.environment_id,
                incident_id=session.incident_id,
                service_id=session.service_id,
                created_at=session.created_at,
                updated_at=session.updated_at,
                archived_at=session.archived_at,
            )
        )

    def get_by_id(self, session_id: UUID) -> SessionData | None:
        """按主键读取会话。"""
        record = self._session.get(SessionRecord, session_id)
        return _session_data(record) if record is not None else None

    def save(self, session: SessionData) -> bool:
        """保存已有会话，返回是否找到目标记录，不提交。"""
        record = self._session.get(SessionRecord, session.id)
        if record is None:
            return False
        record.title = session.title
        record.status = session.status.value
        record.environment_id = session.environment_id
        record.incident_id = session.incident_id
        record.service_id = session.service_id
        record.updated_at = session.updated_at
        record.archived_at = session.archived_at
        return True

    def list_page(
        self,
        cursor: SessionCursor | None,
        limit: int,
        status: SessionStatus | None = None,
    ) -> RepositoryPage[SessionData, SessionCursor]:
        """按更新时间倒序读取会话页。"""
        _validate_limit(limit)
        statement: Select[tuple[SessionRecord]] = select(SessionRecord)
        filters = []
        if status is not None:
            filters.append(SessionRecord.status == status.value)
        if cursor is not None:
            filters.append(
                or_(
                    SessionRecord.updated_at < cursor.updated_at,
                    and_(
                        SessionRecord.updated_at == cursor.updated_at,
                        SessionRecord.id < cursor.id,
                    ),
                )
            )
        if filters:
            statement = statement.where(*filters)
        records = list(
            self._session.scalars(
                statement.order_by(SessionRecord.updated_at.desc(), SessionRecord.id.desc()).limit(limit + 1)
            )
        )
        return _page(
            [_session_data(record) for record in records],
            limit,
            lambda item: SessionCursor(updated_at=item.updated_at, id=item.id),
        )


class SqlAlchemyMessageRepository:
    """基于 SQLAlchemy 的 Message Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, message: MessageData) -> None:
        """将消息加入调用方事务，不提交。"""
        self._session.add(
            MessageRecord(
                id=message.id,
                session_id=message.session_id,
                run_id=message.run_id,
                role=message.role.value,
                content=message.content,
                created_at=message.created_at,
            )
        )

    def get_by_id(self, message_id: UUID) -> MessageData | None:
        """按主键读取消息。"""
        record = self._session.get(MessageRecord, message_id)
        return _message_data(record) if record is not None else None

    def list_by_session(
        self,
        session_id: UUID,
        cursor: MessageCursor | None,
        limit: int,
    ) -> RepositoryPage[MessageData, MessageCursor]:
        """按创建时间正序读取会话消息页。"""
        _validate_limit(limit)
        statement: Select[tuple[MessageRecord]] = select(MessageRecord).where(MessageRecord.session_id == session_id)
        if cursor is not None:
            statement = statement.where(
                or_(
                    MessageRecord.created_at > cursor.created_at,
                    and_(
                        MessageRecord.created_at == cursor.created_at,
                        MessageRecord.id > cursor.id,
                    ),
                )
            )
        records = list(
            self._session.scalars(
                statement.order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc()).limit(limit + 1)
            )
        )
        return _page(
            [_message_data(record) for record in records],
            limit,
            lambda item: MessageCursor(created_at=item.created_at, id=item.id),
        )


class SqlAlchemyDiagnosisRunRepository:
    """基于 SQLAlchemy 的 DiagnosisRun Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, run: DiagnosisRunData) -> None:
        """将 Run 加入调用方事务，不提交。"""
        self._session.add(
            DiagnosisRunRecord(
                id=run.id,
                session_id=run.session_id,
                trace_id=run.trace_id,
                input_message_id=run.input_message_id,
                status=run.status.value,
                next_event_sequence=run.next_event_sequence,
                error_code=run.error_code,
                error_message=run.error_message,
                created_at=run.created_at,
                started_at=run.started_at,
                finished_at=run.finished_at,
            )
        )

    def get_by_id(self, run_id: UUID) -> DiagnosisRunData | None:
        """按主键读取 Run。"""
        record = self._session.get(DiagnosisRunRecord, run_id)
        return _diagnosis_run_data(record) if record is not None else None

    def transition_status(
        self,
        run_id: UUID,
        expected_statuses: set[RunStatus],
        status: RunStatus,
        started_at: datetime | None = None,
        finished_at: datetime | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> DiagnosisRunData | None:
        """仅在当前状态属于预期集合时更新 Run，返回更新后的值。"""
        values: dict[str, object] = {"status": status.value}
        if started_at is not None:
            values["started_at"] = started_at
        if finished_at is not None:
            values["finished_at"] = finished_at
        if error_code is not None:
            values["error_code"] = error_code
        if error_message is not None:
            values["error_message"] = error_message
        result = self._session.execute(
            update(DiagnosisRunRecord)
            .where(
                DiagnosisRunRecord.id == run_id,
                DiagnosisRunRecord.status.in_([item.value for item in expected_statuses]),
            )
            .values(**values)
            .execution_options(synchronize_session="fetch")
        )
        if result.rowcount != 1:
            return None
        record = self._session.get(DiagnosisRunRecord, run_id)
        return _diagnosis_run_data(record) if record is not None else None

    def reserve_event_sequence(self, run_id: UUID) -> int | None:
        """原子预留下一事件 sequence，返回预留值，不提交。"""
        next_sequence = self._session.scalar(
            update(DiagnosisRunRecord)
            .where(DiagnosisRunRecord.id == run_id)
            .values(next_event_sequence=DiagnosisRunRecord.next_event_sequence + 1)
            .returning(DiagnosisRunRecord.next_event_sequence)
        )
        return int(next_sequence) - 1 if next_sequence is not None else None

    def list_by_session(
        self,
        session_id: UUID,
        cursor: DiagnosisRunCursor | None,
        limit: int,
    ) -> RepositoryPage[DiagnosisRunData, DiagnosisRunCursor]:
        """按创建时间倒序读取 Session 下的 Run 页。"""
        _validate_limit(limit)
        statement: Select[tuple[DiagnosisRunRecord]] = select(DiagnosisRunRecord).where(
            DiagnosisRunRecord.session_id == session_id
        )
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
        records = list(
            self._session.scalars(
                statement.order_by(DiagnosisRunRecord.created_at.desc(), DiagnosisRunRecord.id.desc()).limit(limit + 1)
            )
        )
        return _page(
            [_diagnosis_run_data(record) for record in records],
            limit,
            lambda item: DiagnosisRunCursor(created_at=item.created_at, id=item.id),
        )


class SqlAlchemyRunEventRepository:
    """基于 SQLAlchemy 的 RunEvent Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: RunEventData) -> None:
        """将事件加入调用方事务，不提交。"""
        self._session.add(
            RunEventRecord(
                id=event.id,
                run_id=event.run_id,
                sequence=event.sequence,
                type=event.type.value,
                occurred_at=event.occurred_at,
                data=event.data,
            )
        )

    def list_by_run(
        self,
        run_id: UUID,
        cursor: RunEventCursor | None,
        limit: int,
    ) -> RepositoryPage[RunEventData, RunEventCursor]:
        """按 sequence 正序读取 Run 事件页。"""
        _validate_limit(limit)
        statement: Select[tuple[RunEventRecord]] = select(RunEventRecord).where(RunEventRecord.run_id == run_id)
        if cursor is not None:
            statement = statement.where(RunEventRecord.sequence > cursor.sequence)
        records = list(self._session.scalars(statement.order_by(RunEventRecord.sequence.asc()).limit(limit + 1)))
        return _page(
            [_run_event_data(record) for record in records],
            limit,
            lambda item: RunEventCursor(sequence=item.sequence),
        )


class SqlAlchemyDiagnosisResultRepository:
    """基于 SQLAlchemy 的 DiagnosisResult Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, result: DiagnosisResultData) -> None:
        """将结果加入调用方事务，不提交。"""
        self._session.add(
            DiagnosisResultRecord(
                id=result.id,
                run_id=result.run_id,
                schema_version=result.schema_version,
                summary=result.summary,
                severity=result.severity.value,
                confidence=result.confidence,
                root_causes=result.root_causes,
                evidence=result.evidence,
                impact=result.impact,
                recommendations=result.recommendations,
                risks=result.risks,
                requires_approval=result.requires_approval,
                agent_summary=result.agent_summary,
                report_markdown=result.report_markdown,
                created_at=result.created_at,
            )
        )

    def get_by_run_id(self, run_id: UUID) -> DiagnosisResultData | None:
        """按 Run 唯一关联读取结果。"""
        record = self._session.scalar(select(DiagnosisResultRecord).where(DiagnosisResultRecord.run_id == run_id))
        return _diagnosis_result_data(record) if record is not None else None


class SqlAlchemyRunIdempotencyKeyRepository:
    """基于 SQLAlchemy 的 Run 幂等记录 Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, key: RunIdempotencyKeyData) -> None:
        """将幂等记录加入调用方事务，不提交。"""
        self._session.add(
            RunIdempotencyKeyRecord(
                id=key.id,
                session_id=key.session_id,
                endpoint=key.endpoint,
                idempotency_key=key.idempotency_key,
                request_fingerprint=key.request_fingerprint,
                run_id=key.run_id,
                expires_at=key.expires_at,
                created_at=key.created_at,
            )
        )

    def get_by_scope(
        self,
        session_id: UUID,
        endpoint: str,
        idempotency_key: UUID,
    ) -> RunIdempotencyKeyData | None:
        """按 Session、端点和幂等键读取记录。"""
        record = self._session.scalar(
            select(RunIdempotencyKeyRecord).where(
                RunIdempotencyKeyRecord.session_id == session_id,
                RunIdempotencyKeyRecord.endpoint == endpoint,
                RunIdempotencyKeyRecord.idempotency_key == idempotency_key,
            )
        )
        return _run_idempotency_key_data(record) if record is not None else None


def _session_data(record: SessionRecord) -> SessionData:
    """将 Session ORM mapper 转换为领域数据对象。"""
    return SessionData(
        id=record.id,
        title=record.title,
        status=SessionStatus(record.status),
        environment_id=record.environment_id,
        incident_id=record.incident_id,
        service_id=record.service_id,
        created_at=_as_utc(record.created_at),
        updated_at=_as_utc(record.updated_at),
        archived_at=_as_utc(record.archived_at),
    )


def _message_data(record: MessageRecord) -> MessageData:
    """将 Message ORM mapper 转换为领域数据对象。"""
    return MessageData(
        id=record.id,
        session_id=record.session_id,
        run_id=record.run_id,
        role=MessageRole(record.role),
        content=record.content,
        created_at=_as_utc(record.created_at),
    )


def _diagnosis_run_data(record: DiagnosisRunRecord) -> DiagnosisRunData:
    """将 DiagnosisRun ORM mapper 转换为领域数据对象。"""
    return DiagnosisRunData(
        id=record.id,
        session_id=record.session_id,
        trace_id=record.trace_id,
        input_message_id=record.input_message_id,
        status=RunStatus(record.status),
        next_event_sequence=record.next_event_sequence,
        error_code=record.error_code,
        error_message=record.error_message,
        created_at=_as_utc(record.created_at),
        started_at=_as_utc(record.started_at),
        finished_at=_as_utc(record.finished_at),
    )


def _run_event_data(record: RunEventRecord) -> RunEventData:
    """将 RunEvent ORM mapper 转换为领域数据对象。"""
    return RunEventData(
        id=record.id,
        run_id=record.run_id,
        sequence=record.sequence,
        type=RunEventType(record.type),
        occurred_at=_as_utc(record.occurred_at),
        data=record.data,
    )


def _diagnosis_result_data(record: DiagnosisResultRecord) -> DiagnosisResultData:
    """将 DiagnosisResult ORM mapper 转换为领域数据对象。"""
    return DiagnosisResultData(
        id=record.id,
        run_id=record.run_id,
        schema_version=record.schema_version,
        summary=record.summary,
        severity=DiagnosisSeverity(record.severity),
        confidence=record.confidence,
        root_causes=record.root_causes,
        evidence=record.evidence,
        impact=record.impact,
        recommendations=record.recommendations,
        risks=record.risks,
        requires_approval=record.requires_approval,
        agent_summary=record.agent_summary,
        report_markdown=record.report_markdown,
        created_at=_as_utc(record.created_at),
    )


def _run_idempotency_key_data(record: RunIdempotencyKeyRecord) -> RunIdempotencyKeyData:
    """将幂等 ORM mapper 转换为领域数据对象。"""
    return RunIdempotencyKeyData(
        id=record.id,
        session_id=record.session_id,
        endpoint=record.endpoint,
        idempotency_key=record.idempotency_key,
        request_fingerprint=record.request_fingerprint,
        run_id=record.run_id,
        expires_at=_as_utc(record.expires_at),
        created_at=_as_utc(record.created_at),
    )
