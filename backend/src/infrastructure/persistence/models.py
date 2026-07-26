"""P2 会话诊断闭环的 SQLAlchemy ORM mapper。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint, Uuid
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
        Index("ix_sessions_updated_at_id", "updated_at", "id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default=SessionStatus.ACTIVE.value)
    environment_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    incident_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
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
            "'run_succeeded', 'run_failed', 'run_cancelled')",
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
