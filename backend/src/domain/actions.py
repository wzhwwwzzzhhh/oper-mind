"""P4.2 固定修复提案与受控执行的领域状态、记录和资格规则。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
from json import dumps
from typing import Literal
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL

from pydantic import Field, JsonValue

from src.domain.diagnosis import DiagnosisSeverity
from src.domain.records import DiagnosisResultData, DomainRecord, TimestampedRecord, utc_now


ORDERS_INDEX_REPAIR_ACTION_ID = "postgres.orders.rebuild_missing_user_created_index.v1"
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
    action_id: str = ORDERS_INDEX_REPAIR_ACTION_ID
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


def get_orders_index_repair_eligibility(result: DiagnosisResultData) -> tuple[UUID, list[UUID]] | None:
    """严格重校验 P4.1 结构化事实，拒绝 Recommendation 反向授权。"""
    if result.severity is not DiagnosisSeverity.HIGH or result.confidence != 0.95:
        return None
    root_cause = next(
        (item for item in result.root_causes if item.get("title") == "订单查询缺少复合索引"),
        None,
    )
    if root_cause is None:
        return None
    root_cause_id = _as_uuid(root_cause.get("id"))
    if root_cause_id is None:
        return None
    database = _evidence_by_source(result, "database")
    logs = _evidence_by_source(result, "log")
    metric = _evidence_by_source(result, "metric")
    if database is None or logs is None or metric is None:
        return None
    database_attributes = database.get("attributes")
    log_attributes = logs.get("attributes")
    metric_attributes = metric.get("attributes")
    if not all(isinstance(item, dict) for item in (database_attributes, log_attributes, metric_attributes)):
        return None
    if database_attributes.get("target_database_confirmed") is not True:
        return None
    if database_attributes.get("target_index_exists") is not False:
        return None
    if database_attributes.get("plan_uses_seq_scan") is not True:
        return None
    if not _has_anomaly(log_attributes) or not _has_anomaly(metric_attributes):
        return None
    evidence_ids = [_as_uuid(item.get("id")) for item in (database, logs, metric)]
    if any(item is None for item in evidence_ids):
        return None
    return root_cause_id, [item for item in evidence_ids if item is not None]


def build_orders_index_repair_proposal(result: DiagnosisResultData, mode: ActionMode) -> ActionProposalData | None:
    """由满足严格前置条件的 Result 创建唯一固定提案。"""
    eligibility = get_orders_index_repair_eligibility(result)
    if eligibility is None:
        return None
    root_cause_id, evidence_ids = eligibility
    target = {"service": "order-service", "scope": "订单慢查询受控靶场"}
    verification_plan = [
        "确认目标索引存在并且固定计划使用目标索引。",
        "固定订单诊断探测恰好执行 3 次，均不得慢查询或超时。",
        "仅聚合这 3 次探测的受限日志，确认无慢查询或超时。",
    ]
    digest = action_digest(
        source_run_id=result.run_id,
        root_cause_id=root_cause_id,
        evidence_ids=evidence_ids,
        target=target,
        verification_plan=verification_plan,
    )
    return ActionProposalData(
        source_run_id=result.run_id,
        action_digest=digest,
        mode=mode,
        title="重建订单查询联合索引",
        description="对订单慢查询受控靶场执行固定的联合索引重建；不接受 SQL、表名或参数输入。",
        target=target,
        root_cause_id=root_cause_id,
        evidence_ids=evidence_ids,
        risk_summary="该操作会在专用靶场创建固定索引；执行前后均需重新校验，验证失败不会自动回滚。",
        verification_plan=verification_plan,
    )


def build_orders_index_repair_recommendation(result: DiagnosisResultData) -> dict[str, JsonValue] | None:
    """为符合条件的 P4.1 Result 添加仅用于界面入口的固定建议。"""
    eligibility = get_orders_index_repair_eligibility(result)
    if eligibility is None:
        return None
    _, evidence_ids = eligibility
    recommendation_id = uuid5(NAMESPACE_URL, f"{result.run_id}:{ORDERS_INDEX_REPAIR_ACTION_ID}")
    return {
        "id": str(recommendation_id),
        "title": "申请重建订单查询联合索引",
        "description": "已确认的固定修复需由本地操作者审批并再次确认执行。",
        "priority": "p1",
        "risk_level": "medium",
        "requires_approval": True,
        "evidence_ids": [str(item) for item in evidence_ids],
    }


def action_digest(
    *,
    source_run_id: UUID,
    root_cause_id: UUID,
    evidence_ids: list[UUID],
    target: dict[str, str],
    verification_plan: list[str],
) -> str:
    """对固定提案快照计算稳定 SHA-256，不包含凭据或 DDL。"""
    payload = {
        "action_id": ORDERS_INDEX_REPAIR_ACTION_ID,
        "evidence_ids": [str(item) for item in evidence_ids],
        "root_cause_id": str(root_cause_id),
        "source_run_id": str(source_run_id),
        "target": target,
        "verification_plan": verification_plan,
    }
    return sha256(dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()


def _evidence_by_source(result: DiagnosisResultData, source_type: str) -> dict[str, JsonValue] | None:
    return next((item for item in result.evidence if item.get("source_type") == source_type), None)


def _has_anomaly(attributes: dict[str, JsonValue]) -> bool:
    slow_query_count = attributes.get("slow_query_count")
    timeout_count = attributes.get("timeout_count")
    return (
        isinstance(slow_query_count, int)
        and not isinstance(slow_query_count, bool)
        and slow_query_count > 0
    ) or (
        isinstance(timeout_count, int)
        and not isinstance(timeout_count, bool)
        and timeout_count > 0
    )


def _as_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None
