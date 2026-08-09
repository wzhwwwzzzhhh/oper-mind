"""P4.2 action Proposal 的 SQLAlchemy Repository 实现。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, select, update
from sqlalchemy.orm import Session

from src.domain.actions import (
    ActionApprovalData,
    ActionApprovalDecision,
    ActionEventCursor,
    ActionEventData,
    ActionEventType,
    ActionExecutionData,
    ActionExecutionStatus,
    ActionIdempotencyKeyData,
    ActionProposalData,
    ActionProposalStatus,
    ActionVerificationData,
    ActionVerificationStatus,
)
from src.domain.records import RepositoryPage
from src.infrastructure.persistence.models import (
    ActionApprovalRecord,
    ActionEventRecord,
    ActionExecutionRecord,
    ActionIdempotencyKeyRecord,
    ActionProposalRecord,
    ActionVerificationRecord,
)
from src.infrastructure.persistence.repositories import _as_utc, _page, _validate_limit


class SqlAlchemyActionProposalRepository:
    """固定 Proposal 的 ORM Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, proposal: ActionProposalData) -> None:
        """加入不可编辑提案快照。"""
        self._session.add(
            ActionProposalRecord(
                id=proposal.id, source_run_id=proposal.source_run_id, action_id=proposal.action_id,
                action_digest=proposal.action_digest, status=proposal.status.value, mode=proposal.mode,
                title=proposal.title, description=proposal.description, target=proposal.target,
                root_cause_id=proposal.root_cause_id, evidence_ids=[str(item) for item in proposal.evidence_ids],
                risk_summary=proposal.risk_summary, verification_plan=proposal.verification_plan,
                next_event_sequence=1, created_at=proposal.created_at, updated_at=proposal.updated_at,
                approved_at=proposal.approved_at, expires_at=proposal.expires_at,
                execution_started_at=proposal.execution_started_at, completed_at=proposal.completed_at,
                failure_code=proposal.failure_code, failure_message=proposal.failure_message,
            )
        )

    def get_by_id(self, proposal_id: UUID) -> ActionProposalData | None:
        record = self._session.get(ActionProposalRecord, proposal_id)
        return _action_proposal_data(record) if record is not None else None

    def get_by_source_run_id(self, run_id: UUID) -> ActionProposalData | None:
        record = self._session.scalar(select(ActionProposalRecord).where(ActionProposalRecord.source_run_id == run_id))
        return _action_proposal_data(record) if record is not None else None

    def transition_status(
        self, proposal_id: UUID, expected_statuses: set[ActionProposalStatus], status: ActionProposalStatus,
        *, updated_at: datetime, approved_at: datetime | None = None, expires_at: datetime | None = None,
        execution_started_at: datetime | None = None, completed_at: datetime | None = None,
        failure_code: str | None = None, failure_message: str | None = None,
    ) -> ActionProposalData | None:
        values: dict[str, object] = {"status": status.value, "updated_at": updated_at}
        for key, value in {
            "approved_at": approved_at, "expires_at": expires_at,
            "execution_started_at": execution_started_at, "completed_at": completed_at,
            "failure_code": failure_code, "failure_message": failure_message,
        }.items():
            if value is not None:
                values[key] = value
        outcome = self._session.execute(
            update(ActionProposalRecord).where(
                ActionProposalRecord.id == proposal_id,
                ActionProposalRecord.status.in_([item.value for item in expected_statuses]),
            ).values(**values).execution_options(synchronize_session="fetch")
        )
        if outcome.rowcount != 1:
            return None
        record = self._session.get(ActionProposalRecord, proposal_id)
        return _action_proposal_data(record) if record is not None else None

    def reserve_event_sequence(self, proposal_id: UUID) -> int | None:
        next_sequence = self._session.scalar(
            update(ActionProposalRecord).where(ActionProposalRecord.id == proposal_id)
            .values(next_event_sequence=ActionProposalRecord.next_event_sequence + 1)
            .returning(ActionProposalRecord.next_event_sequence)
        )
        return int(next_sequence) - 1 if next_sequence is not None else None


