# OperMind API v1 契约草案

> 日期：2026-07-25　|　状态：草案，供 P1/P2 实现　|　范围：单租户 MVP、文档与类型草案

## 1. 契约原则

- 所有新产品接口使用 `/api/v1`；现有 `/diagnose` 与 `/diagnose/stream` 不重定向、不改响应体，继续作为阶段一演示兼容接口。
- 单租户 MVP 不传递 `tenant_id`、组织或复杂 RBAC 字段；后续多租户必须通过 API 与持久化迁移显式加入，不能复用隐式全局状态。
- 所有资源主键（包括 `RunEvent.id`）、`request_id`、`trace_id`、幂等键均为 RFC 4122 UUID 字符串。实现默认生成 UUID v4。
- 所有时间为 UTC ISO 8601 字符串，必须以 `Z` 结尾，例如 `2026-07-25T12:34:56.789Z`。
- 所有列表使用 cursor 分页，不暴露 offset。cursor 是服务端不透明字符串，客户端只能原样回传。
- `DiagnosisResult` 是 Run 成功后的最终结构化事实；Markdown 仅为 `report_markdown` 展示补充，不能替代任何结构化字段。
- 所有对外错误使用安全错误码与通用信息，不返回内部异常、模型配置、连接串、凭据或原始敏感证据。

## 2. 通用元数据、分页与错误体

### 2.1 响应元数据

每个 JSON 成功或失败响应都包含 `meta`。HTTP 同时返回 `X-Request-Id`；带 Run 的响应还返回 `X-Trace-Id`。

```json
{
  "meta": {
    "request_id": "0d72e68c-c5b7-4cfb-9006-2f9b8c81f2ce",
    "trace_id": "f5eae0de-6635-4cac-8e21-33c8c664c96d"
  }
}
```

- `request_id`：一次 HTTP 请求的关联 ID。客户端可选发送有效 UUID 的 `X-Request-Id`；服务端接受后回显，否则生成新值。
- `trace_id`：一次 `DiagnosisRun` 的稳定诊断链路 ID。创建 Run 时生成，之后查询该 Run、事件列表与 SSE 均返回同一值；与 Run 无关的请求可省略。

### 2.2 资源元数据与列表响应

所有持久化资源至少有 `id`、`created_at`；可变资源另有 `updated_at`。`GET` 列表统一返回：

```json
{
  "items": [],
  "page": {
    "next_cursor": null,
    "has_more": false
  },
  "meta": {
    "request_id": "0d72e68c-c5b7-4cfb-9006-2f9b8c81f2ce"
  }
}
```

请求参数：`cursor` 可选，`limit` 可选，默认 `20`、最大 `100`。排序由端点固定并在端点表声明；客户端不得从 cursor 推断或构造排序条件。

实现要求：Pydantic `datetime` 的默认 JSON 序列化可能产生 `+00:00`，P1 必须通过统一序列化器或字段序列化确保对外 JSON 使用 `Z`；数据库内部时间同样以 UTC 保存。

### 2.3 统一错误体

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数不合法",
    "details": [
      {
        "field": "query",
        "reason": "不能为空"
      }
    ]
  },
  "meta": {
    "request_id": "0d72e68c-c5b7-4cfb-9006-2f9b8c81f2ce",
    "trace_id": "f5eae0de-6635-4cac-8e21-33c8c664c96d"
  }
}
```

`details` 仅用于可安全展示的字段校验或冲突说明；未知内部错误不返回 `details`。既有阶段一 `ErrorResponse` 保持兼容，不被本草案修改。

## 3. Pydantic 类型草案

以下是 P1/P2 建议新增的产品契约类型，**不是本 Step 创建的 Python 源码**。所有模型默认 `extra="forbid"`；JSON 字段名与 TypeScript 草案一致。

```python
from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ApiV1Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ResponseMeta(ApiV1Model):
    request_id: UUID
    trace_id: UUID | None = None


class CursorPage(ApiV1Model):
    next_cursor: str | None = None
    has_more: bool


class FieldIssue(ApiV1Model):
    field: str
    reason: str


class ApiError(ApiV1Model):
    code: str
    message: str
    details: list[FieldIssue] | None = None


class Session(ApiV1Model):
    id: UUID
    title: str
    status: Literal["active", "archived"]
    environment_id: UUID | None = None
    incident_id: UUID | None = None
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None = None


