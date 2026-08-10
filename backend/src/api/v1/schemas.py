"""P2.4 v1 API 的请求、资源与响应契约。"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, JsonValue, field_serializer, field_validator, model_validator

from src.domain.model_provider import validate_provider_base_url
from src.infrastructure.secrets import MIN_API_KEY_LENGTH


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
        return value.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ResponseMeta(ApiV1Model):
    """v1 HTTP 与 SSE 响应关联信息。"""

    request_id: UUID
    trace_id: UUID | None = None


class ModelEndpointResource(ApiV1Model):
    """单个模型端点的非敏感配置事实。"""

    provider: str
    base_url_host: str
    model: str
    status: Literal["configured", "not_configured"]


class ModelConfigResource(ApiV1Model):
    """模型配置的安全视图，不包含 API Key 或完整连接 URL。"""

    mode: Literal["mock", "real"]
    diagnostic_model: ModelEndpointResource
    judge_model: ModelEndpointResource | None = None


class ModelConfigResponse(ApiV1Model):
    """模型配置读取响应。"""

    config: ModelConfigResource
    meta: ResponseMeta


class ModelProviderResource(ApiV1Model):
    """单个 Provider 配置的安全视图；不含 API Key 明文。"""

    id: UUID
    name: str
    base_url: str
    model: str
    has_api_key: bool
    masked_tail: str | None = None
    active_endpoint: Literal["diagnostic", "judge"] | None = None
    verify_status: Literal["unknown", "ok", "failed", "timeout"]
    last_verified_at: datetime | None = None
    verify_error_code: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ModelProviderListResponse(ApiV1Model):
    """Provider 列表响应。"""

    items: list[ModelProviderResource]
    meta: ResponseMeta


class ModelProviderResponse(ApiV1Model):
    """单个 Provider 响应。"""

    provider: ModelProviderResource
    meta: ResponseMeta


class CreateModelProviderRequest(ApiV1Model):
    """新增 Provider 请求。"""

    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    api_key: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        """拒绝协议或主机不合法的 Base URL。"""
        return validate_provider_base_url(value)

    @field_validator("api_key")
    @classmethod
    def validate_api_key_length(cls, value: str | None) -> str | None:
        """API Key 若提供则必须达到最小长度。"""
        if value is not None and value != "" and len(value) < MIN_API_KEY_LENGTH:
            raise ValueError(f"API Key 长度至少需要 {MIN_API_KEY_LENGTH} 字符。")
        return value


class UpdateModelProviderRequest(ApiV1Model):
    """编辑 Provider 请求；api_key 不传=不改，空串=清空。"""

    name: str = Field(min_length=1, max_length=80)
    base_url: str = Field(min_length=1, max_length=500)
    model: str = Field(min_length=1, max_length=120)
    api_key: str | None = None

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        """拒绝协议或主机不合法的 Base URL。"""
        return validate_provider_base_url(value)

    @field_validator("api_key")
    @classmethod
    def validate_api_key_length(cls, value: str | None) -> str | None:
        """非空 API Key 必须达到最小长度。"""
        if value is not None and value != "" and len(value) < MIN_API_KEY_LENGTH:
            raise ValueError(f"API Key 长度至少需要 {MIN_API_KEY_LENGTH} 字符。")
        return value


class ActivateModelProviderRequest(ApiV1Model):
    """激活 Provider 为指定端点生效配置。"""

    endpoint: Literal["diagnostic", "judge"]


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
    service_id: str | None = Field(default=None, min_length=1, max_length=64)
    service_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class ServiceInvestigationResource(ApiV1Model):
    """静态服务暴露的固定调查入口。"""

    id: str = Field(min_length=1, max_length=80)
    title: str
    description: str
    default_query: str


class ServiceServerMetricsResource(ApiV1Model):
    """服务详情可展示的有限指标标量。

    PG 语义字段（p50_ms / p95_ms / slow_query_count / timeout_count）对 Redis 实例为 null，
    Redis 专用标量（memory_bytes / client_connections / slowlog_count）对 PG 实例为 null。
    """

    source_status: Literal["available", "unavailable", "not_configured"]
    window_size: int | None = Field(default=None, ge=0)
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    slow_query_count: int | None = Field(default=None, ge=0)
    timeout_count: int | None = Field(default=None, ge=0)
    memory_bytes: int | None = Field(default=None, ge=0)
    client_connections: int | None = Field(default=None, ge=0)
    slowlog_count: int | None = Field(default=None, ge=0)


class ServiceDatabaseResource(ApiV1Model):
    """固定数据库读取收敛后的安全状态。"""

    source_status: Literal["available", "unavailable", "not_configured"]
    signal: Literal[
        "missing_index_seq_scan_detected",
        "index_and_plan_confirmed",
        "insufficient_data",
        "no_slow_query_detected",
        "unavailable",
        "not_configured",
    ]


class ServiceSnapshotResource(ApiV1Model):
    """一次请求读取的当前有限快照。"""

    observed_at: datetime
    mode: Literal["disabled", "mock", "target"]
    availability: Literal["healthy", "unhealthy", "unavailable", "not_configured"]
    performance_signal: Literal[
        "slow_query_detected",
        "no_slow_query_detected",
        "insufficient_data",
        "unavailable",
        "not_configured",
    ]
    server_metrics: ServiceServerMetricsResource
    database: ServiceDatabaseResource


class HostMetricsResource(ApiV1Model):
    """服务所在后端主机的脱敏主机指标。

    与快照并列的兄弟字段：主机指标属于「后端所在主机 · 单主机采集」，而非服务数据库本身。
    不可用/未采集时标量为 null，不使用 0 代替缺失。
    """

    mode: Literal["mock", "target"]
    source_status: Literal["available", "unavailable"]
    observed_at: datetime
    cpu_percent: float | None = Field(default=None, ge=0.0)
    cpu_count: int | None = Field(default=None, ge=1)
    load_avg_1m: float | None = Field(default=None, ge=0.0)
    memory_total_bytes: int | None = Field(default=None, ge=0)
    memory_used_bytes: int | None = Field(default=None, ge=0)
    memory_percent: float | None = Field(default=None, ge=0.0)
    disk_used_percent: float | None = Field(default=None, ge=0.0)
    disk_top_partitions: list[HostDiskPartitionResource]
    network_connections: int | None = Field(default=None, ge=0)
    network_established: int | None = Field(default=None, ge=0)
    network_time_wait: int | None = Field(default=None, ge=0)
    abnormal_processes: list[HostProcessResource]


class HostDiskPartitionResource(ApiV1Model):
    """单个挂载点的脱敏使用信息。"""

    mount: str = Field(min_length=1, max_length=200)
    percent: float | None = Field(default=None, ge=0.0)
    used_bytes: int | None = Field(default=None, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)


class HostProcessResource(ApiV1Model):
    """异常进程的脱敏展示信息，不含命令行或凭据。"""

    name: str = Field(min_length=1, max_length=200)
    pid: int = Field(ge=1)
    cpu_percent: float | None = Field(default=None, ge=0.0)
    memory_percent: float | None = Field(default=None, ge=0.0)


class ServiceResource(ApiV1Model):
    """静态注册服务与其当前安全快照、共享主机指标。"""

    id: str = Field(min_length=1, max_length=64)
    title: str
    kind: str = Field(min_length=1, max_length=80)
    supported_investigations: list[ServiceInvestigationResource]
    action_boundary: str
    snapshot: ServiceSnapshotResource
    host_metrics: HostMetricsResource


class ServiceActivityResource(ApiV1Model):
    """服务绑定会话中 Run 与修复闭环的最小历史摘要。"""

    session_id: UUID
    session_title: str
    run_id: UUID
    run_status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    created_at: datetime
    finished_at: datetime | None = None
    summary: str | None = None
    severity: Literal["info", "low", "medium", "high", "critical"] | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    proposal_status: Literal[
        "pending_approval",
        "approved",
        "rejected",
        "expired",
        "executing",
        "verifying",
        "verified",
        "blocked",
        "failed",
    ] | None = None
    verification_status: Literal["verified", "failed"] | None = None


class CreateSessionRequest(ApiV1Model):
    """创建会话请求。"""

    title: str = Field(min_length=1, max_length=200)
    environment_id: UUID | None = None
    incident_id: UUID | None = None
    service_id: str | None = Field(default=None, min_length=1, max_length=64)
    service_ids: list[str] | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        """去除标题首尾空白。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized

    @field_validator("service_ids")
    @classmethod
    def reject_duplicate_service_ids(cls, value: list[str] | None) -> list[str] | None:
        """拒绝重复服务，避免请求体语义被静默更改。"""
        if value is not None and len(set(value)) != len(value):
            raise ValueError("service_ids 不允许重复")
        return value


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
    def require_change(self) -> UpdateSessionRequest:
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
    service_id: str | None = Field(default=None, min_length=1, max_length=64)

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
    service_id: str | None = Field(default=None, min_length=1, max_length=64)
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    result: DiagnosisResultResource | None = None
    error: RunErrorResource | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def validate_terminal_payload(self) -> DiagnosisRunResource:
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
        "run_failed", "run_cancelled", "tool_invoked",
    ]
    occurred_at: datetime
    data: dict[str, JsonValue]