class SqlAlchemyActionApprovalRepository:
    """审批记录 ORM Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, approval: ActionApprovalData) -> None:
        self._session.add(ActionApprovalRecord(
            id=approval.id, proposal_id=approval.proposal_id, decision=approval.decision.value,
            actor=approval.actor, comment=approval.comment, action_digest=approval.action_digest,
            created_at=approval.created_at,
        ))

    def get_by_proposal_id(self, proposal_id: UUID) -> ActionApprovalData | None:
        record = self._session.scalar(select(ActionApprovalRecord).where(ActionApprovalRecord.proposal_id == proposal_id))
        return _action_approval_data(record) if record is not None else None


class SqlAlchemyActionExecutionRepository:
    """固定执行记录 ORM Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, execution: ActionExecutionData) -> None:
        self._session.add(ActionExecutionRecord(
            id=execution.id, proposal_id=execution.proposal_id, mode=execution.mode,
            status=execution.status.value, precondition_summary=execution.precondition_summary,
            action_summary=execution.action_summary, failure_code=execution.failure_code,
            failure_message=execution.failure_message, created_at=execution.created_at,
            started_at=execution.started_at, finished_at=execution.finished_at,
        ))

    def get_by_proposal_id(self, proposal_id: UUID) -> ActionExecutionData | None:
        record = self._session.scalar(select(ActionExecutionRecord).where(ActionExecutionRecord.proposal_id == proposal_id))
        return _action_execution_data(record) if record is not None else None

    def get_by_id(self, execution_id: UUID) -> ActionExecutionData | None:
        record = self._session.get(ActionExecutionRecord, execution_id)
        return _action_execution_data(record) if record is not None else None

    def transition_status(
        self, execution_id: UUID, expected_statuses: set[ActionExecutionStatus], status: ActionExecutionStatus,
        *, started_at: datetime | None = None, finished_at: datetime | None = None,
        precondition_summary: str | None = None, action_summary: str | None = None,
        failure_code: str | None = None, failure_message: str | None = None,
    ) -> ActionExecutionData | None:
        values: dict[str, object] = {"status": status.value}
        for key, value in {
            "started_at": started_at, "finished_at": finished_at,
            "precondition_summary": precondition_summary, "action_summary": action_summary,
            "failure_code": failure_code, "failure_message": failure_message,
        }.items():
            if value is not None:
                values[key] = value
        outcome = self._session.execute(
            update(ActionExecutionRecord).where(
                ActionExecutionRecord.id == execution_id,
                ActionExecutionRecord.status.in_([item.value for item in expected_statuses]),
            ).values(**values).execution_options(synchronize_session="fetch")
        )
        if outcome.rowcount != 1:
            return None
        record = self._session.get(ActionExecutionRecord, execution_id)
        return _action_execution_data(record) if record is not None else None


class SqlAlchemyActionVerificationRepository:
    """Verify 记录 ORM Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, verification: ActionVerificationData) -> None:
        self._session.add(ActionVerificationRecord(
            id=verification.id, execution_id=verification.execution_id, status=verification.status.value,
            mode=verification.mode, summary=verification.summary, facts=verification.facts,
            created_at=verification.created_at,
        ))

    def get_by_execution_id(self, execution_id: UUID) -> ActionVerificationData | None:
        record = self._session.scalar(select(ActionVerificationRecord).where(ActionVerificationRecord.execution_id == execution_id))
        return _action_verification_data(record) if record is not None else None


class SqlAlchemyActionEventRepository:
    """Action 审计事件 ORM Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, event: ActionEventData) -> None:
        self._session.add(ActionEventRecord(
            id=event.id, proposal_id=event.proposal_id, sequence=event.sequence,
            type=event.type.value, occurred_at=event.occurred_at, data=event.data,
        ))

    def list_by_proposal(
        self, proposal_id: UUID, cursor: ActionEventCursor | None, limit: int
    ) -> RepositoryPage[ActionEventData, ActionEventCursor]:
        _validate_limit(limit)
        statement: Select[tuple[ActionEventRecord]] = select(ActionEventRecord).where(
            ActionEventRecord.proposal_id == proposal_id
        )
        if cursor is not None:
            statement = statement.where(ActionEventRecord.sequence > cursor.sequence)
        records = list(self._session.scalars(statement.order_by(ActionEventRecord.sequence.asc()).limit(limit + 1)))
        return _page(
            [_action_event_data(record) for record in records], limit,
            lambda item: ActionEventCursor(sequence=item.sequence),
        )


