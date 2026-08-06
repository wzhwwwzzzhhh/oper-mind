"""P2 会话诊断闭环的 SQLAlchemy ORM mapper。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from src.domain.diagnosis import MessageRole, RunEventType, RunStatus, SessionStatus
from src.infrastructure.persistence.database import Base


def utc_now() -> datetime:
    """返回用于应用元数据的 UTC aware 当前时间。"""
    return datetime.now(timezone.utc)


class SessionRecord(Base):
    """可归档的诊断会话。"""

    __tablename__ = "sessions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'archived')",
            name="session_status_valid",
        ),
        CheckConstraint(
            "service_id IS NULL OR service_id IN ('postgres-production', 'postgres-staging')",
            name="session_service_id_valid",
        ),
        Index("ix_sessions_updated_at_id", "updated_at", "id"),
        Index("ix_sessions_service_updated_at_id", "service_id", "updated_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SessionStatus.ACTIVE.value)
    environment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    incident_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    service_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class MessageRecord(Base):
    """会话中的用户、助手或系统消息。"""

    __tablename__ = "messages"
    __table_args__ = (
        CheckConstraint(
            "role IN ('user', 'assistant', 'system')",
            name="message_role_valid",
        ),
        Index("ix_messages_session_created_at_id", "session_id", "created_at", "id"),
        Index("ix_messages_run_id", "run_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # run_id 不建物理外键，避免 input_message_id 与助手消息关联形成循环 DDL；P2.3 负责同 Session 校验。
    run_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DiagnosisRunRecord(Base):
    """一次可追踪、可恢复的诊断执行。"""

    __tablename__ = "diagnosis_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'cancelled')",
            name="diagnosis_run_status_valid",
        ),
        CheckConstraint("next_event_sequence >= 1", name="diagnosis_run_next_sequence_positive"),
        UniqueConstraint("input_message_id", name="diagnosis_run_input_message_unique"),
        Index("ix_diagnosis_runs_session_created_at_id", "session_id", "created_at", "id"),
        Index("ix_diagnosis_runs_service_created_at_id", "service_id", "created_at", "id"),
        Index("ix_diagnosis_runs_trace_id", "trace_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    trace_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, default=uuid4)
    input_message_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("messages.id", ondelete="RESTRICT"),
        nullable=False,
    )
    service_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=RunStatus.QUEUED.value)
    next_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunEventRecord(Base):
    """按 sequence 持久化并可经 SSE 重放的运行事件。"""

    __tablename__ = "run_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="run_event_sequence_positive"),
        CheckConstraint(
            "type IN ('run_queued', 'run_started', 'route_decided', 'agent_start', "
            "'agent_done', 'conflict_checked', 'debate_round', 'report', 'reflection', "
            "'run_succeeded', 'run_failed', 'run_cancelled', 'tool_invoked')",
            name="run_event_type_valid",
        ),
        UniqueConstraint("run_id", "sequence", name="run_event_sequence_unique"),
        Index("ix_run_events_run_sequence", "run_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class DiagnosisResultRecord(Base):
    """成功 Run 的最终结构化诊断事实。"""

    __tablename__ = "diagnosis_results"
    __table_args__ = (
        CheckConstraint(
            "severity IN ('info', 'low', 'medium', 'high', 'critical')",
            name="diagnosis_result_severity_valid",
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="diagnosis_result_confidence_range"),
        CheckConstraint("schema_version >= 1", name="diagnosis_result_schema_version_positive"),
        UniqueConstraint("run_id", name="diagnosis_result_run_unique"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float] = mapped_column(nullable=False)
    root_causes: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    impact: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    risks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    requires_approval: Mapped[bool] = mapped_column(Boolean, nullable=False)
    agent_summary: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    report_markdown: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RunIdempotencyKeyRecord(Base):
    """Run 创建请求的幂等语义记录。"""

    __tablename__ = "run_idempotency_keys"
    __table_args__ = (
        UniqueConstraint(
            "session_id",
            "endpoint",
            "idempotency_key",
            name="run_idempotency_scope_unique",
        ),
        CheckConstraint("expires_at > created_at", name="run_idempotency_expiry_after_created"),
        Index("ix_run_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("sessions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("diagnosis_runs.id", ondelete="RESTRICT"),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ActionProposalRecord(Base):
    """P4.2 来源 Run 的不可编辑固定修复提案。"""

    __tablename__ = "action_proposals"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending_approval', 'approved', 'rejected', 'expired', 'executing', 'verifying', 'verified', 'blocked', 'failed')",
            name="action_proposal_status_valid",
        ),
        CheckConstraint("mode IN ('mock', 'target')", name="action_proposal_mode_valid"),
        CheckConstraint("next_event_sequence >= 1", name="action_proposal_next_sequence_positive"),
        UniqueConstraint("source_run_id", name="action_proposal_source_run_unique"),
        Index("ix_action_proposals_status_created_at", "status", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    source_run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("diagnosis_runs.id", ondelete="RESTRICT"), nullable=False
    )
    action_id: Mapped[str] = mapped_column(String(160), nullable=False)
    action_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    target: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    root_cause_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    evidence_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    risk_summary: Mapped[str] = mapped_column(Text, nullable=False)
    verification_plan: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    next_event_sequence: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    execution_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ActionApprovalRecord(Base):
    """一次且仅一次的本地审批快照。"""

    __tablename__ = "action_approvals"
    __table_args__ = (
        CheckConstraint("decision IN ('approve', 'reject')", name="action_approval_decision_valid"),
        CheckConstraint("actor = 'local_operator'", name="action_approval_local_actor"),
        UniqueConstraint("proposal_id", name="action_approval_proposal_unique"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("action_proposals.id", ondelete="RESTRICT"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(12), nullable=False)
    actor: Mapped[str] = mapped_column(String(80), nullable=False)
    comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ActionExecutionRecord(Base):
    """白名单执行声明与最终安全摘要。"""

    __tablename__ = "action_executions"
    __table_args__ = (
        CheckConstraint("mode IN ('mock', 'target')", name="action_execution_mode_valid"),
        CheckConstraint("status IN ('queued', 'running', 'succeeded', 'blocked', 'failed')", name="action_execution_status_valid"),
        UniqueConstraint("proposal_id", name="action_execution_proposal_unique"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("action_proposals.id", ondelete="RESTRICT"), nullable=False
    )
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    precondition_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    action_summary: Mapped[str | None] = mapped_column(String(500), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ActionVerificationRecord(Base):
    """独立 Verify 的脱敏标量事实。"""

    __tablename__ = "action_verifications"
    __table_args__ = (
        CheckConstraint("status IN ('verified', 'failed')", name="action_verification_status_valid"),
        CheckConstraint("mode IN ('mock', 'target')", name="action_verification_mode_valid"),
        UniqueConstraint("execution_id", name="action_verification_execution_unique"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    execution_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("action_executions.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    mode: Mapped[str] = mapped_column(String(12), nullable=False)
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    facts: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ActionEventRecord(Base):
    """用于轮询读取的 action 审计事件。"""

    __tablename__ = "action_events"
    __table_args__ = (
        CheckConstraint("sequence >= 1", name="action_event_sequence_positive"),
        CheckConstraint(
            "type IN ('proposal_created', 'approval_recorded', 'execution_requested', 'execution_started', "
            "'precondition_checked', 'execution_completed', 'verification_started', 'verification_completed', "
            "'action_blocked', 'action_failed')",
            name="action_event_type_valid",
        ),
        UniqueConstraint("proposal_id", "sequence", name="action_event_sequence_unique"),
        Index("ix_action_events_proposal_sequence", "proposal_id", "sequence"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("action_proposals.id", ondelete="RESTRICT"), nullable=False
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(40), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class ActionIdempotencyKeyRecord(Base):
    """审批和执行请求的幂等键。"""

    __tablename__ = "action_idempotency_keys"
    __table_args__ = (
        CheckConstraint("resource_type IN ('approval', 'execution')", name="action_idempotency_resource_type_valid"),
        CheckConstraint("expires_at > created_at", name="action_idempotency_expiry_after_created"),
        UniqueConstraint("proposal_id", "endpoint", "idempotency_key", name="action_idempotency_scope_unique"),
        Index("ix_action_idempotency_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("action_proposals.id", ondelete="RESTRICT"), nullable=False
    )
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(16), nullable=False)
    resource_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class ServiceMonitorSampleRecord(Base):
    """定时采样留下的服务脱敏标量历史。"""

    __tablename__ = "service_monitor_samples"
    __table_args__ = (
        CheckConstraint(
            "availability IN ('healthy', 'unhealthy', 'unavailable', 'not_configured')",
            name="monitor_sample_availability_valid",
        ),
        CheckConstraint(
            "performance_signal IN ('slow_query_detected', 'no_slow_query_detected', 'insufficient_data', 'unavailable', 'not_configured')",
            name="monitor_sample_performance_signal_valid",
        ),
        CheckConstraint(
            "source_status IN ('available', 'unavailable', 'not_configured')",
            name="monitor_sample_source_status_valid",
        ),
        CheckConstraint("p50_ms IS NULL OR p50_ms >= 0", name="monitor_sample_p50_nonnegative"),
        CheckConstraint("p95_ms IS NULL OR p95_ms >= 0", name="monitor_sample_p95_nonnegative"),
        CheckConstraint("slow_query_count IS NULL OR slow_query_count >= 0", name="monitor_sample_slow_count_nonnegative"),
        CheckConstraint("timeout_count IS NULL OR timeout_count >= 0", name="monitor_sample_timeout_count_nonnegative"),
        CheckConstraint("memory_bytes IS NULL OR memory_bytes >= 0", name="monitor_sample_memory_bytes_nonnegative"),
        CheckConstraint("client_connections IS NULL OR client_connections >= 0", name="monitor_sample_client_connections_nonnegative"),
        CheckConstraint("slowlog_count IS NULL OR slowlog_count >= 0", name="monitor_sample_slowlog_count_nonnegative"),
        Index("ix_service_monitor_samples_service_observed_at", "service_id", "observed_at"),
        Index("ix_service_monitor_samples_observed_at", "observed_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    service_id: Mapped[str] = mapped_column(String(64), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    availability: Mapped[str] = mapped_column(String(24), nullable=False)
    p50_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    p95_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    slow_query_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    timeout_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    memory_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    client_connections: Mapped[int | None] = mapped_column(Integer, nullable=True)
    slowlog_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    performance_signal: Mapped[str] = mapped_column(String(40), nullable=False)
    source_status: Mapped[str] = mapped_column(String(24), nullable=False)
