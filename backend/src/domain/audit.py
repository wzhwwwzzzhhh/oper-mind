"""P8 审计活动检索的领域模型：统一审计流类型、结果派生与游标。"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from enum import StrEnum
from typing import Final
from uuid import UUID

from pydantic import Field

from src.domain.records import TimestampedRecord

APPROVAL_ACTOR_UNRECORDED: Final[str] = "未记录"


class AuditActivityKind(StrEnum):
    """审计活动的两类来源。"""

    RUN = "run"
    ACTION = "action"


class AuditActivityType(StrEnum):
    """审计类型收敛枚举：5 类 Run 派生 + 6 类里程碑 action 事件。"""

    RUN_CREATED = "run_created"
    RUN_RUNNING = "run_running"
    RUN_COMPLETED = "run_completed"
    RUN_FAILED = "run_failed"
    RUN_CANCELLED = "run_cancelled"
    PROPOSAL_CREATED = "proposal_created"
    APPROVAL_RECORDED = "approval_recorded"
    EXECUTION_COMPLETED = "execution_completed"
    VERIFICATION_COMPLETED = "verification_completed"
    ACTION_BLOCKED = "action_blocked"
    ACTION_FAILED = "action_failed"


class AuditOutcome(StrEnum):
    """审计结果收敛枚举；approval_recorded / action_failed 按事件 data.status 派生。"""

    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    BLOCKED = "blocked"
    VERIFIED = "verified"


AUDIT_RUN_TYPES: frozenset[AuditActivityType] = frozenset(
    {
        AuditActivityType.RUN_CREATED,
        AuditActivityType.RUN_RUNNING,
        AuditActivityType.RUN_COMPLETED,
        AuditActivityType.RUN_FAILED,
        AuditActivityType.RUN_CANCELLED,
    }
)

AUDIT_ACTION_TYPES: frozenset[AuditActivityType] = frozenset(
    {
        AuditActivityType.PROPOSAL_CREATED,
        AuditActivityType.APPROVAL_RECORDED,
        AuditActivityType.EXECUTION_COMPLETED,
        AuditActivityType.VERIFICATION_COMPLETED,
        AuditActivityType.ACTION_BLOCKED,
        AuditActivityType.ACTION_FAILED,
    }
)

# Run 状态（diagnosis_runs.status 字面量）→ 审计类型；未知状态不入流。
_RUN_TYPE_BY_STATUS: dict[str, AuditActivityType] = {
    "queued": AuditActivityType.RUN_CREATED,
    "running": AuditActivityType.RUN_RUNNING,
    "succeeded": AuditActivityType.RUN_COMPLETED,
    "failed": AuditActivityType.RUN_FAILED,
    "cancelled": AuditActivityType.RUN_CANCELLED,
}

# Run 审计类型 → 结果。
_RUN_OUTCOME_BY_TYPE: dict[AuditActivityType, AuditOutcome] = {
    AuditActivityType.RUN_CREATED: AuditOutcome.RUNNING,
    AuditActivityType.RUN_RUNNING: AuditOutcome.RUNNING,
    AuditActivityType.RUN_COMPLETED: AuditOutcome.SUCCEEDED,
    AuditActivityType.RUN_FAILED: AuditOutcome.FAILED,
    AuditActivityType.RUN_CANCELLED: AuditOutcome.CANCELLED,
}

# action 事件类型 → 结果；approval_recorded / action_failed 按 data.status 派生，不入本表。
_ACTION_OUTCOME_BY_TYPE: dict[AuditActivityType, AuditOutcome] = {
    AuditActivityType.PROPOSAL_CREATED: AuditOutcome.PENDING_APPROVAL,
    AuditActivityType.EXECUTION_COMPLETED: AuditOutcome.SUCCEEDED,
    AuditActivityType.VERIFICATION_COMPLETED: AuditOutcome.VERIFIED,
    AuditActivityType.ACTION_BLOCKED: AuditOutcome.BLOCKED,
}

# 结果 → 可命中的 Run 状态集合；空集表示该结果在 Run 侧不命中。
_RUN_STATUSES_BY_OUTCOME: dict[AuditOutcome, frozenset[str]] = {
    AuditOutcome.RUNNING: frozenset({"queued", "running"}),
    AuditOutcome.SUCCEEDED: frozenset({"succeeded"}),
    AuditOutcome.FAILED: frozenset({"failed"}),
    AuditOutcome.CANCELLED: frozenset({"cancelled"}),
}

# 结果 → (事件类型, 必需 data.status)；事件类型 None 表示该结果在 action 侧不命中。
_ACTION_FILTER_BY_OUTCOME: dict[AuditOutcome, tuple[AuditActivityType | None, str | None]] = {
    AuditOutcome.RUNNING: (None, None),
    AuditOutcome.SUCCEEDED: (AuditActivityType.EXECUTION_COMPLETED, None),
    AuditOutcome.FAILED: (AuditActivityType.ACTION_FAILED, "failed"),
    AuditOutcome.CANCELLED: (None, None),
    AuditOutcome.PENDING_APPROVAL: (AuditActivityType.PROPOSAL_CREATED, None),
    AuditOutcome.APPROVED: (AuditActivityType.APPROVAL_RECORDED, "approved"),
    AuditOutcome.REJECTED: (AuditActivityType.APPROVAL_RECORDED, "rejected"),
    AuditOutcome.EXPIRED: (AuditActivityType.ACTION_FAILED, "expired"),
    AuditOutcome.BLOCKED: (AuditActivityType.ACTION_BLOCKED, None),
    AuditOutcome.VERIFIED: (AuditActivityType.VERIFICATION_COMPLETED, None),
}


def audit_run_type(run_status: str) -> AuditActivityType | None:
    """把 Run 状态字面量映射为审计类型；未知状态返回 None（防御不入流）。"""
    return _RUN_TYPE_BY_STATUS.get(run_status)


def run_status_for_type(run_type: AuditActivityType) -> str:
    """把 Run 审计类型反查数据库状态字面量。"""
    for status, candidate in _RUN_TYPE_BY_STATUS.items():
        if candidate is run_type:
            return status
    raise ValueError(f"未知 Run 审计类型：{run_type}")


def run_outcome(run_type: AuditActivityType) -> AuditOutcome:
    """把 Run 审计类型映射为结果。"""
    try:
        return _RUN_OUTCOME_BY_TYPE[run_type]
    except KeyError as error:
        raise ValueError(f"非 Run 审计类型：{run_type}") from error


def action_audit_type(event_type: str) -> AuditActivityType | None:
    """把 action 事件类型映射为审计类型；瞬时事件或未知类型返回 None（不入流）。"""
    try:
        candidate = AuditActivityType(event_type)
    except ValueError:
        return None
    return candidate if candidate in AUDIT_ACTION_TYPES else None


def action_outcome(event_type: AuditActivityType, event_data: Mapping[str, object]) -> AuditOutcome:
    """把 action 事件映射为结果；approval_recorded / action_failed 按事件 data.status 派生。"""
    if event_type is AuditActivityType.APPROVAL_RECORDED:
        return (
            AuditOutcome.APPROVED
            if event_data.get("status") == "approved"
            else AuditOutcome.REJECTED
        )
    if event_type is AuditActivityType.ACTION_FAILED:
        return (
            AuditOutcome.EXPIRED
            if event_data.get("status") == "expired"
            else AuditOutcome.FAILED
        )
    try:
        return _ACTION_OUTCOME_BY_TYPE[event_type]
    except KeyError as error:
        raise ValueError(f"非 action 审计类型：{event_type}") from error


def run_statuses_for_outcome(outcome: AuditOutcome) -> frozenset[str]:
    """返回结果可命中的 Run 状态集合（空集 = Run 侧不命中）。"""
    return _RUN_STATUSES_BY_OUTCOME.get(outcome, frozenset())


def action_filter_for_outcome(outcome: AuditOutcome) -> tuple[AuditActivityType | None, str | None]:
    """返回结果可命中的 (事件类型, 必需 data.status)；事件类型 None = action 侧不命中。"""
    return _ACTION_FILTER_BY_OUTCOME.get(outcome, (None, None))


class AuditActivityCursor(TimestampedRecord):
    """统一审计流键集分页游标：两侧共用 (time desc, id desc) 全序。"""

    created_at: datetime
    id: UUID


class AuditActivityData(TimestampedRecord):
    """统一审计流的一行安全摘要；run 与 action 项共用结构，类型专属字段可空。"""

    id: UUID
    kind: AuditActivityKind
    type: AuditActivityType
    occurred_at: datetime
    service_id: str | None = Field(default=None, max_length=64)
    session_id: UUID
    session_title: str = Field(min_length=1, max_length=200)
    outcome: AuditOutcome
    summary: str | None = Field(default=None, max_length=800)
    # run 项：Run 安全摘要与修复闭环状态
    run_id: UUID | None = None
    severity: str | None = Field(default=None, max_length=20)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    proposal_status: str | None = Field(default=None, max_length=32)
    verification_status: str | None = Field(default=None, max_length=32)
    # action 项：事件锚点与审批诚实标注
    proposal_id: UUID | None = None
    action_id: str | None = Field(default=None, max_length=120)
    mode: str | None = Field(default=None, max_length=12)
    approval_actor: str | None = Field(default=None, max_length=20)