class CreateSessionRequest(ApiV1Model):
    title: str = Field(min_length=1, max_length=200)
    environment_id: UUID | None = None
    incident_id: UUID | None = None


class UpdateSessionRequest(ApiV1Model):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    status: Literal["active", "archived"] | None = None


class Message(ApiV1Model):
    id: UUID
    session_id: UUID
    run_id: UUID | None = None
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class Evidence(ApiV1Model):
    id: UUID
    source_type: Literal["tool", "log", "metric", "database", "agent", "user"]
    source_name: str
    title: str
    summary: str
    locator: str | None = None
    observed_at: datetime | None = None
    attributes: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class RootCause(ApiV1Model):
    id: UUID
    title: str
    summary: str
    confidence: float = Field(ge=0.0, le=1.0)
    evidence_ids: list[UUID] = Field(default_factory=list)


class Impact(ApiV1Model):
    summary: str
    affected_services: list[str] = Field(default_factory=list)
    affected_scope: str | None = None


class Recommendation(ApiV1Model):
    id: UUID
    title: str
    description: str
    priority: Literal["p0", "p1", "p2", "p3"]
    risk_level: Literal["none", "low", "medium", "high", "critical"]
    requires_approval: bool
    evidence_ids: list[UUID] = Field(default_factory=list)


class Risk(ApiV1Model):
    id: UUID
    level: Literal["low", "medium", "high", "critical"]
    summary: str
    mitigation: str | None = None


class AgentSummary(ApiV1Model):
    agent: str
    status: Literal["completed", "skipped", "failed"]
    summary: str
    duration_ms: int | None = Field(default=None, ge=0)


class DiagnosisResult(ApiV1Model):
    id: UUID
    run_id: UUID
    summary: str
    severity: Literal["info", "low", "medium", "high", "critical"]
    confidence: float = Field(ge=0.0, le=1.0)
    root_causes: list[RootCause]
    evidence: list[Evidence]
    impact: Impact | None = None
    recommendations: list[Recommendation]
    risks: list[Risk]
    requires_approval: bool
    agent_summary: list[AgentSummary]
    report_markdown: str | None = None
    created_at: datetime


class CreateRunRequest(ApiV1Model):
    query: str = Field(min_length=1, max_length=4000)


class RunError(ApiV1Model):
    code: str
    message: str


class DiagnosisRun(ApiV1Model):
    id: UUID
    session_id: UUID
    trace_id: UUID
    input_message_id: UUID
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    result: DiagnosisResult | None = None
    error: RunError | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DiagnosisRunListResponse(ApiV1Model):
    items: list[DiagnosisRun]
    page: CursorPage
    meta: ResponseMeta

class RunEvent(ApiV1Model):
    id: UUID
    run_id: UUID
    sequence: int = Field(ge=1)
    type: Literal[
        "run_queued", "run_started", "route_decided", "agent_start",
        "agent_done", "conflict_checked", "debate_round", "report",
        "reflection", "run_succeeded", "run_failed", "run_cancelled",
    ]
    occurred_at: datetime
    data: dict[str, object]


class RunEventEnvelope(ApiV1Model):
    event: RunEvent
    meta: ResponseMeta
```

约束：`Evidence.attributes` 只包含已脱敏、可展示的标量值；原始日志、SQL 文本、连接信息和工具原始返回不得无审查地放入其中。`DiagnosisResult.root_causes`、`recommendations`、`risks`、`agent_summary` 可以为空列表，但 `summary`、`severity`、`confidence`、`requires_approval` 必须存在。Run 只有 `succeeded` 时才有 `result`，只有 `failed` 时才有 `error`。

## 4. TypeScript 对应草案

```ts
export type Uuid = string;
export type UtcDateTime = string;

export interface ResponseMeta {
  request_id: Uuid;
  trace_id?: Uuid;
}

export interface CursorPage {
  next_cursor: string | null;
  has_more: boolean;
}

export interface FieldIssue {
  field: string;
  reason: string;
}

export interface ApiError {
  code: string;
  message: string;
  details?: FieldIssue[] | null;
}

export interface CreateSessionRequest {
  title: string;
  environment_id?: Uuid | null;
  incident_id?: Uuid | null;
}