class ServiceListResponse(ApiV1Model):
    """静态服务中心列表响应。"""

    items: list[ServiceResource]
    meta: ResponseMeta


class ServiceResponse(ApiV1Model):
    """单个静态服务详情响应。"""

    service: ServiceResource
    meta: ResponseMeta


class ServiceActivityListResponse(ApiV1Model):
    """服务活动 cursor 分页响应。"""

    items: list[ServiceActivityResource]
    page: CursorPage
    meta: ResponseMeta


class MonitorSampleResource(ApiV1Model):
    """历史监控样本的安全标量资源。"""

    id: UUID | None = None
    service_id: str = Field(min_length=1, max_length=64)
    observed_at: datetime
    availability: Literal["healthy", "unhealthy", "unavailable", "not_configured"]
    p50_ms: float | None = Field(default=None, ge=0.0)
    p95_ms: float | None = Field(default=None, ge=0.0)
    slow_query_count: int | None = Field(default=None, ge=0)
    timeout_count: int | None = Field(default=None, ge=0)
    memory_bytes: int | None = Field(default=None, ge=0)
    client_connections: int | None = Field(default=None, ge=0)
    slowlog_count: int | None = Field(default=None, ge=0)
    # P6 主机指标历史标量；不可用/未采样为 null，不用 0 代替缺失。
    host_cpu_percent: float | None = Field(default=None, ge=0.0)
    host_memory_percent: float | None = Field(default=None, ge=0.0)
    host_memory_bytes: int | None = Field(default=None, ge=0)
    host_disk_used_percent: float | None = Field(default=None, ge=0.0)
    performance_signal: Literal[
        "slow_query_detected", "no_slow_query_detected", "insufficient_data", "unavailable", "not_configured"
    ]
    source_status: Literal["available", "unavailable", "not_configured"]


