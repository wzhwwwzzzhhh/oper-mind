# P2 设计 — 会话诊断闭环

> 日期：2026-07-26　|　状态：P2.1 已完成并提交　|　分支：`feat/p2-session-diagnosis`　|　稳定基线：`6aa3302 feat: 建立P1应用持久化地基`

## 目标

P2 将阶段一即时诊断升级为可恢复的 V1 会话诊断闭环：用户创建/进入 Session，在其中创建 DiagnosisRun，Run 的执行过程以持久化 RunEvent 供 SSE 重放，成功后写入结构化 DiagnosisResult 与助手消息，失败后保留安全错误和可审计终态。

P2 只新增 `/api/v1`，不改阶段一 `POST /diagnose`、`GET /diagnose/stream`、`GET /health` 或 `/memory/*` 的兼容语义。Agent Core 继续只负责编排和诊断；数据库事务、幂等、状态机、事件映射和 SSE 协议属于 Application Service 与基础设施边界。

## 已完成基线

- `1559266`：根 Python/依赖环境恢复。
- `3d9d810`：根配置、数据与脚本路径收口。
- `22b58b0`：持久化、迁移、事务与安全设计。
- `6aa3302`：同步 SQLAlchemy/Alembic/psycopg、应用 DB Settings、Engine/Session factory、跨目录迁移骨架与基础设施测试。
- P0.3 `api-v1-contract.md` 是 P2 对外资源、状态码、幂等和 SSE 契约的唯一字段语义来源。

## P2 分解

| Step | 名称 | 状态 | 交付与边界 |
|---|---|---|---|
| P2.1 | 领域、迁移与闭环设计 | Review 通过，待本次提交 | 固定表关系、状态机、事务、Trace 映射、端点切片与测试门；不写业务实现 |
| P2.2 | 领域模型、首个业务迁移与 Repository | 下一步 | ORM mapper、首个非空 Alembic revision、Repository 端口/实现与数据库测试；不接入 HTTP/Agent |
| P2.3 | Session/Run Application Service | 待开始 | 受理、幂等、状态迁移、事件追加、结果写入与 Agent 适配端口；不实现 v1 HTTP/SSE |
| P2.4 | `/api/v1` 与 SSE 恢复 | 待开始 | Pydantic 契约、路由、SSE 重放、错误映射与 API 测试；旧接口不改 |
| P2.5 | 刷新恢复与闭环验收 | 待开始 | 端到端恢复、失败、幂等、结构化结果和 `report/` 受控 Trace 链接验收 |

## 1. 领域关系与首个业务 migration

```text
Session 1 ── * Message
Session 1 ── * DiagnosisRun
Message(user) 1 ── 1 DiagnosisRun.input_message
DiagnosisRun 1 ── * RunEvent
DiagnosisRun 1 ── 0..1 DiagnosisResult
DiagnosisRun 1 ── 0..1 Message(assistant)
Session 1 ── * RunIdempotencyKey
```

`Message.run_id` 是可空外键：输入用户消息在创建 Run 的受理事务中先持久化，因而 `DiagnosisRun.input_message_id` 可以是非空外键；成功后的助手消息在 Run 成功事务中写入并带 `run_id`。不在 `DiagnosisRun` 保存助手消息 ID，避免双向外键循环。

P2.2 第一份非空 revision 创建以下表：

| 表 | 核心字段与约束 | 索引/用途 |
|---|---|---|
| `sessions` | UUID `id`、title、`active/archived`、可空 environment/incident UUID、UTC 时间 | `(updated_at desc, id desc)` 支持 Session cursor 列表 |
| `messages` | UUID `id`、`session_id`、可空 `run_id`、`user/assistant/system`、content、UTC 创建时间 | `(session_id, created_at, id)` 支持按时间读取；`run_id` 仅允许关联同 Session 的 Run 由 Service 校验 |
| `diagnosis_runs` | UUID `id`、session/input message/trace UUID、状态、`next_event_sequence`、UTC 时间 | `(session_id, created_at, id)`；状态检查；`input_message_id` 唯一，防止同一输入生成多个 Run |
| `run_events` | UUID `id`、`run_id`、正整数 sequence、受控 type、UTC 时间、受校验 JSON `data` | `UNIQUE(run_id, sequence)`；`(run_id, sequence)` 支持 SSE/事件重放 |
| `diagnosis_results` | UUID `id`、`run_id` 唯一、最终结构化 JSON 子结构、Markdown 补充、UTC 时间 | 每 Run 仅一个成功结果；JSON 写入前/读取后 Pydantic 校验 |
| `run_idempotency_keys` | UUID `id`、session、endpoint、key、request fingerprint、run、expires_at、UTC 创建时间 | `UNIQUE(session_id, endpoint, idempotency_key)`；同键不同指纹冲突 |

所有业务主键、`trace_id` 和幂等键以 Python UUID v4 生成；所有内部时间为 UTC aware datetime；对外由 P2.4 统一序列化为 `Z`。数据库 JSON 只保存经 Pydantic 校验、可展示且脱敏的对象；Evidence 的原始日志、SQL、连接串和工具原始响应绝不入库。

## 2. Run 状态机与事务

```text
queued --worker accepted--> running --result committed--> succeeded
   |                            |                         (terminal)
   +--dispatch/persistence--> failed
                                +--safe error committed--> failed
queued/running --cancel committed--> cancelled
```

- `succeeded`、`failed`、`cancelled` 为终态，不能回退到 `running` 或互相迁移。
- `queued → running`、`running → terminal` 必须以 `UPDATE ... WHERE status IN (...)` 或等价的 Repository 条件更新保护；零行更新映射 `409 RUN_ALREADY_TERMINAL` 或无操作重放。
- `next_event_sequence` 保存在 `diagnosis_runs`。同一 Run 的事件追加在短事务内原子递增并插入 `run_events`；`UNIQUE(run_id, sequence)` 是数据库最终保护。P2.3 默认单 Run worker，后续并发 worker 必须新增锁/乐观版本策略，不能假设内存串行。