export interface UpdateSessionRequest {
  title?: string;
  status?: "active" | "archived";
}

export interface Session {
  id: Uuid;
  title: string;
  status: "active" | "archived";
  environment_id: Uuid | null;
  incident_id: Uuid | null;
  created_at: UtcDateTime;
  updated_at: UtcDateTime;
  archived_at: UtcDateTime | null;
}

export interface Message {
  id: Uuid;
  session_id: Uuid;
  run_id: Uuid | null;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: UtcDateTime;
}

export interface CreateRunRequest {
  query: string;
}

export interface Evidence {
  id: Uuid;
  source_type: "tool" | "log" | "metric" | "database" | "agent" | "user";
  source_name: string;
  title: string;
  summary: string;
  locator: string | null;
  observed_at: UtcDateTime | null;
  attributes: Record<string, string | number | boolean | null>;
}

export interface RootCause {
  id: Uuid;
  title: string;
  summary: string;
  confidence: number;
  evidence_ids: Uuid[];
}

export interface Impact {
  summary: string;
  affected_services: string[];
  affected_scope: string | null;
}

export interface Recommendation {
  id: Uuid;
  title: string;
  description: string;
  priority: "p0" | "p1" | "p2" | "p3";
  risk_level: "none" | "low" | "medium" | "high" | "critical";
  requires_approval: boolean;
  evidence_ids: Uuid[];
}

export interface Risk {
  id: Uuid;
  level: "low" | "medium" | "high" | "critical";
  summary: string;
  mitigation: string | null;
}

export interface AgentSummary {
  agent: string;
  status: "completed" | "skipped" | "failed";
  summary: string;
  duration_ms: number | null;
}

export interface DiagnosisResult {
  id: Uuid;
  run_id: Uuid;
  summary: string;
  severity: "info" | "low" | "medium" | "high" | "critical";
  confidence: number;
  root_causes: RootCause[];
  evidence: Evidence[];
  impact: Impact | null;
  recommendations: Recommendation[];
  risks: Risk[];
  requires_approval: boolean;
  agent_summary: AgentSummary[];
  report_markdown: string | null;
  created_at: UtcDateTime;
}

export interface DiagnosisRun {
  id: Uuid;
  session_id: Uuid;
  trace_id: Uuid;
  input_message_id: Uuid;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  result: DiagnosisResult | null;
  error: { code: string; message: string } | null;
  created_at: UtcDateTime;
  started_at: UtcDateTime | null;
  finished_at: UtcDateTime | null;
}

export interface DiagnosisRunListResponse {
  items: DiagnosisRun[];
  page: CursorPage;
  meta: ResponseMeta;
}
export interface RunEvent {
  id: Uuid;
  run_id: Uuid;
  sequence: number;
  type: RunEventType;
  occurred_at: UtcDateTime;
  data: Record<string, unknown>;
}

export interface RunEventEnvelope {
  event: RunEvent;
  meta: ResponseMeta;
}

export type RunEventType =
  | "run_queued" | "run_started" | "route_decided" | "agent_start"
  | "agent_done" | "conflict_checked" | "debate_round" | "report"
  | "reflection" | "run_succeeded" | "run_failed" | "run_cancelled";