class MonitorHistoryResponse(ApiV1Model):
    """历史趋势查询响应。"""

    service_id: str
    status: Literal["available", "not_sampled", "not_configured", "unavailable"]
    source: Literal["scheduled_sampling"]
    sample_interval_seconds: int = Field(ge=30)
    retention_hours: int = Field(ge=1)
    from_: datetime = Field(alias="from")
    to: datetime
    samples: list[MonitorSampleResource]
    meta: ResponseMeta


class MonitorTrendSummaryResource(ApiV1Model):
    """概览窗口内的趋势摘要：样本数与异常采样点计数。"""

    sample_count: int = Field(ge=0)
    anomaly_sample_count: int = Field(ge=0)


class MonitorServiceOverviewResource(ApiV1Model):
    """单个已注册服务的监控概览资源。"""

    service_id: str = Field(min_length=1, max_length=64)
    title: str
    kind: str = Field(min_length=1, max_length=80)
    connection_status: Literal["available", "unavailable", "not_configured", "not_sampled"]
    availability: Literal["healthy", "unhealthy", "unavailable", "not_configured"]
    latest_sample: MonitorSampleResource | None = None
    trend_summary: MonitorTrendSummaryResource


class MonitorOverviewResponse(ApiV1Model):
    """监控概览响应。"""

    items: list[MonitorServiceOverviewResource]
    source: Literal["scheduled_sampling"]
    sample_interval_seconds: int = Field(ge=30)
    retention_hours: int = Field(ge=1)
    meta: ResponseMeta


class SessionResponse(ApiV1Model):
    """单个会话响应。"""

    session: SessionResource
    meta: ResponseMeta


class MessageListResponse(ApiV1Model):
    """会话消息列表响应。"""

    items: list[MessageResource]
    page: CursorPage
    meta: ResponseMeta


class SendPlainMessageRequest(ApiV1Model):
    """发送普通对话消息的请求。"""

    content: str = Field(min_length=1, max_length=4000)

    @field_validator("content")
    @classmethod
    def normalize_content(cls, value: str) -> str:
        """去除内容首尾空白并拒绝纯空白消息。"""
        normalized = value.strip()
        if not normalized:
            raise ValueError("不能为空")
        return normalized


class PlainMessageResponse(ApiV1Model):
    """普通消息通道响应：user + assistant 两条消息。"""

    user_message: MessageResource
    assistant_message: MessageResource
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


class DiagnosisRunListResponse(ApiV1Model):
    """会话下 Run 的固定排序分页响应。"""

    items: list[DiagnosisRunResource]
    page: CursorPage
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


class ActionApprovalResource(ApiV1Model):
    """固定 Proposal 的本地审批记录。"""

    id: UUID
    proposal_id: UUID
    decision: Literal["approve", "reject"]
    actor: Literal["local_operator"]
    comment: str | None = None
    action_digest: str = Field(min_length=64, max_length=64)
    created_at: datetime


