"""P4.2 固定 Proposal、审批、白名单执行与 Verify 应用服务。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from json import dumps
from typing import Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.application.action_execution import (
    ActionPreconditionBlockedError,
    ActionVerificationFailedError,
    ControlledActionError,
    ControlledActionExecutor,
)
from src.application.errors import (
    ActionProposalExpiredError,
    ActionProposalInvalidStateError,
    ActionProposalNotFoundError,
    IdempotencyKeyReusedError,
)
from src.domain.actions import (
    ACTION_APPROVAL_ENDPOINT,
    ACTION_EXECUTION_ENDPOINT,
    APPROVAL_VALIDITY_SECONDS,
    LOCAL_OPERATOR,
    ActionApprovalData,
    ActionApprovalDecision,
    ActionEventCursor,
    ActionEventData,
    ActionEventType,
    ActionExecutionData,
    ActionExecutionStatus,
    ActionIdempotencyKeyData,
    ActionProposalData,
    ActionProposalDetail,
    ActionProposalStatus,
    ActionVerificationData,
    ActionVerificationStatus,
    action_digest,
)
from src.domain.records import DiagnosisResultData, DiagnosisRunData, RepositoryPage
from src.infrastructure.persistence.action_repositories import (
    SqlAlchemyActionApprovalRepository,
    SqlAlchemyActionEventRepository,
    SqlAlchemyActionExecutionRepository,
    SqlAlchemyActionIdempotencyKeyRepository,
    SqlAlchemyActionProposalRepository,
    SqlAlchemyActionVerificationRepository,
)
from src.infrastructure.persistence.database import SessionFactory

TransactionT = TypeVar("TransactionT")
ACTION_IDEMPOTENCY_RETENTION = timedelta(hours=24)
ActionDecision = Literal["approve", "reject"]
COMPOUND_INDEX_ACTION_ID = "postgres.orders_compound_index_rebuild.v1"
TARGET_SERVICE_ID = "postgres-target"
TARGET_SCHEMA = "public"
TARGET_TABLE = "orders"
TARGET_COLUMNS = ("customer_id", "created_at")
TARGET_INDEX_NAME = "idx_orders_customer_created_at"
COMPOUND_INDEX_VERIFICATION_PLAN = [
    "确认受控靶场目标表存在",
    "确认固定联合索引存在且有效",
    "只读执行计划确认固定索引可用",
]


class DecideActionProposalCommand(BaseModel):
    """本地操作者的唯一审批输入。"""

    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    decision: ActionDecision
    comment: str | None = Field(default=None, max_length=500)
    idempotency_key: UUID

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        """去除可选审批备注的首尾空白。"""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class RequestActionExecutionCommand(BaseModel):
    """第二次确认执行固定 Proposal 的命令；无动作参数。"""

    model_config = ConfigDict(extra="forbid")

    proposal_id: UUID
    idempotency_key: UUID


class AcceptedActionExecution(BaseModel):
    """异步执行声明的结果。"""

    model_config = ConfigDict(extra="forbid")

    execution: ActionExecutionData
    replayed: bool


class ActionApplicationService:
    """P4.2 固定动作的审批、异步执行、Verify 和读取用例。"""

    def __init__(self, session_factory: SessionFactory, executor: ControlledActionExecutor | None) -> None:
        self._session_factory = session_factory
        self._executor = executor

    def maybe_create_proposal_in_transaction(
        self,
        session: Session,
        run: DiagnosisRunData,
        result: DiagnosisResultData,
        mode: Literal["mock", "target"] | None,
    ) -> ActionProposalData | None:
        """仅根据已持久化的固定缺索引事实生成不可编辑提案。"""
        if mode != "target":
            return None
        signal = _missing_index_signal(result)
        if signal is None:
            return None
        evidence_ids = _evidence_ids(result, signal)
        root_cause_id = _root_cause_id(result, evidence_ids, signal)
        if root_cause_id is None or len(evidence_ids) < 3:
            return None
        target = {
            "service_id": TARGET_SERVICE_ID,
            "schema": TARGET_SCHEMA,
            "table": TARGET_TABLE,
            "columns": ",".join(TARGET_COLUMNS),
            "index_name": TARGET_INDEX_NAME,
        }
        proposal = ActionProposalData(
            source_run_id=run.id,
            action_id=COMPOUND_INDEX_ACTION_ID,
            action_digest=action_digest(
                action_id=COMPOUND_INDEX_ACTION_ID,
                source_run_id=run.id,
                root_cause_id=root_cause_id,
                evidence_ids=evidence_ids,
                target=target,
                verification_plan=COMPOUND_INDEX_VERIFICATION_PLAN,
            ),
            mode="target",
            title="重建受控靶场联合索引",
            description="只对受控靶场固定目标执行代码内联合索引动作。",
            target=target,
            root_cause_id=root_cause_id,
            evidence_ids=evidence_ids,
            risk_summary="这是受控靶场结构变更；生产和预发布实例不会执行。",
            verification_plan=COMPOUND_INDEX_VERIFICATION_PLAN,
        )
        SqlAlchemyActionProposalRepository(session).add(proposal)
        self._append_event_in_transaction(
            session,
            proposal.id,
            ActionEventType.PROPOSAL_CREATED,
            {"action_id": proposal.action_id, "status": proposal.status.value, "mode": proposal.mode, "summary": "已生成受控靶场固定动作提案。"},
        )
        return proposal

    def get_by_run(self, run_id: UUID) -> ActionProposalDetail | None:
        """按来源 Run 读取提案快照；无提案并非错误。"""
        session = self._session_factory()
        try:
            proposal = SqlAlchemyActionProposalRepository(session).get_by_source_run_id(run_id)
            return self._detail(session, proposal) if proposal is not None else None
        finally:
            session.close()

    def get_detail(self, proposal_id: UUID) -> ActionProposalDetail:
        """读取 Proposal 与审批、执行、Verify 当前快照。"""
        session = self._session_factory()
        try:
            proposal = SqlAlchemyActionProposalRepository(session).get_by_id(proposal_id)
            if proposal is None:
                raise ActionProposalNotFoundError()
            return self._detail(session, proposal)
        finally:
            session.close()

    def list_events(
        self,
        proposal_id: UUID,
        cursor: ActionEventCursor | None,
        limit: int,
    ) -> RepositoryPage[ActionEventData, ActionEventCursor]:
        """分页读取已提交 action 审计事件。"""
        session = self._session_factory()
        try:
            if SqlAlchemyActionProposalRepository(session).get_by_id(proposal_id) is None:
                raise ActionProposalNotFoundError()
            return SqlAlchemyActionEventRepository(session).list_by_proposal(proposal_id, cursor, limit)
        finally:
            session.close()

    def decide(self, command: DecideActionProposalCommand) -> ActionProposalDetail:
        """原子记录批准或拒绝，并支持同请求幂等重放。"""
        fingerprint = _fingerprint({"decision": command.decision, "comment": command.comment})
        try:
            return _in_transaction(
                self._session_factory,
                lambda session: self._decide_in_transaction(session, command, fingerprint),
            )
        except IntegrityError as error:
            return self._load_decision_replay(command, fingerprint, error)

    def request_execution(self, command: RequestActionExecutionCommand) -> AcceptedActionExecution:
        """CAS 声明一次异步执行；过期状态先持久化再返回安全错误。"""
        fingerprint = _fingerprint({})
        try:
            accepted = _in_transaction(
                self._session_factory,
                lambda session: self._request_execution_in_transaction(session, command, fingerprint),
            )
        except IntegrityError as error:
            return self._load_execution_replay(command, fingerprint, error)
        if accepted is None:
            raise ActionProposalExpiredError()
        return accepted

    def execute(self, proposal_id: UUID) -> None:
        """后台执行已声明 Proposal；异常均收敛为持久化安全终态。"""
        if self._executor is None:
            self._finish_without_executor(proposal_id)
            return
        claim = self._claim_execution(proposal_id)
        if claim is None:
            return
        proposal, execution = claim
        try:
            attempt = self._executor.execute(proposal)
        except ActionPreconditionBlockedError as error:
            self._finish_blocked(proposal, execution, error)
            return
        except ControlledActionError as error:
            self._finish_failed(proposal, execution, error)
            return
        except (OSError, ValueError):
            self._finish_failed(proposal, execution, ControlledActionError())
            return
        self._record_execution_success(proposal, execution, attempt.precondition_summary, attempt.action_summary)
        self._start_verification(proposal.id)
        try:
            verification = self._executor.verify(proposal)
        except ActionVerificationFailedError as error:
            self._finish_verification_failed(proposal, execution, error)
            return
        except ControlledActionError as error:
            self._finish_verification_failed(proposal, execution, error)
            return
        except (OSError, ValueError):
            self._finish_verification_failed(proposal, execution, ActionVerificationFailedError())
            return
        self._finish_verified(proposal, execution, verification.summary, verification.facts)

    def _decide_in_transaction(
        self,
        session: Session,
        command: DecideActionProposalCommand,
        fingerprint: str,
    ) -> ActionProposalDetail:
        proposals = SqlAlchemyActionProposalRepository(session)
        idempotency = SqlAlchemyActionIdempotencyKeyRepository(session)
        existing_key = idempotency.get_by_scope(
            command.proposal_id, ACTION_APPROVAL_ENDPOINT, command.idempotency_key
        )
        if existing_key is not None:
            if existing_key.request_fingerprint != fingerprint:
                raise IdempotencyKeyReusedError("幂等键已用于不同的审批请求。")
            proposal = proposals.get_by_id(command.proposal_id)
            if proposal is None:
                raise ActionProposalNotFoundError()
            return self._detail(session, proposal)
        proposal = proposals.get_by_id(command.proposal_id)
        if proposal is None:
            raise ActionProposalNotFoundError()
        if proposal.status is not ActionProposalStatus.PENDING_APPROVAL:
            raise ActionProposalInvalidStateError()
        now = _utc_now()
        decision = ActionApprovalDecision(command.decision)
        status = (
            ActionProposalStatus.APPROVED
            if decision is ActionApprovalDecision.APPROVE
            else ActionProposalStatus.REJECTED
        )
        updated = proposals.transition_status(
            proposal.id,
            {ActionProposalStatus.PENDING_APPROVAL},
            status,
            updated_at=now,
            approved_at=now if status is ActionProposalStatus.APPROVED else None,
            expires_at=(now + timedelta(seconds=APPROVAL_VALIDITY_SECONDS))
            if status is ActionProposalStatus.APPROVED
            else None,
            completed_at=now if status is ActionProposalStatus.REJECTED else None,
        )
        if updated is None:
            raise ActionProposalInvalidStateError()
        approval = ActionApprovalData(
            proposal_id=proposal.id,
            decision=decision,
            actor=LOCAL_OPERATOR,
            comment=command.comment,
            action_digest=proposal.action_digest,
            created_at=now,
        )
        SqlAlchemyActionApprovalRepository(session).add(approval)
        idempotency.add(
            ActionIdempotencyKeyData(
                proposal_id=proposal.id,
                endpoint=ACTION_APPROVAL_ENDPOINT,
                idempotency_key=command.idempotency_key,
                request_fingerprint=fingerprint,
                resource_type="approval",
                resource_id=approval.id,
                expires_at=now + ACTION_IDEMPOTENCY_RETENTION,
                created_at=now,
            )
        )
        self._append_event_in_transaction(
            session,
            proposal.id,
            ActionEventType.APPROVAL_RECORDED,
            {
                "status": updated.status.value,
                "summary": "本地操作者已批准固定修复。"
                if decision is ActionApprovalDecision.APPROVE
                else "本地操作者已拒绝固定修复。",
            },
        )
        return self._detail(session, updated)

    def _request_execution_in_transaction(
        self,
        session: Session,
        command: RequestActionExecutionCommand,
        fingerprint: str,
    ) -> AcceptedActionExecution | None:
        proposals = SqlAlchemyActionProposalRepository(session)
        idempotency = SqlAlchemyActionIdempotencyKeyRepository(session)
        existing_key = idempotency.get_by_scope(
            command.proposal_id, ACTION_EXECUTION_ENDPOINT, command.idempotency_key
        )
        if existing_key is not None:
            if existing_key.request_fingerprint != fingerprint:
                raise IdempotencyKeyReusedError("幂等键已用于不同的执行请求。")
            execution = SqlAlchemyActionExecutionRepository(session).get_by_id(existing_key.resource_id)
            if execution is None:
                raise ActionProposalInvalidStateError()
            return AcceptedActionExecution(execution=execution, replayed=True)
        proposal = proposals.get_by_id(command.proposal_id)
        if proposal is None:
            raise ActionProposalNotFoundError()
        now = _utc_now()
        if (
            proposal.status is ActionProposalStatus.APPROVED
            and proposal.expires_at is not None
            and now >= proposal.expires_at
        ):
            proposals.transition_status(
                proposal.id,
                {ActionProposalStatus.APPROVED},
                ActionProposalStatus.EXPIRED,
                updated_at=now,
                completed_at=now,
                failure_code="APPROVAL_EXPIRED",
                failure_message="批准已过期，请重新调查后生成新提案。",
            )
            self._append_event_in_transaction(
                session,
                proposal.id,
                ActionEventType.ACTION_FAILED,
                {"status": ActionProposalStatus.EXPIRED.value, "summary": "批准已过期，未执行固定修复。"},
            )
            return None
        if proposal.status is not ActionProposalStatus.APPROVED:
            raise ActionProposalInvalidStateError()
        updated = proposals.transition_status(
            proposal.id,
            {ActionProposalStatus.APPROVED},
            ActionProposalStatus.EXECUTING,
            updated_at=now,
            execution_started_at=now,
        )
        if updated is None:
            raise ActionProposalInvalidStateError()
        execution = ActionExecutionData(proposal_id=proposal.id, mode=proposal.mode, created_at=now)
        SqlAlchemyActionExecutionRepository(session).add(execution)
        idempotency.add(
            ActionIdempotencyKeyData(
                proposal_id=proposal.id,
                endpoint=ACTION_EXECUTION_ENDPOINT,
                idempotency_key=command.idempotency_key,
                request_fingerprint=fingerprint,
                resource_type="execution",
                resource_id=execution.id,
                expires_at=now + ACTION_IDEMPOTENCY_RETENTION,
                created_at=now,
            )
        )
        self._append_event_in_transaction(
            session,
            proposal.id,
            ActionEventType.EXECUTION_REQUESTED,
            {
                "status": updated.status.value,
                "mode": proposal.mode,
                "summary": "已确认执行固定修复，等待受控执行器处理。",
            },
        )
        return AcceptedActionExecution(execution=execution, replayed=False)

    def _load_decision_replay(
        self,
        command: DecideActionProposalCommand,
        fingerprint: str,
        error: IntegrityError,
    ) -> ActionProposalDetail:
        session = self._session_factory()
        try:
            key = SqlAlchemyActionIdempotencyKeyRepository(session).get_by_scope(
                command.proposal_id, ACTION_APPROVAL_ENDPOINT, command.idempotency_key
            )
            if key is None:
                raise error
            if key.request_fingerprint != fingerprint:
                raise IdempotencyKeyReusedError("幂等键已用于不同的审批请求。")
            proposal = SqlAlchemyActionProposalRepository(session).get_by_id(command.proposal_id)
            if proposal is None:
                raise ActionProposalNotFoundError()
            return self._detail(session, proposal)
        finally:
            session.close()

    def _load_execution_replay(
        self,
        command: RequestActionExecutionCommand,
        fingerprint: str,
        error: IntegrityError,
    ) -> AcceptedActionExecution:
        session = self._session_factory()
        try:
            key = SqlAlchemyActionIdempotencyKeyRepository(session).get_by_scope(
                command.proposal_id, ACTION_EXECUTION_ENDPOINT, command.idempotency_key
            )
            if key is None:
                raise error
            if key.request_fingerprint != fingerprint:
                raise IdempotencyKeyReusedError("幂等键已用于不同的执行请求。")
            execution = SqlAlchemyActionExecutionRepository(session).get_by_id(key.resource_id)
            if execution is None:
                raise ActionProposalInvalidStateError()
            return AcceptedActionExecution(execution=execution, replayed=True)
        finally:
            session.close()

    def _claim_execution(self, proposal_id: UUID) -> tuple[ActionProposalData, ActionExecutionData] | None:
        def operation(session: Session) -> tuple[ActionProposalData, ActionExecutionData] | None:
            proposal = SqlAlchemyActionProposalRepository(session).get_by_id(proposal_id)
            execution = SqlAlchemyActionExecutionRepository(session).get_by_proposal_id(proposal_id)
            if proposal is None or execution is None or proposal.status is not ActionProposalStatus.EXECUTING:
                return None
            updated = SqlAlchemyActionExecutionRepository(session).transition_status(
                execution.id,
                {ActionExecutionStatus.QUEUED},
                ActionExecutionStatus.RUNNING,
                started_at=_utc_now(),
            )
            if updated is None:
                return None
            self._append_event_in_transaction(
                session,
                proposal.id,
                ActionEventType.EXECUTION_STARTED,
                {
                    "status": updated.status.value,
                    "mode": proposal.mode,
                    "summary": "受控执行器已开始处理固定修复。",
                },
            )
            return proposal, updated

        return _in_transaction(self._session_factory, operation)

    def _record_execution_success(
        self,
        proposal: ActionProposalData,
        execution: ActionExecutionData,
        precondition_summary: str,
        action_summary: str,
    ) -> None:
        def operation(session: Session) -> None:
            updated = SqlAlchemyActionExecutionRepository(session).transition_status(
                execution.id,
                {ActionExecutionStatus.RUNNING},
                ActionExecutionStatus.SUCCEEDED,
                finished_at=_utc_now(),
                precondition_summary=precondition_summary,
                action_summary=action_summary,
            )
            if updated is None:
                raise ActionProposalInvalidStateError()
            self._append_event_in_transaction(
                session,
                proposal.id,
                ActionEventType.PRECONDITION_CHECKED,
                {"status": "passed", "mode": proposal.mode, "summary": precondition_summary},
            )
            self._append_event_in_transaction(
                session,
                proposal.id,
                ActionEventType.EXECUTION_COMPLETED,
                {"status": "succeeded", "mode": proposal.mode, "summary": action_summary},
            )

        _in_transaction(self._session_factory, operation)

    def _start_verification(self, proposal_id: UUID) -> None:
        def operation(session: Session) -> None:
            proposals = SqlAlchemyActionProposalRepository(session)
            proposal = proposals.get_by_id(proposal_id)
            if proposal is None:
                raise ActionProposalNotFoundError()
            updated = proposals.transition_status(
                proposal_id,
                {ActionProposalStatus.EXECUTING},
                ActionProposalStatus.VERIFYING,
                updated_at=_utc_now(),
            )
            if updated is None:
                raise ActionProposalInvalidStateError()
            self._append_event_in_transaction(
                session,
                proposal_id,
                ActionEventType.VERIFICATION_STARTED,
                {
                    "status": updated.status.value,
                    "mode": proposal.mode,
                    "summary": "固定修复已提交，开始独立 Verify。",
                },
            )

        _in_transaction(self._session_factory, operation)

    def _finish_verified(
        self,
        proposal: ActionProposalData,
        execution: ActionExecutionData,
        summary: str,
        facts: dict[str, JsonValue],
    ) -> None:
        def operation(session: Session) -> None:
            now = _utc_now()
            SqlAlchemyActionVerificationRepository(session).add(
                ActionVerificationData(
                    execution_id=execution.id,
                    status=ActionVerificationStatus.VERIFIED,
                    mode=proposal.mode,
                    summary=summary,
                    facts=facts,
                    created_at=now,
                )
            )
            updated = SqlAlchemyActionProposalRepository(session).transition_status(
                proposal.id,
                {ActionProposalStatus.VERIFYING},
                ActionProposalStatus.VERIFIED,
                updated_at=now,
                completed_at=now,
            )
            if updated is None:
                raise ActionProposalInvalidStateError()
            self._append_event_in_transaction(
                session,
                proposal.id,
                ActionEventType.VERIFICATION_COMPLETED,
                {"status": updated.status.value, "mode": proposal.mode, "summary": summary},
            )

        _in_transaction(self._session_factory, operation)

    def _finish_verification_failed(
        self,
        proposal: ActionProposalData,
        execution: ActionExecutionData,
        error: ControlledActionError,
    ) -> None:
        def operation(session: Session) -> None:
            now = _utc_now()
            SqlAlchemyActionVerificationRepository(session).add(
                ActionVerificationData(
                    execution_id=execution.id,
                    status=ActionVerificationStatus.FAILED,
                    mode=proposal.mode,
                    summary=error.message,
                    facts={"verification_passed": False},
                    created_at=now,
                )
            )
            SqlAlchemyActionProposalRepository(session).transition_status(
                proposal.id,
                {ActionProposalStatus.VERIFYING},
                ActionProposalStatus.FAILED,
                updated_at=now,
                completed_at=now,
                failure_code=error.code,
                failure_message=error.message,
            )
            self._append_event_in_transaction(
                session,
                proposal.id,
                ActionEventType.ACTION_FAILED,
                {"status": ActionProposalStatus.FAILED.value, "mode": proposal.mode, "summary": error.message},
            )

        _in_transaction(self._session_factory, operation)

    def _finish_blocked(
        self,
        proposal: ActionProposalData,
        execution: ActionExecutionData,
        error: ControlledActionError,
    ) -> None:
        self._finish_execution_terminal(
            proposal,
            execution,
            ActionProposalStatus.BLOCKED,
            ActionExecutionStatus.BLOCKED,
            ActionEventType.ACTION_BLOCKED,
            error,
        )

    def _finish_failed(
        self,
        proposal: ActionProposalData,
        execution: ActionExecutionData,
        error: ControlledActionError,
    ) -> None:
        self._finish_execution_terminal(
            proposal,
            execution,
            ActionProposalStatus.FAILED,
            ActionExecutionStatus.FAILED,
            ActionEventType.ACTION_FAILED,
            error,
        )

    def _finish_execution_terminal(
        self,
        proposal: ActionProposalData,
        execution: ActionExecutionData,
        proposal_status: ActionProposalStatus,
        execution_status: ActionExecutionStatus,
        event_type: ActionEventType,
        error: ControlledActionError,
    ) -> None:
        def operation(session: Session) -> None:
            now = _utc_now()
            SqlAlchemyActionExecutionRepository(session).transition_status(
                execution.id,
                {ActionExecutionStatus.RUNNING},
                execution_status,
                finished_at=now,
                failure_code=error.code,
                failure_message=error.message,
            )
            SqlAlchemyActionProposalRepository(session).transition_status(
                proposal.id,
                {ActionProposalStatus.EXECUTING},
                proposal_status,
                updated_at=now,
                completed_at=now,
                failure_code=error.code,
                failure_message=error.message,
            )
            self._append_event_in_transaction(
                session,
                proposal.id,
                event_type,
                {"status": proposal_status.value, "mode": proposal.mode, "summary": error.message},
            )

        _in_transaction(self._session_factory, operation)

    def _finish_without_executor(self, proposal_id: UUID) -> None:
        session = self._session_factory()
        try:
            proposal = SqlAlchemyActionProposalRepository(session).get_by_id(proposal_id)
            execution = SqlAlchemyActionExecutionRepository(session).get_by_proposal_id(proposal_id)
        finally:
            session.close()
        if proposal is not None and execution is not None:
            self._finish_failed(
                proposal,
                execution,
                ControlledActionError("固定执行器当前不可用，未执行任何操作。"),
            )

    def _append_event_in_transaction(
        self,
        session: Session,
        proposal_id: UUID,
        event_type: ActionEventType,
        data: dict[str, object],
    ) -> None:
        sequence = SqlAlchemyActionProposalRepository(session).reserve_event_sequence(proposal_id)
        if sequence is None:
            raise ActionProposalNotFoundError()
        SqlAlchemyActionEventRepository(session).add(
            ActionEventData(
                proposal_id=proposal_id,
                sequence=sequence,
                type=event_type,
                occurred_at=_utc_now(),
                data=_safe_action_event_data(data),
            )
        )

    @staticmethod
    def _detail(session: Session, proposal: ActionProposalData) -> ActionProposalDetail:
        approval = SqlAlchemyActionApprovalRepository(session).get_by_proposal_id(proposal.id)
        execution = SqlAlchemyActionExecutionRepository(session).get_by_proposal_id(proposal.id)
        verification = (
            SqlAlchemyActionVerificationRepository(session).get_by_execution_id(execution.id)
            if execution is not None
            else None
        )
        return ActionProposalDetail(
            proposal=proposal,
            approval=approval,
            execution=execution,
            verification=verification,
        )


def _in_transaction(
    session_factory: SessionFactory,
    operation: Callable[[Session], TransactionT],
) -> TransactionT:
    """建立短事务，不跨越任何外部靶场调用。"""
    session = session_factory()
    try:
        value = operation(session)
        session.commit()
        return value
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _safe_action_event_data(data: dict[str, object]) -> dict[str, JsonValue]:
    """持久化 action 事件时只保留状态、模式、固定动作和简短摘要。"""
    safe: dict[str, JsonValue] = {}
    action_id = data.get("action_id")
    if isinstance(action_id, str) and 0 < len(action_id) <= 120:
        safe["action_id"] = action_id
    status = data.get("status")
    allowed_statuses = {
        "pending_approval", "approved", "rejected", "expired", "executing", "verifying",
        "verified", "blocked", "failed", "queued", "running", "succeeded", "passed",
    }
    if isinstance(status, str) and status in allowed_statuses:
        safe["status"] = status
    mode = data.get("mode")
    if mode in {"mock", "target"}:
        safe["mode"] = mode
    summary = data.get("summary")
    if isinstance(summary, str) and 0 < len(summary) <= 500:
        safe["summary"] = summary
    return safe


def _missing_index_signal(result: DiagnosisResultData) -> dict[str, JsonValue] | None:
    """读取并严格匹配结果中的固定缺索引信号。"""
    for root_cause in result.root_causes:
        raw = root_cause.get("missing_index")
        if not isinstance(raw, dict):
            continue
        if (
            raw.get("service_id") == TARGET_SERVICE_ID
            and raw.get("schema") == TARGET_SCHEMA
            and raw.get("table") == TARGET_TABLE
            and raw.get("columns") == list(TARGET_COLUMNS)
            and raw.get("index_name") == TARGET_INDEX_NAME
        ):
            return raw
    return None


def _evidence_ids(result: DiagnosisResultData, signal: dict[str, JsonValue]) -> list[UUID]:
    """只读取拥有匹配信号的根因所引用的合法证据 ID。"""
    evidence_by_id = {
        item.get("id"): item for item in result.evidence if isinstance(item.get("id"), str)
    }
    for root_cause in result.root_causes:
        if root_cause.get("missing_index") != signal:
            continue
        raw_ids = root_cause.get("evidence_ids")
        if not isinstance(raw_ids, list):
            return []
        ids: list[UUID] = []
        for raw_id in raw_ids:
            if not isinstance(raw_id, str) or raw_id not in evidence_by_id:
                return []
            try:
                ids.append(UUID(raw_id))
            except ValueError:
                return []
        return ids[:8]
    return []


def _root_cause_id(
    result: DiagnosisResultData,
    evidence_ids: list[UUID],
    signal: dict[str, JsonValue],
) -> UUID | None:
    """读取绑定缺索引信号与证据的根因 UUID。"""
    allowed_evidence = set(evidence_ids)
    for item in result.root_causes:
        if item.get("missing_index") != signal:
            continue
        raw_evidence_ids = item.get("evidence_ids")
        if not isinstance(raw_evidence_ids, list):
            continue
        try:
            linked = {UUID(value) for value in raw_evidence_ids if isinstance(value, str)}
        except ValueError:
            continue
        if not linked or not linked.issubset(allowed_evidence):
            continue
        raw_id = item.get("id")
        if not isinstance(raw_id, str):
            continue
        try:
            return UUID(raw_id)
        except ValueError:
            continue
    return None


def _fingerprint(payload: object) -> str:
    """对审批/空执行请求计算稳定幂等指纹。"""
    return sha256(
        dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    ).hexdigest()


def _utc_now() -> datetime:
    """返回 action 应用服务的 UTC 时间。"""
    return datetime.now(UTC)