```

上述 TypeScript 接口与同名 Pydantic 模型逐字段对应；P3 前端不得改用本地不同字段名或通过 Markdown 正则重建它们。

## 5. 最小端点表

| 方法与路径 | 请求 | 成功响应 | 状态码与排序 | 幂等语义 |
|---|---|---|---|---|
| `POST /api/v1/sessions` | `CreateSessionRequest` | `Session + meta` | `201` | 每次请求创建新 Session；当前未定义 `Idempotency-Key` 重放语义 |
| `GET /api/v1/sessions` | `cursor`、`limit`、可选 `status` | `items: Session[]`、`page`、`meta` | `200`；`updated_at desc, id desc` | 安全读取 |
| `GET /api/v1/sessions/{session_id}` | 路径 ID | `Session + meta` | `200` | 安全读取 |
| `PATCH /api/v1/sessions/{session_id}` | `UpdateSessionRequest` | `Session + meta` | `200` | 重复相同请求结果相同 |
| `DELETE /api/v1/sessions/{session_id}` | 路径 ID | 空响应 | `204`；逻辑归档 | 重复删除仍为 `204` |
| `GET /api/v1/sessions/{session_id}/messages` | `cursor`、`limit` | `items: Message[]`、`page`、`meta` | `200`；`created_at asc, id asc` | 安全读取 |
| `GET /api/v1/sessions/{session_id}/runs` | `cursor`、`limit` | `items: DiagnosisRun[]`、`page`、`meta` | `200`；`created_at desc, id desc` | 刷新恢复只读，不触发执行 |
| `POST /api/v1/sessions/{session_id}/runs` | `CreateRunRequest` + 必填 `Idempotency-Key` | `DiagnosisRun + meta` | `202`；新 Run 初始为 `queued` | 同 session、同 key、同 query 返回原 Run；不同 query 返回 `409` |
| `GET /api/v1/runs/{run_id}` | 路径 ID | `DiagnosisRun + meta` | `200` | 安全读取 |
| `GET /api/v1/runs/{run_id}/events` | `cursor`、`limit` | `items: RunEvent[]`、`page`、`meta` | `200`；`sequence asc` | 安全读取 |
| `GET /api/v1/runs/{run_id}/stream` | `Last-Event-ID` 或 `after_sequence` | `text/event-stream` | `200` | 只重放持久化 RunEvent，不创建新 Run |

`DELETE Session` 只能将 Session 逻辑归档；不会删除 Message、Run、RunEvent、DiagnosisResult 或审计记录。对已归档 Session 创建 Run 返回 `409 SESSION_ARCHIVED`。`PATCH` 不能跨端点变更 `environment_id` 或 `incident_id`，这些关联的正式变更语义留给后续 Incident/Environment API。

## 6. 创建 Run、SSE 与断线恢复

### 6.1 创建与持久化顺序

```text
POST /sessions/{session_id}/runs
  1. 校验 Session 为 active
  2. 使用 Idempotency-Key 去重
  3. 持久化用户 Message、DiagnosisRun(status=queued, trace_id) 与 RunEvent(sequence=1, type=run_queued)
  4. 返回 202 + Run
  5. 后台执行时依次持久化 run_started、Agent Trace、终态事件
  6. succeeded 时在同一产品事务边界写入 DiagnosisResult 与 run_succeeded
```

客户端拿到 `run.id` 后再打开 SSE；页面刷新时先 `GET /sessions/{session_id}/runs` 恢复可见 Run，再对选定 Run 调用 `GET /runs/{run_id}`；若非终态则读取事件或重连 SSE。产品 Run 不依赖当前单例 Coordinator 的“最近 trace”。

### 6.2 SSE 帧

每条持久化 `RunEvent` 对应一条 SSE 帧：

```text
id: 12
event: run_event
data: {"event":{"id":"e31c9fcb-24a2-4f7a-95cc-320d9d75e649","run_id":"...","sequence":12,"type":"agent_done","occurred_at":"2026-07-25T12:34:59.120Z","data":{"agent":"db","summary":"已完成"}},"meta":{"request_id":"...","trace_id":"..."}}

