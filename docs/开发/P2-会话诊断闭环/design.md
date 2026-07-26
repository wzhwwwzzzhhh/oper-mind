# P2 设计 — 会话诊断闭环

> 日期：2026-07-26　|　状态：✅ 已完成并提交　|　历史分支：`feat/p2-session-diagnosis`　|　最终提交：`54f02e5 feat: 完成P2.5刷新恢复与闭环验收`

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
| P2.1 | 领域、迁移与闭环设计 | 已提交 | 固定表关系、状态机、事务、Trace 映射、端点切片与测试门；不写业务实现 |
| P2.2a | 领域模型、首个业务迁移与 schema 验证 | 已提交 `11634b4` | 领域常量、ORM mapper、首个非空 Alembic revision、fresh DB/约束/降级/方言测试；不接入 HTTP/Agent |
| P2.2b | Repository 端口与 SQLAlchemy 实现 | 已提交 `5cf2c6b` | Repository ports/实现、固定 cursor 查询、Pydantic 数据边界与事务边界测试；不接入 Application Service/HTTP/Agent |
| P2.3 | Session/Run Application Service | 已提交 `ae2f978` | 受理、幂等、短事务、状态迁移、事件追加、结果写入与安全诊断适配；不实现 v1 HTTP/SSE |
| P2.4 | `/api/v1` 与 SSE 恢复 | 已提交 `440f03d` | Pydantic 契约、路由、SSE 重放、错误映射与 API 测试；旧接口不改 |
| P2.5 | 刷新恢复与闭环验收 | 已提交 `54f02e5` | Session→Run 恢复读模型、跨请求成功/失败恢复、终态 SSE、OpenAPI 与旧接口回归；不改 `report/` |

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

`Message.run_id` 是可空、带索引但**不设物理外键**的应用层校验引用：输入用户消息在创建 Run 的受理事务中先持久化，因而 `DiagnosisRun.input_message_id` 是非空物理外键；成功后的助手消息在 Run 成功事务中写入并带 `run_id`。若在 `messages.run_id` 再加反向外键会与 `diagnosis_runs.input_message_id` 形成循环 DDL，故 P2.3 Application Service 必须校验该 `run_id` 所属 Run 与 Message 的 `session_id` 一致。

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


## 1.1 P2.2a 实际落地与 schema 验证

- `backend/src/domain/diagnosis.py` 提供 Session、Message、Run、RunEvent 的受控枚举与终态集合。项目支持 Python 3.10+，枚举使用 `str, Enum`，不依赖 Python 3.11 才提供的 `StrEnum`。
- `backend/src/infrastructure/persistence/models.py` 映射六张表；主键、`trace_id` 与幂等键均使用 UUID，默认时间由 UTC aware `utc_now()` 生成。ORM 不声明关系级联，不创建表，也不持有事务边界。
- `backend/migrations/versions/20260726_01_p2_session_diagnosis.py` 是首份非空 revision（`20260726_01_p2`）；仅创建六张 P2 表及必要索引、外键、唯一键和检查约束。`backend/migrations/env.py` 显式导入 ORM mapper，使 Alembic `target_metadata` 完整加载。
- `backend/tests/test_p2_schema.py` 使用独立临时 SQLite，覆盖 fresh DB、绝对 `alembic.ini` 的跨目录执行、降级至 base 后业务表消失、再次升级、SQLite 外键、受控值、唯一/检查约束、无循环 `messages.run_id` 外键、UTC 默认时间，以及 ORM metadata 与 migration 的 PostgreSQL 离线 DDL 编译；不连接真实 PostgreSQL。
- JSON 列仅是结构化结果/事件的存储边界，不在 mapper 层接受原始日志、SQL、连接串或工具原始输出。P2.3/P2.4 必须在写入前与读取后以 Pydantic 契约完成可展示、脱敏 JSON 的校验。


## 1.2 P2.2b Repository 端口与实现结论

- `backend/src/domain/records.py` 定义跨层 Pydantic 数据对象、已解码 cursor 与页片段。端口仅传递这些对象，不暴露 SQLAlchemy mapper；所有时间均要求 UTC aware，基础设施从 SQLite 读取无时区值时按既有 UTC 存储约定归一化。
- `backend/src/domain/repositories.py` 定义 Session、Message、DiagnosisRun、RunEvent、DiagnosisResult、RunIdempotencyKey 六个 ports。它们不负责 HTTP cursor 编码、签名、limit 默认值/上限或错误体映射；这些仍是 P2.4 API 的职责。
- `backend/src/infrastructure/persistence/repositories.py` 只接受调用方注入的同步 SQLAlchemy `Session`，只做 staged `add`、按主键/唯一作用域读取和固定排序查询，未调用 `commit()`/`rollback()`。P2.3 Application Service 负责短事务和错误语义。
- 固定排序：Session 为 `(updated_at desc, id desc)`，Message 为 `(created_at asc, id asc)`，Run 为 `(created_at desc, id desc)`，RunEvent 为 `sequence asc`；实现通过 `limit + 1` 构造 `has_more` 和下一条已解码 cursor，拒绝非正页大小。
- 数据对象在进入 ORM 前校验 UTC、Role/Status/EventType/Severity、`sequence >= 1`、`next_event_sequence >= 1`、`schema_version >= 1` 与 `0 <= confidence <= 1`。Result/Event JSON 仍只是受控 JSON 容器，P2.3/P2.4 才接入正式的结构化资源校验和脱敏逻辑。

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


