# P2 独立审查 — 会话诊断闭环

> 更新时间：2026-07-26　|　结论：P2.4 已通过独立审查，待用户授权提交

## 已提交基线

- P2.1 设计：`8f27717 docs: 完成P2会话诊断闭环设计`。
- P2.2a schema：`11634b4 feat: 完成P2.2a领域模型与首个业务迁移`。
- P2.2b Repository：`5cf2c6b feat: 完成P2.2b Repository端口与SQLAlchemy实现`。

## P2.3 审查范围

审查 Application Service 短事务、Session/Run 受理与归档、幂等、条件状态更新、事件 sequence、成功/失败终态、Message/Run 跨表一致性、Coordinator/ResultAssembler 适配、安全 JSON 边界、Repository 事务纪律和旧接口范围。P2.4 HTTP/SSE 不在本 Step。

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| 事务归属 | 通过 | 仅 `application/services.py` 的统一事务辅助函数调用 commit/rollback；Repository、Coordinator 适配和 Agent 不控制事务 |
| 受理原子性 | 通过 | 单短事务写 input Message、queued Run、幂等记录和 sequence=1 `run_queued`；显式 flush 保证无 ORM relationship 时的 Message→Run 外键写入顺序 |
| 幂等 | 通过 | 固定 endpoint + Session + key 作用域；规范 query SHA-256；同 key/同指纹回放、不同指纹抛应用冲突；非幂等完整性错误不被伪装为重放 |
| 状态与重复 worker | 通过 | queued→running 由条件更新认领并写 `run_started`；已 running/终态 Run 不重复执行；成功/失败仅从运行态收口 |
| sequence 与事件 | 通过 | Run `next_event_sequence` 通过原子 update returning 预留，逐事件短事务写入；最终仍由 `UNIQUE(run_id, sequence)` 保护 |
| 成功/失败原子性 | 通过 | 成功事务写 Result/助手 Message/succeeded/final event；组装失败会 rollback 成功写入后再安全失败；失败只写安全 code/message 与 `run_failed` |
| Message/Run 一致性 | 通过 | 执行前验证 input Message 存在、同 Session 且为 user；助手 Message 写入前验证 `run_id`/`session_id` 与 Run 一致，承担无物理 `messages.run_id` FK 的责任 |
| 执行隔离 | 通过 | `run_started` 提交后才调用 executor；测试以独立 Session 读取 running 状态确认执行器处于无事务区间 |
| Coordinator/JSON 安全 | 通过 | Adapter 仅传 type/node/time/有限 strategy，丢弃 detail、原始 Markdown 和 executor data；保守 assembler 不伪造 Evidence/根因 |
| 分层与越界 | 通过 | 新增 application/ 与 infrastructure/diagnosis/ 已同步规则；domain 无 SQLAlchemy 泄露；未新增 API/SSE/旧 API/前端/真实数据源改动 |
| 回归 | 通过 | P2 定向 32 passed；完整后端 119 passed；direct/chain/parallel/debate pipeline smoke 通过；1 条既有弃用警告 |

## 已知风险与 P2.4 门槛

- SQLite 测试不能替代 PostgreSQL 高并发的幂等唯一键竞争、`UPDATE ... RETURNING` 和 sequence 锁语义；P2.4/P7 必须增加受控 PostgreSQL 集成或等价并发门。
- P2.3 暂无 HTTP 层，`ApplicationError` 尚未映射 P0.3 错误体/状态码；P2.4 必须实现安全错误映射、请求/trace ID、Pydantic 资源模型和不透明 cursor。
- SSE 只能在 P2.4 重放已提交 RunEvent；不得在 executor 内直接推送或读取未提交数据。
- 结构化 Result JSON 的正式 Pydantic 资源级脱敏/校验必须在 P2.4 衔接，保守 assembler 不应被误作真实诊断事实。

## 外部未提交改动

工作区存在 `docs/00-项目方案说明书.md` 的外部 1 行文本改动；本 Step 未读取内容、未修改、未暂存，且必须排除在 P2.3 提交之外。另有两个包初始化文件显示为修改但内容 hash 与 HEAD 一致、无 diff，不纳入提交。

## 结论

P2.3 在既定边界内通过独立审查。待用户授权后可提交；提交后的唯一下一步为 **P2.4：`/api/v1` 与 SSE 恢复**。

---

## P2.4 独立审查

### 审查范围

审查 `/api/v1` 的 Pydantic 资源契约、依赖装配、Session/Message/Run/RunEvent 路由、后台执行触发、统一 request/trace 元数据、安全错误映射、cursor 分页、持久化 SSE 重放、结构化 Result 读取边界，以及对阶段一旧 API、事务规则和工作区隔离的影响。