class ActionExecutionResource(ApiV1Model):
    """受控执行器的当前安全状态。"""

    id: UUID
    proposal_id: UUID
    mode: Literal["mock", "target"]
    status: Literal["queued", "running", "succeeded", "blocked", "failed"]
    precondition_summary: str | None = None
    action_summary: str | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ActionVerificationResource(ApiV1Model):
    """独立 Verify 的脱敏标量事实。"""

    id: UUID
    execution_id: UUID
    status: Literal["verified", "failed"]
    mode: Literal["mock", "target"]
    summary: str
    facts: dict[str, JsonValue]
    created_at: datetime


class ActionProposalResource(ApiV1Model):
    """来源 Run 的不可编辑固定修复提案。"""

    id: UUID
    source_run_id: UUID
    action_id: Literal["postgres.orders_compound_index_rebuild.v1"]
    action_digest: str = Field(min_length=64, max_length=64)
    status: Literal[
        "pending_approval", "approved", "rejected", "expired", "executing", "verifying",
        "verified", "blocked", "failed",
    ]
    mode: Literal["mock", "target"]
    title: str
    description: str
    target: dict[str, str]
    root_cause_id: UUID
    evidence_ids: list[UUID]
    risk_summary: str
    verification_plan: list[str]
    created_at: datetime
    updated_at: datetime
    approved_at: datetime | None = None
    expires_at: datetime | None = None
    execution_started_at: datetime | None = None
    completed_at: datetime | None = None
    failure_code: str | None = None
    failure_message: str | None = None
    approval: ActionApprovalResource | None = None
    execution: ActionExecutionResource | None = None
    verification: ActionVerificationResource | None = None


class ActionEventResource(ApiV1Model):
    """可轮询读取的 action 审计事件。"""

    id: UUID
    proposal_id: UUID
    sequence: int = Field(ge=1)
    type: Literal[
        "proposal_created", "approval_recorded", "execution_requested", "execution_started",
        "precondition_checked", "execution_completed", "verification_started",
        "verification_completed", "action_blocked", "action_failed",
    ]
    occurred_at: datetime
    data: dict[str, JsonValue]


class ActionApprovalRequest(ApiV1Model):
    """批准或拒绝不可编辑 Proposal 的请求。"""

    decision: Literal["approve", "reject"]
    comment: str | None = Field(default=None, max_length=500)

    @field_validator("comment")
    @classmethod
    def normalize_comment(cls, value: str | None) -> str | None:
        """清理可选的拒绝原因。"""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def validate_approval_body(self) -> ActionApprovalRequest:
        """批准不接受备注，避免把审批输入扩展成动作参数。"""
        if self.decision == "approve" and self.comment is not None:
            raise ValueError("批准请求不接受备注")
        return self


class ActionExecutionRequest(ApiV1Model):
    """第二次确认执行固定 Proposal 的空请求体。"""


class RunActionProposalResponse(ApiV1Model):
    """按来源 Run 查询的可选 Proposal。"""

    proposal: ActionProposalResource | None = None
    meta: ResponseMeta


class ActionProposalResponse(ApiV1Model):
    """单个 Proposal 安全快照。"""

    proposal: ActionProposalResource
    meta: ResponseMeta


class ActionEventListResponse(ApiV1Model):
    """Action 审计事件分页响应。"""

    items: list[ActionEventResource]
    page: CursorPage
    meta: ResponseMeta


class ActionExecutionResponse(ApiV1Model):
    """异步执行声明响应。"""

    execution: ActionExecutionResource
    meta: ResponseMeta


class KnowledgeDocumentResource(ApiV1Model):
    """知识库文档清单条目：标题 + 受管目录内相对 posix 路径。"""

    title: str
    relative_path: str


class KnowledgeSearchHitResource(ApiV1Model):
    """知识库检索命中项：标题 + 相对路径 + 命中片段。"""

    title: str
    relative_path: str
    snippet_count: int
    title_hit: bool
    snippets: list[str]


class KnowledgeDocumentDetailResource(ApiV1Model):
    """知识库文档详情：标题 + 相对路径 + 脱敏正文。"""

    title: str
    relative_path: str
    content: str


class KnowledgeListResponse(ApiV1Model):
    """知识库文档列表响应（诚实状态：not_configured/empty/ok）。"""

    status: Literal["not_configured", "empty", "ok"]
    items: list[KnowledgeDocumentResource]
    meta: ResponseMeta


class KnowledgeSearchResponse(ApiV1Model):
    """知识库检索响应（诚实状态：not_configured/empty/no_match/ok）。"""

    status: Literal["not_configured", "empty", "no_match", "ok"]
    query: str
    items: list[KnowledgeSearchHitResource]
    meta: ResponseMeta


class KnowledgeDocumentResponse(ApiV1Model):
    """知识库文档详情响应（诚实状态：not_configured/ok）。"""

    status: Literal["not_configured", "ok"]
    document: KnowledgeDocumentDetailResource | None = None
    meta: ResponseMeta