```

- SSE `id` 必须是 `RunEvent.sequence` 的十进制字符串，不使用随机 UUID，也不依赖连接产生顺序。
- SSE `event` 固定为 `run_event`；事件类别由 `data.event.type` 区分。`run_succeeded`、`run_failed`、`run_cancelled` 是持久化终态事件，发送后服务器关闭流。
- 服务端可发送无 `id` 的 keep-alive 注释，但不得把它们写为 RunEvent。
- 现有 Trace 类型映射：`route_decided`、`agent_start`、`agent_done`、`conflict_checked`、`debate_round`、`report`、`reflection` 同名映射；新产品补充 `run_queued`、`run_started` 和三个终态事件。

### 6.3 断线恢复

1. 浏览器自动重连时发送 `Last-Event-ID: <最后处理的 sequence>`；服务端仅发送 `sequence > Last-Event-ID` 的持久化事件。
2. 非 `EventSource` 客户端可使用 `after_sequence` 查询参数，语义与 `Last-Event-ID` 相同；两个值同时出现且不一致时返回 `400 INVALID_EVENT_CURSOR`。
3. 若客户端没有事件 ID，服务端从最早可用事件开始重放；客户端可先调用事件列表端点按 cursor 补齐。
4. 若 Run 已终态且客户端已收到终态 sequence，SSE 返回 `200` 后立即关闭；不会再次发送 complete/error 的临时帧。
5. 无效、负数或超出当前最大 sequence 的事件 ID 返回 `400 INVALID_EVENT_CURSOR`；事件保留策略导致的不可恢复游标在 P2 固化为 `409 EVENT_CURSOR_EXPIRED`，响应携带可安全的重新同步提示。

## 7. 状态码、失败与幂等

| HTTP | 错误码示例 | 语义 |
|---|---|---|
| `400` | `INVALID_EVENT_CURSOR`、`INVALID_REQUEST_ID` | 语法合法但协议语义无效 |
| `404` | `SESSION_NOT_FOUND`、`RUN_NOT_FOUND` | 资源不存在或不属于当前单租户范围 |
| `409` | `SESSION_ARCHIVED`、`RUN_ALREADY_TERMINAL`、`IDEMPOTENCY_KEY_REUSED`、`EVENT_CURSOR_EXPIRED` | 状态迁移、幂等键或恢复游标冲突 |
| `422` | `VALIDATION_ERROR` | 字段校验失败，返回安全 `details` |
| `429` | `RATE_LIMITED` | 后续限流启用时保留；可带 `Retry-After` |
| `500` | `INTERNAL_ERROR` | 未处理内部错误，不泄露细节 |
| `503` | `DIAGNOSIS_UNAVAILABLE` | 在 Run 尚未受理或持久化前，编排或必要依赖不可用，无法创建 Run |

幂等约束：

- `POST /runs` 的 `Idempotency-Key` 必填、UUID 格式、作用域为 `session_id + endpoint`，服务端至少保留 24 小时。
- 首次请求必须原子保存请求语义指纹（规范化 query）与结果 Run ID；同 key、同指纹返回同一 Run 和原始 `trace_id`，不重新执行 Agent。
- 同 key、不同指纹返回 `409 IDEMPOTENCY_KEY_REUSED`；并发首请求只能创建一个 Run。
- 网络超时后客户端必须使用相同幂等键重试；不得靠重复 POST 猜测 Run 是否创建成功。

失败约束：Run 一旦进入 `succeeded`、`failed` 或 `cancelled` 不可回退到 `running`。已返回 `202` 的 Run 后续若无法执行，HTTP 不再改写为 `503`；服务端必须将其转为 `failed`、写入安全 `error` 和最终 `run_failed` 事件。`failed` 的 `error` 与终态事件只含公共错误码和通用消息；详细异常只写服务端日志并以 `request_id`、`trace_id` 关联。

## 8. 旧接口兼容声明

| 旧接口 | 保留行为 | 与 v1 的边界 |
|---|---|---|
| `POST /diagnose` | 同步、无持久化的 Markdown 诊断，可选 trace/thinking | 不创建 Session、Message、Run、RunEvent 或 DiagnosisResult；不得被前端误作 v1 Run API |
| `GET /diagnose/stream` | 基于 query 的即时 SSE，使用既有 `progress/complete/error` 事件名 | 不保证 event ID、重放、持久化或断线恢复；不能接入 v1 Session 历史 |
| `GET /health` | 当前运行状态探针 | v1 可继续复用或未来新增版本化健康端点，不阻塞 P1/P2 |
| `/memory/*` | 阶段一兼容/占位行为 | 不作为 V1 Session、Knowledge 或 MemoryRecord 契约 |

P1/P2 只新增 `/api/v1`，不改变上述端点行为。`report/` 继续消费阶段一 Trace/实验能力；P3 主产品只消费 v1 Session/Run/Result 契约，并通过受控链接跳转完整 Trace。

## 9. 实现前验收

- P1 实现前：将本草案拆成 Pydantic 模型、TypeScript 生成/校验边界、OpenAPI 响应模型和迁移测试；不手工维护两份漂移字段。验证所有对外时间以 UTC `Z` 格式序列化。
- P2 实现前：验证 Run 状态机、`sequence` 单调递增、SSE `id` 一一映射、断线恢复、同 key 幂等、终态不可逆、结构化 `DiagnosisResult` 与 Markdown 补充共存。
- P1 前先解决 P0.2 记录的配置/数据路径与 Python 解释器问题；不得将本草案当成已运行的 API。