| 检查项 | 结论 | 审查结果 |
|---|---|---|
| 路由隔离 | 通过 | 新增实现位于 `backend/src/api/v1/`；`backend/src/api/` 阶段一模型/事件未被修改，`test_api.py` 旧 `/diagnose` 与 `/diagnose/stream` 回归通过 |
| 应用装配 | 通过 | `backend/src/app.py` 只装配 v1 服务、request ID 中间件、v1 错误处理和 router；启动不执行 Alembic、`create_all()` 或写入业务数据 |
| 事务边界 | 通过 | API 写入只调用 `SessionApplicationService` / `RunApplicationService`；扫描确认 commit/rollback 仍只在 `application/services.py` 的统一短事务辅助函数中出现 |
| Run 受理/后台执行 | 通过 | `POST /runs` 强制 UUID 幂等键；首次受理提交后才由 BackgroundTasks 调用 `execute_run`；同键重放不会重复调度执行器 |
| Resource/JSON 安全 | 通过 | v1 资源默认拒绝额外字段，Result 读取再次经过 Pydantic 资源模型；保守 assembler 的空证据/低置信度结果没有被包装成真实诊断事实 |
| 时间与关联 ID | 通过 | v1 JSON datetime 统一序列化为 UTC `Z`；有效 `X-Request-Id` 回显，无效值安全返回 `400 INVALID_REQUEST_ID`；Run/事件/SSE 返回稳定 trace ID |
| Cursor 与读取 | 通过 | Session/Message/Event 固定排序 cursor 经过 URL-safe 不透明编解码；非法 cursor 返回 `400 INVALID_CURSOR`；不存在 Session/Run 返回安全 `404` |
| SSE 协议 | 通过 | v1 固定 `event: run_event`，SSE `id` 与提交后的 sequence 一一映射；支持 Last-Event-ID/after_sequence 续传，冲突/非法/超范围为 `400 INVALID_EVENT_CURSOR`；终态事件发送后关闭 |
| 未提交数据隔离 | 通过 | SSE 每次读取短 Session 中 Repository 已提交事件；不订阅 executor 即时输出，也不产生临时 complete/error 帧 |
| 越界检查 | 通过 | 未改动 `frontend/`、`report/`、`backend/src/core/`、`backend/src/agents/`；没有真实 PostgreSQL、真实数据源或运行时 SQLite 资产 |
| 回归 | 通过 | P2.4 定向 5 passed；P2 应用/API/旧 API 联合 23 passed；完整后端 124 passed；pipeline smoke 通过；仅保留既有 Starlette TestClient 弃用警告 |

### 审查发现与修复

- 初次审查发现执行器异常文本可被持久化/API 透传；现已在 `RunApplicationService` 统一收敛为 `DIAGNOSIS_FAILED` 与固定公开文案，并在 v1 资源映射增加纵深防御。对抗性测试覆盖 `postgresql://`、SQL 与 token 不进入 Run HTTP/SSE。
- 初次审查发现 `_claim_run()` 在 try 之外可能使异常 Run 保持 queued；现已纳入失败收口。跨 Session 输入消息测试验证不调用 executor、写入 `run_failed` 且终态可重放。
- 初次审查发现 API fixture 在导入 `src.app` 前未显式固定数据库 URL；现已先设 `OPERMIND_APP_DATABASE_URL` 指向临时 Alembic SQLite。
- 修复后独立复审结论：通过，无阻塞项。

### 已知风险与 P2.5 门槛

- FastAPI BackgroundTasks 适合当前单进程 mock/开发闭环，但不等价于生产级队列、重试或多进程 worker；P2.5/P7 要明确进程重启后的 queued/running Run 恢复策略。
- SSE 当前采用短连接轮询已提交事件，满足 sequence 重放而非高吞吐实时推送；P2.5/P7 应覆盖连接取消、慢客户端和长期轮询资源上限。
- SQLite 覆盖了约束和 API 行为，不能替代 PostgreSQL 的并发幂等唯一键竞争与 sequence 语义验证；真实 PostgreSQL 仍不在本 Step 接入范围。
- Session 创建请求的可选 `Idempotency-Key` 因 schema 尚无对应记录表而没有伪实现；P2.4 只对 Run 落实已设计且已迁移的幂等语义。

### 结论

P2.4 在既定边界内通过独立审查。实现、文档和测试已经准备完成；待用户授权后，只能暂存并提交 P2.4 范围文件。提交后的唯一下一步为 **P2.5：刷新恢复与闭环验收**。