## 2.3 P2.3 实际 Application Service 与适配结论

- `backend/src/application/services.py` 是唯一的事务所有者：每个 Session/Run 用例打开短生命周期 Session，成功时 commit、异常时 rollback、最后 close。Repository 保持 staged add/read/条件更新，不自行控制事务。
- Run 受理事务显式按 Message → Run 的外键顺序 flush（ORM 未声明二者 relationship 以避免循环 DDL），再写幂等记录和 `run_queued`；同 key/同 SHA-256 规范 query 指纹回放同一 Run，同 key/不同指纹抛出 `IDEMPOTENCY_KEY_REUSED`。Session 活动时间在受理及终态写入时更新。
- Run 执行只使用已持久化的输入用户 Message；短事务条件认领 `queued → running` 并写 `run_started` 后，执行器在无事务状态运行。事件逐条在独立短事务中原子预留 sequence 并写入。已 running/终态 Run 不被重复 worker 执行。
- 成功短事务原子写 Result、助手 Message、`succeeded`、`run_succeeded`；失败短事务写安全错误、`failed`、`run_failed`。Application Service 校验 input Message 与 Run 的同 Session/user 关系，并校验助手 Message 的 `run_id`/`session_id` 一致，承担无物理 `messages.run_id` 外键的跨表一致性责任。
- `CoordinatorDiagnosisExecutor` 仅映射受控 event type/node/time 与有限 strategy，丢弃 Trace detail、原始报告 Markdown 和执行器任意 data；`ConservativeResultAssembler` 生成字段完整、低置信度、无未审查 evidence 的结果，不从 Markdown 推断事实。

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

## 6. P2.4 实际 API/SSE 落地

- 新增隔离的 `backend/src/api/v1/`：资源/请求 Pydantic 契约默认 `extra="forbid"`，响应由统一字段序列化为 UTC `Z`；`X-Request-Id` 接受有效 UUID 或生成新值并回显，带 Run 的响应同时回显稳定 `X-Trace-Id`。
- `/api/v1` 已实现 Session 创建、固定 cursor 列表、读取、标题更新、逻辑归档、消息列表、Run 受理/后台执行、Run/Result 读取、RunEvent 列表和 SSE 重放。写入仅委派 Application Service，读取仅通过 Repository；没有 API 层 commit/rollback。
- `POST /sessions/{session_id}/runs` 强制 UUID `Idempotency-Key`。首次受理提交 queued Run 后返回 `202`，由 BackgroundTasks 调用已持久化 Run 的执行用例；同键同 query 返回同 Run，不会重新加入后台执行；同键不同 query 为 `409 IDEMPOTENCY_KEY_REUSED`。
- `GET /runs/{run_id}/stream` 只读取已提交 RunEvent；SSE 固定为 `event: run_event`，`id` 为十进制 sequence，`Last-Event-ID` 与 `after_sequence` 支持断线续传，不一致、非法或超过当前最大 sequence 时返回 `400 INVALID_EVENT_CURSOR`。终态事件发送后关闭，绝不把 executor 的即时输出或未提交事件写入 SSE。
- Result 读取必须经过公开 Pydantic 资源模型；不合规结构化 JSON 不向客户端透传。当前保守 ResultAssembler 仍只写低置信度、无未审查证据的结果，真实证据组装不在 P2.4 范围。执行失败在 Application Service 和 v1 资源映射两层均收敛为固定公开错误，防止未来非受控写入透传。

## 7. P2.4 验收与遗留

- 使用 Alembic 创建独立临时 SQLite 的 v1 测试覆盖资源 meta、UTC `Z`、cursor、Session 更新/归档、Run 幂等、后台执行、结构化 Result、消息、RunEvent sequence、SSE 全量/续传重放、游标错误、request ID 和旧 API 隔离。
- 已通过：P2.4 定向 5 passed；P2 应用/API/旧 API 联合 23 passed；完整后端 124 passed（1 条既有 TestClient 弃用警告）；direct/chain/parallel/debate pipeline smoke 通过；未生成 `data/opermind.sqlite3`。
- P2.5 已完成：新增 `GET /sessions/{session_id}/runs` 的固定 `created_at desc, id desc` cursor 读模型与 `DiagnosisRunListResponse`；它先确认 Session 存在，再只通过 Repository 读取 Run/Result，不调用 executor、Application Service 写用例或 API 层事务。
- 独立 Alembic 临时 SQLite 的跨 TestClient 验收覆盖成功和安全失败 Run：刷新后可恢复 Session、Run、Message、Result、RunEvent；Run/Event/SSE 的 trace_id 一致；终态 `Last-Event-ID` 或 `after_sequence` 重连立即关闭；错误中的连接串、令牌与 SQL 不会出现在资源或 SSE。
- 已通过：P2 定向回归 20 passed、完整后端 126 passed（均仅有既有 Starlette TestClient 弃用警告）、direct/chain/parallel/debate pipeline smoke；未生成 `data/opermind.sqlite3`。SQLite 仍不替代 PostgreSQL 的并发幂等/sequence 验证；BackgroundTasks 也仍不等价于可崩溃恢复的持久化任务队列，留作 P7 生产加固风险。