class SqlAlchemyActionIdempotencyKeyRepository:
    """Action POST 幂等键 ORM Repository。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, key: ActionIdempotencyKeyData) -> None:
        self._session.add(ActionIdempotencyKeyRecord(
            id=key.id, proposal_id=key.proposal_id, endpoint=key.endpoint,
            idempotency_key=key.idempotency_key, request_fingerprint=key.request_fingerprint,
            resource_type=key.resource_type, resource_id=key.resource_id,
            expires_at=key.expires_at, created_at=key.created_at,
        ))

    def get_by_scope(self, proposal_id: UUID, endpoint: str, idempotency_key: UUID) -> ActionIdempotencyKeyData | None:
        record = self._session.scalar(select(ActionIdempotencyKeyRecord).where(
            ActionIdempotencyKeyRecord.proposal_id == proposal_id,
            ActionIdempotencyKeyRecord.endpoint == endpoint,
            ActionIdempotencyKeyRecord.idempotency_key == idempotency_key,
        ))
        return _action_idempotency_data(record) if record is not None else None


def _action_proposal_data(record: ActionProposalRecord) -> ActionProposalData:
    return ActionProposalData(
        id=record.id, source_run_id=record.source_run_id, action_id=record.action_id,
        action_digest=record.action_digest, status=ActionProposalStatus(record.status), mode=record.mode,
        title=record.title, description=record.description, target=record.target,
        root_cause_id=record.root_cause_id, evidence_ids=[UUID(item) for item in record.evidence_ids],
        risk_summary=record.risk_summary, verification_plan=record.verification_plan,
        created_at=_as_utc(record.created_at), updated_at=_as_utc(record.updated_at),
        approved_at=_as_utc(record.approved_at), expires_at=_as_utc(record.expires_at),
        execution_started_at=_as_utc(record.execution_started_at), completed_at=_as_utc(record.completed_at),
        failure_code=record.failure_code, failure_message=record.failure_message,
    )


def _action_approval_data(record: ActionApprovalRecord) -> ActionApprovalData:
    return ActionApprovalData(
        id=record.id, proposal_id=record.proposal_id, decision=ActionApprovalDecision(record.decision),
        actor=record.actor, comment=record.comment, action_digest=record.action_digest,
        created_at=_as_utc(record.created_at),
    )


def _action_execution_data(record: ActionExecutionRecord) -> ActionExecutionData:
    return ActionExecutionData(
        id=record.id, proposal_id=record.proposal_id, mode=record.mode,
        status=ActionExecutionStatus(record.status), precondition_summary=record.precondition_summary,
        action_summary=record.action_summary, failure_code=record.failure_code,
        failure_message=record.failure_message, created_at=_as_utc(record.created_at),
        started_at=_as_utc(record.started_at), finished_at=_as_utc(record.finished_at),
    )


def _action_verification_data(record: ActionVerificationRecord) -> ActionVerificationData:
    return ActionVerificationData(
        id=record.id, execution_id=record.execution_id, status=ActionVerificationStatus(record.status),
        mode=record.mode, summary=record.summary, facts=record.facts, created_at=_as_utc(record.created_at),
    )


def _action_event_data(record: ActionEventRecord) -> ActionEventData:
    return ActionEventData(
        id=record.id, proposal_id=record.proposal_id, sequence=record.sequence,
        type=ActionEventType(record.type), occurred_at=_as_utc(record.occurred_at), data=record.data,
    )


def _action_idempotency_data(record: ActionIdempotencyKeyRecord) -> ActionIdempotencyKeyData:
    return ActionIdempotencyKeyData(
        id=record.id, proposal_id=record.proposal_id, endpoint=record.endpoint,
        idempotency_key=record.idempotency_key, request_fingerprint=record.request_fingerprint,
        resource_type=record.resource_type, resource_id=record.resource_id,
        expires_at=_as_utc(record.expires_at), created_at=_as_utc(record.created_at),
    )
