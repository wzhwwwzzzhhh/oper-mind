"""P2 会话诊断持久化边界的数据对象。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Generic, TypeVar
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationInfo, field_validator

from src.domain.diagnosis import DiagnosisSeverity, MessageRole, RunEventType, RunStatus, SessionStatus


RecordT = TypeVar("RecordT", bound=BaseModel)
CursorT = TypeVar("CursorT", bound=BaseModel)


def utc_now() -> datetime:
    """返回领域持久化对象默认使用的 UTC aware 当前时间。"""
    return datetime.now(timezone.utc)


class DomainRecord(BaseModel):
    """跨 Repository 边界传递的受控领域数据基类。"""

    model_config = ConfigDict(extra="forbid", validate_default=True)


class TimestampedRecord(DomainRecord):
    """要求所有时间字段为 UTC aware 的数据基类。"""

    @field_validator("*", mode="after")
    @classmethod
    def validate_utc_datetime(cls, value: object, info: ValidationInfo) -> object:
        """拒绝非 UTC aware 时间，避免持久化边界混入本地时间。"""
        if not info.field_name.endswith("_at") or value is None:
            return value
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None or value.utcoffset() != timezone.utc.utcoffset(value):
            raise ValueError(f"{info.field_name} 必须是 UTC aware datetime。")
        return value


class SessionData(TimestampedRecord):
    """诊断会话的 Repository 数据对象。"""

    id: UUID = Field(default_factory=uuid4)
    title: str
    status: SessionStatus = SessionStatus.ACTIVE
    environment_id: UUID | None = None
    incident_id: UUID | None = None
    service_id: str | None = Field(default=None, max_length=64)
    service_ids: tuple[str, ...] = ()
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    archived_at: datetime | None = None



class MessageData(TimestampedRecord):
    """会话消息的 Repository 数据对象。"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    run_id: UUID | None = None
    role: MessageRole
    content: str
    created_at: datetime = Field(default_factory=utc_now)


class DiagnosisRunData(TimestampedRecord):
    """诊断运行的 Repository 数据对象。"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    trace_id: UUID = Field(default_factory=uuid4)
    input_message_id: UUID
    service_id: str | None = Field(default=None, max_length=64)
    status: RunStatus = RunStatus.QUEUED
    next_event_sequence: int = Field(default=1, ge=1)
    error_code: str | None = None
    error_message: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class RunEventData(TimestampedRecord):
    """可重放 Run 事件的 Repository 数据对象。"""

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    sequence: int = Field(ge=1)
    type: RunEventType
    occurred_at: datetime = Field(default_factory=utc_now)
    data: dict[str, JsonValue]


class DiagnosisResultData(TimestampedRecord):
    """结构化诊断结果的 Repository 数据对象。"""

    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    schema_version: int = Field(default=1, ge=1)
    summary: str
    severity: DiagnosisSeverity
    confidence: float = Field(ge=0.0, le=1.0)
    root_causes: list[dict[str, JsonValue]]
    evidence: list[dict[str, JsonValue]]
    impact: dict[str, JsonValue] | None = None
    recommendations: list[dict[str, JsonValue]]
    risks: list[dict[str, JsonValue]]
    requires_approval: bool
    agent_summary: list[dict[str, JsonValue]]
    report_markdown: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class RunIdempotencyKeyData(TimestampedRecord):
    """Run 创建幂等记录的 Repository 数据对象。"""

    id: UUID = Field(default_factory=uuid4)
    session_id: UUID
    endpoint: str
    idempotency_key: UUID
    request_fingerprint: str
    run_id: UUID
    expires_at: datetime
    created_at: datetime = Field(default_factory=utc_now)


class SessionCursor(TimestampedRecord):
    """Session 固定排序查询的已解码游标。"""

    updated_at: datetime
    id: UUID


class MessageCursor(TimestampedRecord):
    """Message 固定排序查询的已解码游标。"""

    created_at: datetime
    id: UUID


class DiagnosisRunCursor(TimestampedRecord):
    """DiagnosisRun 固定排序查询的已解码游标。"""

    created_at: datetime
    id: UUID


class RunEventCursor(DomainRecord):
    """RunEvent 固定排序查询的已解码游标。"""

    sequence: int = Field(ge=1)


class RepositoryPage(DomainRecord, Generic[RecordT, CursorT]):
    """Repository 固定排序查询的一页结果。"""

    items: list[RecordT]
    next_cursor: CursorT | None = None
    has_more: bool
