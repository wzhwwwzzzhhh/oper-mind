"""P2.4 v1 API 的请求、资源与响应契约。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, field_validator, model_validator


class ApiV1Model(BaseModel):
    """v1 对外模型基类，拒绝未约定字段并统一输出 UTC Z 时间。"""

    model_config = ConfigDict(extra="forbid")

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_datetime(self, value: object) -> object:
        """将所有 datetime 规范为 UTC ISO 8601 Z 字符串。"""
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            raise ValueError("对外时间必须是 UTC aware datetime。")
        return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ResponseMeta(ApiV1Model):
    """v1 HTTP 与 SSE 响应关联信息。"""

    request_id: UUID
    trace_id: UUID | None = None


class CursorPage(ApiV1Model):
    """固定排序列表的 cursor 分页信息。"""

    next_cursor: str | None = None
    has_more: bool


class FieldIssue(ApiV1Model):
    """可安全展示的字段校验问题。"""

    field: str
    reason: str


class ApiError(ApiV1Model):
    """安全错误内容。"""

    code: str
    message: str
    details: list[FieldIssue] | None = None


class ErrorEnvelope(ApiV1Model):
    """v1 错误响应包络。"""

    error: ApiError
    meta: ResponseMeta


class SessionResource(ApiV1Model):
    """诊断会话资源。"""

    id: UUID
    title: str
    status: Literal["active", "archived"]
    environment_id: UUID | None = None
    incident_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class CreateSessionRequest(ApiV1Model):
    """创建会话请求。"""

    title: str = Field(min_length=1, max_length=200)
    environment_id: UUID | None = None
    incident_id: UUID | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去除标题首尾空白。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


class UpdateSessionRequest(ApiV1Model):
    """更新会话标题或逻辑归档状态的请求。"""

    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "archived"] | None = None

    @field_validator("title")
    @classmethod
    def normalize_optional_title(cls, value: str | None) -> str | None:
        """拒绝纯空白标题。"""
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "UpdateSessionRequest":
        """避免无语义 PATCH。"""
        if self.title is None and self.status is None:
            raise ValueError("至少提供一个可更新字段")
        return self


class MessageResource(ApiV1Model):
    """会话消息资源。"""

    id: UUID
    session_id: UUID
    run_id: UUID | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class EvidenceResource(ApiV1Model):
    """经安全审查的结构化证据。"""

    id: UUID
    source_type: Literal["tool", "log", "metric", "database", "agent", "user"]
    source_name: str
    title: str
    summary: str
    locator: str | None = None
    observed_at: datetime | None = None
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RootCauseResource(ApiV1Model):
    """结构化根因。"""

    id: UUID
    title: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(default_factory=list)


class ImpactResource(ApiV1Model):
    """影响范围。"""

    summary: str
    affected_services: list[str] = Field(default_factory=list)
    affected_scope: str | None = None


class RecommendationResource(ApiV1Model):
    """诊断建议。"""

    id: UUID
    title: str
    description: str
    priority: Literal["p0", "p1", "p2", "p3"]
    risk_level: Literal["none", "low", "medium", "high", "critical"]
    requires_approval: bool
    evidence_ids: list[UUID] = Field(default_factory=list)


class RiskResource(ApiV1Model):
    """诊断风险。"""

    id: UUID
    level: Literal["low", "medium", "high", "critical"]
    summary: str
    mitigation: str | None = None


class AgentSummaryResource(ApiV1Model):
    """Agent 运行摘要。"""

    agent: str
    status: Literal["completed", "skipped", "failed"]
    summary: str
    duration_ms: int | None = Field(default=None, ge=0)


class DiagnosisResultResource(ApiV1Model):
    """成功 Run 的已校验结构化结果。"""

    id: UUID
    run_id: UUID
    summary: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)
    root_causes: list[RootCauseResource]
    evidence: list[EvidenceResource]
    impact: ImpactResource | None = None
    recommendations: list[RecommendationResource]
    risks: list[RiskResource]
    requires_approval: bool
    agent_summary: list[AgentSummaryResource]
    report_markdown: str | None = None
    created_at: datetime


class CreateRunRequest(ApiV1Model):
    """受理诊断 Run 的请求。"""

    query: str = Field(min_length=1, max_length=4000)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        """去除问题首尾空白。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


class RunErrorResource(ApiV1Model):
    """失败 Run 的安全错误。"""

    code: str
    message: str


class DiagnosisRunResource(ApiV1Model):
    """诊断 Run 资源。"""

    id: UUID
    session_id: UUID
    trace_id: UUID
    input_message_id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    result: DiagnosisResultResource | None = None
    error: RunErrorResource | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> "DiagnosisRunResource":
        """保持 Result 与 Error 的终态语义，拒绝不一致的持久化数据。"""
        if self.status == "succeeded" and self.result is None:
            raise ValueError("成功 Run 缺少结构化结果")
        if self.status == "failed" and self.error is None:
            raise ValueError("失败 Run 缺少安全错误")
        if self.status not in {"succeeded", "failed"} and (self.result is not None or self.error is not None):
            raise ValueError("非终态 Run 不得携带结果或错误")
        return self


class RunEventResource(ApiV1Model):
    """可持久化且可重放的 Run 事件。"""

    id: UUID
    run_id: UUID
    sequence: int = Field(ge=1)
    type: Literal[
        "run_queued", "run_started", "route_decided", "agent_start", "agent_done",
        "conflict_checked", "debate_round", "report", "reflection", "run_succeeded",
        "run_failed", "run_cancelled",
    ]
    occurred_at: datetime
    data: dict[str, JsonValue]


class SessionResponse(ApiV1Model):
    """单个会话响应。"""

    session: SessionResource
    meta: ResponseMeta


class MessageListResponse(ApiV1Model):
    """会话消息列表响应。"""

    items: list[MessageResource]
    page: CursorPage
    meta: ResponseMeta


class SessionListResponse(ApiV1Model):
    """会话列表响应。"""

    items: list[SessionResource]
    page: CursorPage
    meta: ResponseMeta


class RunResponse(ApiV1Model):
    """单个 Run 响应。"""

    run: DiagnosisRunResource
    meta: ResponseMeta


class RunEventListResponse(ApiV1Model):
    """Run 事件列表响应。"""

    items: list[RunEventResource]
    page: CursorPage
    meta: ResponseMeta


class RunEventEnvelope(ApiV1Model):
    """SSE 单条 RunEvent 数据包。"""

    event: RunEventResource
    meta: ResponseMeta
