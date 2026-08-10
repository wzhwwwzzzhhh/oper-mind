"""P4.2 固定修复提案与受控执行的领域状态、记录和资格规则。"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from json import dumps
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, JsonValue

from src.domain.records import DomainRecord, TimestampedRecord, utc_now

LOCAL_OPERATOR = "local_operator"
APPROVAL_VALIDITY_SECONDS = 15 * 60
ACTION_APPROVAL_ENDPOINT = "/api/v1/action-proposals/{proposal_id}/approval"
ACTION_EXECUTION_ENDPOINT = "/api/v1/action-proposals/{proposal_id}/executions"


class ActionProposalStatus(StrEnum):
    """不可重开的固定修复提案状态。"""

    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTING = "executing"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    BLOCKED = "blocked"
    FAILED = "failed"


class ActionApprovalDecision(StrEnum):
    """本地操作者对不可编辑提案的唯一决定。"""

    APPROVE = "approve"
    REJECT = "reject"


class ActionExecutionStatus(StrEnum):
    """受控执行器内部可审计状态。"""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    BLOCKED = "blocked"
    FAILED = "failed"


class ActionVerificationStatus(StrEnum):
    """独立 Verify 的终态。"""

    VERIFIED = "verified"
    FAILED = "failed"


class ActionEventType(StrEnum):
    """持久化 action 时间线的最小事件集合。"""

    PROPOSAL_CREATED = "proposal_created"
    APPROVAL_RECORDED = "approval_recorded"
    EXECUTION_REQUESTED = "execution_requested"
    EXECUTION_STARTED = "execution_started"
    PRECONDITION_CHECKED = "precondition_checked"
    EXECUTION_COMPLETED = "execution_completed"
    VERIFICATION_STARTED = "verification_started"
    VERIFICATION_COMPLETED = "verification_completed"
    ACTION_BLOCKED = "action_blocked"
    ACTION_FAILED = "action_failed"


ActionMode = Literal["mock", "target"]
ActionIdempotencyResourceType = Literal["approval", "execution"]
ACTION_TERMINAL_STATUSES = frozenset(
    {
        ActionProposalStatus.REJECTED,
        ActionProposalStatus.EXPIRED,
        ActionProposalStatus.VERIFIED,
        ActionProposalStatus.BLOCKED,
        ActionProposalStatus.FAILED,
    }
)


class ActionProposalData(TimestampedRecord):
    """来源 Run 的不可编辑固定修复提案快照。"""

    id: UUID = Field(default_factory=uuid4)
    source_run_id: UUID
    action_id: str = Field(min_length=1, max_length=120)
    action_digest: str = Field(min_length=64, max_length=64)
    status: ActionProposalStatus = ActionProposalStatus.PENDING_APPROVAL
    mode: ActionMode
    title: str = Field(min_length=1, max_length=160)
    description: str = Field(min_length=1, max_length=500)
    target: dict[str, str]
    root_cause_id: UUID
    evidence_ids: list[UUID] = Field(min_length=3)
    risk_summary: str = Field(min_length=1, max_length=500)
    verification_plan: list[str] = Field(min_length=1, max_length=8)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    execution_started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = Field(default=None, max_length=80)
    failure_message: str | None = Field(default=None, max_length=500)


class ActionApprovalData(TimestampedRecord):
    """一次且仅一次的本地人工审批记录。"""

    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    decision: ActionApprovalDecision
    actor: str = LOCAL_OPERATOR
    comment: str | None = Field(default=None, max_length=500)
    action_digest: str = Field(min_length=64, max_length=64)
    created_at: datetime = Field(default_factory=utc_now)


class ActionExecutionData(TimestampedRecord):
    """受控执行动作的审计记录。"""

    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    mode: ActionMode
    status: ActionExecutionStatus = ActionExecutionStatus.QUEUED
    precondition_summary: str | None = Field(default=None, max_length=500)
    action_summary: str | None = Field(default=None, max_length=500)
    failure_code: str | None = Field(default=None, max_length=80)
    failure_message: str | None = Field(default=None, max_length=500)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ActionVerificationData(TimestampedRecord):
    """独立 Verify 的脱敏结果。"""

    id: UUID = Field(default_factory=uuid4)
    execution_id: UUID
    status: ActionVerificationStatus
    mode: ActionMode
    summary: str = Field(min_length=1, max_length=500)
    facts: dict[str, JsonValue]
    created_at: datetime = Field(default_factory=utc_now)


class ActionEventData(TimestampedRecord):
    """可轮询重放的 action 审计事件。"""

    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    sequence: int = Field(ge=1)
    type: ActionEventType
    occurred_at: datetime = Field(default_factory=utc_now)
    data: dict[str, JsonValue]


class ActionIdempotencyKeyData(TimestampedRecord):
    """审批或执行请求的幂等语义记录。"""

    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    endpoint: str
    idempotency_key: UUID
    request_fingerprint: str = Field(min_length=64, max_length=64)
    resource_type: ActionIdempotencyResourceType
    resource_id: UUID
    expires_at: datetime
    created_at: datetime = Field(default_factory=utc_now)


class ActionEventCursor(DomainRecord):
    """ActionEvent 固定排序读取的游标。"""

    sequence: int = Field(ge=1)


class ActionProposalDetail(DomainRecord):
    """API 读取所需的提案与关联审计快照。"""

    proposal: ActionProposalData
    approval: ActionApprovalData | None = None
    execution: ActionExecutionData | None = None
    verification: ActionVerificationData | None = None


def action_digest(
    *,
    action_id: str,
    source_run_id: UUID,
    root_cause_id: UUID,
    evidence_ids: list[UUID],
    target: dict[str, str],
    verification_plan: list[str],
) -> str:
    """对固定提案快照计算稳定 SHA-256，不包含凭据或变更语句。

    通用工具：具体动作在生成提案时显式传入自己的 action_id，
    保证同一提案内容的摘要稳定且不可被篡改。
    """
    payload = {
        "action_id": action_id,
        "evidence_ids": [str(item) for item in evidence_ids],
        "root_cause_id": str(root_cause_id),
        "source_run_id": str(source_run_id),
        "target": target,
        "verification_plan": verification_plan,
    }
    return sha256(dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