### 2.1 创建 Run 与幂等受理事务

`POST /api/v1/sessions/{session_id}/runs` 的 Application Service 在一个短事务中：

1. 锁定/读取 Session，归档则 `409 SESSION_ARCHIVED`；不存在为 `404`。
2. 规范化 query（trim 后内容），计算稳定语义指纹。
3. 查询 `(session_id, endpoint, Idempotency-Key)`：同键同指纹返回原 Run/trace_id，不调度 Agent；同键不同指纹为 `409 IDEMPOTENCY_KEY_REUSED`。
4. 新建用户 Message、`queued` DiagnosisRun、幂等记录和 sequence=1 的 `run_queued` 事件。
5. 提交后返回 `202`，再调用独立 worker/执行器适配端口。提交失败则不得返回 Run 或发送 SSE。

### 2.2 执行、事件和终态事务

- Worker 首先用短事务将 Run 迁移为 `running` 并追加 `run_started`；若已终态则不执行 Agent。
- 现有 `CoordinatorAgent.route_stream()` 的 TraceRecord 映射为 P0.3 同名 `route_decided`、`agent_start`、`agent_done`、`conflict_checked`、`debate_round`、`report`、`reflection` 事件。每个事件先持久化、提交后才成为 SSE 可读数据。
- 现阶段 `CoordinatorAgent` 输出的是 Markdown 终稿和 Trace，尚不生产 P0.3 的结构化 DiagnosisResult。P2.3 必须增加可测试的 ResultAssembler 端口：mock 路径生成确定性、字段完整的结构化结果；真实路径在缺乏安全结构化证据时写安全的保守默认值，而不从 Markdown 正则猜测根因。
- 成功短事务原子写入 DiagnosisResult、助手 Message、Run `succeeded`、finished_at 与最后 `run_succeeded`；失败短事务写安全 `RunError`、Run `failed`、finished_at 与 `run_failed`。Run 的 `result` 与 `error` 在数据库层和 Service 层互斥校验。

## 3. API、SSE 与恢复映射

P2.4 实现 P0.3 最小端点，不扩展字段：

| 端点切片 | P2.4 行为 | 事务/恢复约束 |
|---|---|---|
| `POST /api/v1/sessions` | 创建 active Session | 可选幂等，返回 `201` |
| `GET /api/v1/sessions` / `GET /{id}` / `PATCH /{id}` / `DELETE /{id}` | 列表、读取、改标题/归档 | cursor 固定排序；DELETE 是逻辑归档 |
| `GET /sessions/{id}/messages` | 历史消息读取 | `(created_at, id)` cursor 升序 |
| `POST /sessions/{id}/runs` | 幂等受理、返回 queued Run | 必填 UUID `Idempotency-Key`，返回 `202` |
| `GET /runs/{id}` | 查询 Run、终态结果/安全错误 | Run 不存在为 `404` |
| `GET /runs/{id}/events` | 读持久化事件 | `(sequence asc)` cursor |
| `GET /runs/{id}/stream` | 只重放持久化事件 | `Last-Event-ID` / `after_sequence` 语义按 P0.3 |

SSE 固定 `event: run_event`，`id` 是十进制 `sequence`，payload 是 `RunEventEnvelope`。两个恢复游标同时出现且不一致为 `400 INVALID_EVENT_CURSOR`；负数、非数字或超过最大 sequence 也为 `400`。没有游标从最早持久化事件开始；已收到终态 sequence 的客户端连接返回 `200` 后关闭。P2 不实现事件过期，故不提前返回 `EVENT_CURSOR_EXPIRED`。

Request/trace 规则：P2.4 在 v1 路由引入 `X-Request-Id` 校验/生成并回显；Run 创建时生成稳定 trace_id，之后 Run、事件和 SSE 都返回相同 trace_id。阶段一接口不改其现有响应头/响应体。

## 4. 分层与接口边界

```text
api/v1 routes + Pydantic models
  -> Application Services
      -> Repository ports
          -> SQLAlchemy repositories
      -> DiagnosisExecutor / ResultAssembler ports
          -> CoordinatorAgent adapter
```

- `domain/`：状态枚举、Run 状态转移、命令和值对象；不依赖 FastAPI/SQLAlchemy。
- `application/`：Session/Run 用例、事务边界、幂等、异常映射、事件/结果编排；不直接生成 HTTP 响应。
- `infrastructure/persistence/`：ORM mapper、Repository、Session factory；Repository 不 commit/rollback。
- `infrastructure/diagnosis/`：对 `CoordinatorAgent.route_stream()` 的适配，产生诊断事件与最终原始输出；禁止在 Agent 节点写数据库。
- `api/v1/`：Pydantic 模型、依赖注入、响应 meta、错误/SSE 协议。现有 `src/api/` 阶段一接口保持不动。

## 5. 验收与非目标

P2.2/P2.3/P2.4 合并完成前，每一步独立通过自身测试。P2 闭环验收必须覆盖：fresh DB migration、Session 归档、同幂等键重试、同键不同 query 冲突、Run 终态不可逆、sequence 单调递增、提交后 SSE 重放、断线恢复、结构化 Result/Evidence 脱敏、失败安全错误和旧 API/pipeline 回归。

P2 不做 `frontend/` React 工程、P4 真实环境/数据源、P5 审批执行、通知、复杂 RBAC、事件保留过期、真实 PostgreSQL 连接或 `report/` 改造。P3 才初始化主产品前端；P2 仅提供可被它消费的稳定 API。
