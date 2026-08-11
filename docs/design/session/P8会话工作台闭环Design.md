# P8 会话工作台闭环——独立消息、取消 Run 与全局提案列表 Design

> 状态：已确认
> 更新：2026-08-10
> 关联：`docs/prd/session/P8-workbench-loop-closure.md`（已确认，issue #54）、
> `docs/产品定义.md`（§2.1 会话主入口、§5 安全边界）、`docs/开发规范.md`（§2/§4/§5/§6）、
> `docs/架构与开发路径.md`（一条主脊、工具网关接缝、Trace 安全投影）、
> `docs/接口清单.md`（第一大模块缺表：无独立发消息 / 无法取消 Run / 无全局提案列表）、
> `backend/src/application/services.py`、`backend/src/application/action_services.py`、
> `backend/src/api/v1/routes.py`、`backend/src/api/v1/schemas.py`、`backend/src/api/v1/resources.py`、
> `backend/src/domain/actions.py`、`backend/src/domain/records.py`、
> `backend/src/infrastructure/persistence/action_repositories.py`、
> `frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/features/workbench/conversation-turns.ts`、
> `frontend/src/features/workbench/ActionProposalPanel.tsx`、`frontend/src/features/shell/Sidebar.tsx`。

## 1. 目标与范围

### 一句话目标

补上会话主入口的三个体验洞：普通消息不再拉起多 Agent 调查、运行中的 Run 可被取消、
待审批提案有全局入口——让「会话即主入口」与「审批是安全卖点」在产品上成立。

### 做什么

1. **独立消息通道**：新增 `POST /sessions/{id}/messages`，非调查意图的普通消息走轻量回复
   （创建 user 消息 + assistant 模板回复，`run_id` 为空，不创建 Run、不触发多 Agent 图）。
2. **取消 Run**：新增 `POST /runs/{id}/cancel`，对 `queued`/`running` 的 Run 协作式取消
   （状态置 `cancelled`、写入 `run_cancelled` 事件、后台执行在下一个事件检查点停止）；
   已终态 Run 返回 409；重复取消幂等返回 204。
3. **全局提案列表**：新增 `GET /action-proposals`，跨会话跨 Run 返回提案安全摘要，
   cursor 分页 + 状态过滤；前端新增「待审批」入口页并可进入既有审批流程。
4. **前端工作台适配**：消息输入框普通消息走轻量回复、调查意图走既有 Run 主链路；
   运行中的 Run 卡片显示「停止」按钮；导航新增「待审批」入口。

### 明确不做

- 不做消息编辑/删除、全局 Run 列表 `GET /runs`、会话搜索、重跑/重新生成（接口清单欠账，另行排期）。
- 不做身份/审批人模型（`docs/产品定义.md` §7 未决；审批 actor 仍固定为 `local_operator`）。
- 不改变调查类消息的既有行为：`POST /sessions/{id}/runs` 主链路、消息列表接口契约均不变。
- 普通消息不做 LLM 轻量生成（首版用确定性模板回复，零外部依赖）。
- 不做数据库迁移：`RunStatus.CANCELLED`、`RunEventType.RUN_CANCELLED` 及 DB 检查约束
  均已存在，取消不新增字段/表。
- 普通消息端点不做幂等键（PRD 未要求；重复发送由用户显式操作，见 §6 决策 5）。

### 与「一条主脊，能力即插件」硬规则的关系（显式声明）

`docs/架构与开发路径.md` 硬规则 1 禁止「新端点、新流程、新独立脚本/页面」，本 Design 一次新增
3 个公开端点，并引入一条**不走 Run 主脊的普通消息轻流程**。这不是新能力，而是补齐既有
`docs/接口清单.md` 已登记欠账的**主入口体验接线**：

- 独立消息通道是会话主入口的「普通对话」接线，调查仍 100% 走既有 Run 主脊；
- 取消 Run 是对既有 Run 状态机（`CANCELLED`/`run_cancelled` 早已存在）补一个显式入口；
- 全局提案列表是对既有 action 事件表的只读投影，复用既有 cursor 分页基建。

三条均不触碰工具网关、凭据、审批/执行白名单等既有边界；普通消息轻流程刻意不接任何
Tool/Connector（零外部访问）。若确认，需同步把该工作包登记到 `docs/路线图.md` 当前阶段。

## 2. 设计决策

### 2.1 意图判定收敛为单一公开函数（普通消息通道的地基）

- 新增 `src/application/message_routing.py`，把 `services.py` 私有的 `_requires_database_context`
  提升为公开函数 `requires_database_context(query: str) -> bool`（关键词规则与现网一致，
  即 PRD 开放问题 2 的「复用既有关键词」方案；零行为变化）。
- `services.py` 的 `_resolve_run_service_id` / 受理守卫改为调用该公开函数；
  既有 `test_p43_service_context.py` 对关键词判定的断言迁移到该函数，保持单一事实源。
- 判定失败（异常）一律按「普通消息」处理（PRD 降级策略：不误触发调查）。

### 2.2 独立消息通道（后端）

- 新增 `src/application/plain_messages.py`：`SendPlainMessageCommand(content)` 与
  `PlainMessageApplicationService`。用例 `send_plain_message(session_id, content)`：
  1. 短事务内校验会话存在且 `active`；否则 `SessionNotFoundError` / `SessionArchivedError`。
  2. `requires_database_context(content)` 为真 → 抛 `InvestigationRequiredError`（应用错误码
     `INVESTIGATION_REQUIRED`，路由层映射 409），**不创建任何消息**。
  3. 普通意图 → 在一个短事务内创建两条消息（复用 `SqlAlchemyMessageRepository.add`，
     `MessageData.run_id=None`）：一条 `user`（原文）+ 一条 `assistant`（确定性模板回复，
     明确说明「未启动调查」），并 `_touch_session` 更新会话活动时间。
  - **排序确定性**（arch-review F2）：两条消息的 `created_at` 使用递增时间戳
    （assistant 严格晚于 user），使 `GET /sessions/{id}/messages` 按 `(created_at, id)` 排序时
    user → assistant 顺序稳定；前端投影据此就近配对。
- 新增路由 `POST /sessions/{session_id}/messages`，体 `{content: str}`（1..4000，strip 校验）：
  - 普通意图 → 201，返回 `{user_message, assistant_message, meta}`（`PlainMessageResponse`）。
  - 调查意图 → 409 `INVESTIGATION_REQUIRED`；前端收到后回退到既有 `POST /runs` 主链路。
- **装配**（arch-review F1）：`PlainMessageApplicationService` 经 `dependencies.py` 的
  `V1Services` 显式装配（与既有 `session_service` / `run_service` 同层），
  `routes.py` 通过 `Depends(get_v1_services)` 读取使用，不新增全局单例。
- **模板回复文案**（确定性、诚实、零外部依赖）：
  「这是普通对话回复：我没有启动任何调查，也没有访问外部服务。如果你要排查慢查询、连接池、
  索引等问题，可以直接描述，我会发起只读调查。」——满足 AC1/AC3。
- **性能**：秒级轻量路径（两条 INSERT + 一次 Session touch，无 LLM、无工具、无连接）。

### 2.3 取消 Run（协作式，无迁移）

- 复用既有 `RunStatus.CANCELLED` 与 `RunEventType.RUN_CANCELLED`（枚举与 DB 检查约束均已存在，
  见 `backend/migrations/versions/20260726_01_p2_session_diagnosis.py`），**不新增字段/表/迁移**。
- `RunApplicationService.cancel_run(run_id) -> DiagnosisRunData`，在短事务中：
  1. Run 不存在 → `RunNotFoundError`（404）。
  2. 状态 ∈ {`succeeded`, `failed`} → `RunAlreadyTerminalError`（409，AC5）。
  3. 状态 == `cancelled` → 直接返回（幂等 204，AC6）。
  4. 状态 ∈ {`queued`, `running`} → `transition_status({QUEUED, RUNNING}, CANCELLED,
     finished_at=now)`，若返回 None（并发竞争已终态）→ `RunAlreadyTerminalError`；
     成功后 `_append_event_in_transaction` 写 `run_cancelled` 事件，`_touch_session`。
- **AC5/AC6 取舍说明**（arch-review B1）：PRD AC5 字面把 `cancelled` 归入「已结束返回 409」，
  AC6 又要求重复取消幂等成功——两者只能自洽的读法是：`succeeded`/`failed` → 409，
  已 `cancelled` → 204 幂等成功。本 Design 采用该读法并在验收时按此口径执行。
- **协作式终止**（PRD 开放问题 3 推荐方案，安全优先）：
  - `execute_run` 事件循环在**每次持久化事件之前**检查当前 Run 状态
    （轻量仓库方法 `is_cancelled(run_id) -> bool`，只查状态列）；
    若已 `cancelled` → 中断流式迭代并返回当前 Run（终态已由 cancel 端点写入，不覆盖）。
  - `queued` 未启动的 Run：`_claim_run` 看到非 `queued` 直接返回（不再启动执行）。
  - `_complete_success` / `_complete_failure` 已对终态（含 `cancelled`）短路返回，不会覆盖
    取消结果——这正是既有代码已准备好的接缝，无需新状态机。
  - **诚实边界**（arch-review C1）：检查点与下一次事件 append 之间存在竞态，理论上
    `run_cancelled` 之后仍可能落一条工具事件（sequence 由 `reserve_event_sequence` 预留）。
    该场景用户不可见（`sse.py` 读到 `run_cancelled` 即关闭流），但本 Design 如实标注
    「事件流以 `run_cancelled` 收尾」为尽力保证而非严格承诺；实现时在 append 事务内带
    状态守卫可进一步缩小窗口。
- 新增路由 `POST /runs/{run_id}/cancel`，成功 204（沿用既有 204 模式），404/409 走 `ApiV1Error`。
- 单 Run 取消不影响其他 Run（每次独立短事务）；已提审提案不受取消影响（提案与 Run 状态解耦）。

### 2.4 全局提案列表

- 新增领域游标 `ActionProposalCursor(created_at, id)`（放 `domain/records.py`，
  排序口径与 `DiagnosisRunCursor` 一致：`created_at` 倒序 + id 决胜）。
- `SqlAlchemyActionProposalRepository.list_page(cursor, limit, status: ActionProposalStatus | None)`
  → `RepositoryPage[ActionProposalData, ActionProposalCursor]`（固定排序，`limit+1` 判定 has_more，
  复用 `_page` / `_validate_limit`）。
- `ActionApplicationService.list_proposals(cursor, limit, status)` 用例（纯只读，跨会话跨 Run）。
- 新增路由 `GET /action-proposals`：`cursor` / `limit`（默认 20，≤100）/ `status`（可选，
  FastAPI `Literal` 校验，非法值 422）；返回
  `ActionProposalListResponse { items: [ActionProposalSummaryResource], page: CursorPage, meta }`。
- 新增资源 `ActionProposalSummaryResource`（仅安全摘要，AC7/AC8/AC9）：
  `id, source_run_id, action_id, status, mode, title, created_at, updated_at`。
  其中 `mode`/`updated_at` 为 PRD 列举（id / 来源 Run / 动作 / 状态 / 创建时间 / 标题）之外的
  轻微补充，仅作列表展示辅助（arch-review B2）。
  **不含** description / target / root_cause_id / evidence_ids / risk_summary / verification_plan /
  action_digest / failure_message —— 明细仍走既有 `GET /action-proposals/{proposal_id}`。
- 空列表返回空 `items` + `has_more=false`（诚实空态，不伪造）。

### 2.5 前端工作台适配

- **发送路由（服务端权威，客户端预分流 + 回退）**：`WorkbenchPage.SessionWorkspace` 的 Composer 提交走统一处理器 `submit_text(text)`：
  - 前端按与服务端一致的关键词集合（`frontend/src/features/workbench/message-intent.ts`）预分流：
    调查意图直接走既有 Run 幂等链路；普通意图调 `send_plain_message`。
  - `send_plain_message` 成功（201）→ 失效会话消息查询刷新列表，清空输入框；
  - 409 `INVESTIGATION_REQUIRED`（预分流与服务端判定漂移）→ 回退到 `submit_investigation(text)`（Run 主链路，幂等键机制不变，AC2）。
  - 普通意图的发送不进入 `send-intent.ts` 的 Run 幂等恢复链路（Run 链路只服务于调查）。
- **会话页普通回复渲染**：`conversation-turns.ts` 投影需支持 `run_id=null` 的 assistant 消息
  （普通回复）：
  - 现状：assistant 无 `run_id` 会被记为 `ASSISTANT_MESSAGE_RUN_MISSING` 协议问题。
  - 改：assistant 消息带 `run_id` → 继续作为调查输出；`run_id` 为空 → 作为**普通回复**，
    按创建时间就近配对到其前一条 user 消息（同一会话、时间相邻、无 Run 关联），
    渲染为轻量对话气泡；无前驱时作为独立回复展示，不再视为协议异常。
- **「停止」按钮**：运行中（`queued`/`running`）的调查卡片（`AssistantReply` 非终态分支）
  增加「停止」按钮 → `cancel_run(run_id)`；成功（204）后失效 runs/messages 查询；
  SSE 以 `run_cancelled` 收尾；既有 `cancelled` 状态的消息渲染分支（「调查已取消」）已存在，
  无需新增（AC4 的 UI 反馈）。
- **「待审批」入口**：在会话模式的第二栏 `Sidebar` 新增「待审批」项，导航到
  `/workbench/approvals`（审批属会话工作台模块，不放最左全局模块轨，见 §6 决策 3）。
- **提案列表页 + 审批进入**：新增 `frontend/src/features/approvals/ApprovalsPage.tsx`：
  - 状态过滤标签（全部 / 待审批 / 已批准 / …）+ cursor 分页（沿用 `fetch_all_pages` 模式）；
  - 空态如实展示；行内展示 `title / status / mode / created_at`；
  - 点击行 → 进入提案详情页 `/workbench/approvals/:proposal_id`；
  - 详情页复用/抽取 `ActionProposalPanel` 的审批与执行交互：把面板改为按 `proposal_id`
    取数（`get_action_proposal`）而非仅按 `run_id`（`get_run_action_proposal`），
    保持「只读快照 + 固定 local_operator 审批 + 二次确认执行」现有语义（AC10）。

### 2.6 接口契约汇总

| 方法 | 路径 | 说明 | 状态码 |
|---|---|---|---|
| POST | `/sessions/{session_id}/messages` | 普通消息（调查意图 409 回退） | 201 / 409 / 404 / 422 |
| POST | `/runs/{run_id}/cancel` | 取消运行中 Run（幂等） | 204 / 404 / 409 |
| GET | `/action-proposals` | 全局提案安全摘要，cursor+status 过滤 | 200 / 422 |
| GET | `/action-proposals/{proposal_id}` | 既有提案详情（不变） | 200 / 404 |

- 兼容性：`POST /sessions/{id}/runs` 主链路行为不变；`GET /sessions/{id}/messages` 现在也会返回
  `run_id=null` 的消息（普通消息），前端按 §2.5 投影适配，契约字段不变。
- 生成契约：`frontend/src/api/v1/generated.ts` 经 `npm run generate:api` 重新生成（后端起在 8000），
  禁止手工编辑。

### 2.7 安全与脱敏

- 普通消息轻量回复**不触发任何 Tool / Connector / 外部连接**，回复为确定性模板（非模型输出）。
- 意图判定失败按普通对话处理（不误触发调查）。
- 提案列表仅返回 §2.4 白名单摘要字段，不经列表透传 evidence 原文、原始工具输出或未脱敏内容（AC9）。
- 取消只改 Run 状态与事件，不产生部分执行状态；对已提审提案无副作用。
- Trace / SSE 语义不变：`run_cancelled` 已属终态事件，前端只展示状态摘要。

## 3. 文件改动面

### 后端（修改 + 新增）

- `backend/src/application/message_routing.py`（**新增**）：`requires_database_context` 公开函数。
- `backend/src/application/plain_messages.py`（**新增**）：`SendPlainMessageCommand`、
  `PlainMessageApplicationService`。
- `backend/src/application/services.py`（修改）：取消用例 `cancel_run`；
  `execute_run` 事件循环加协作式取消检查点；`_requires_database_context` 改引公开函数。
- `backend/src/application/errors.py`（修改）：新增 `InvestigationRequiredError` 等应用错误。
- `backend/src/application/action_services.py`（修改）：`list_proposals` 只读用例。
- `backend/src/api/v1/dependencies.py`（修改）：`V1Services` 装配 `PlainMessageApplicationService`。
- `backend/src/domain/records.py`（修改）：`ActionProposalCursor`。
- `backend/src/infrastructure/persistence/repositories.py`（修改）：`is_cancelled` 轻量状态查询。
- `backend/src/infrastructure/persistence/action_repositories.py`（修改）：`list_page`。
- `backend/src/api/v1/routes.py`（修改）：3 个新端点 + `APPLICATION_ERROR_STATUS` 新映射。
- `backend/src/api/v1/schemas.py`（修改）：`PlainMessageResponse`、`ActionProposalSummaryResource`、
  `ActionProposalListResponse` 等。
- `backend/src/api/v1/resources.py`（修改）：`action_proposal_summary_resource` 等。
- `backend/src/api/v1/cursors.py`（修改）：注册 `ActionProposalCursor` 编解码。
- 后端测试（新增/修改）：`test_plain_message_api.py`、`test_run_cancel.py`、
  `test_action_proposal_list.py`、既有 `test_p43_service_context.py` 判定断言迁移等。

### 前端（修改 + 新增）

- `frontend/src/api/v1/generated.ts`（重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`（修改）：`send_plain_message` / `cancel_run` /
  `list_action_proposals` 方法 + 类型。
- `frontend/src/api/v1/queries.ts`（修改）：新增 query key / query / mutation。
- `frontend/src/features/workbench/WorkbenchPage.tsx`（修改）：`submit_text` 统一发送路由、
  停止按钮。
- `frontend/src/features/workbench/conversation-turns.ts`（修改）：普通回复（`run_id=null`）投影。
- `frontend/src/features/workbench/ActionProposalPanel.tsx`（修改）：支持按 `proposal_id` 取数。
- `frontend/src/features/approvals/ApprovalsPage.tsx`（**新增**）：提案列表页。
- `frontend/src/app/App.tsx`（修改）：`/workbench/approvals` 与 `:proposal_id` 路由。
- `frontend/src/features/shell/Sidebar.tsx`（修改）：「待审批」入口。
- 前端测试：发送路由（普通→轻量 / 调查→回退）、普通回复投影、停止按钮、提案列表页。

### 文档

- `docs/接口清单.md`（修改）：会话工作台模块三个缺表项标记为已交付，补新端点行。

### 明确无改动

- 无数据库迁移；无配置项/环境变量新增；无 Connector/凭据新增；`data/`、`demo/` 不动。
- `POST /sessions/{id}/runs`、`GET /sessions/{id}/messages` 的既有字段契约不变。

## 4. 切片与验证（指引，不写死）

建议拆 **3 片**（后端 2 片 + 前端 1 片，与 PRD 三个功能一一对应，便于独立验收）：

- **S1：独立消息通道（后端）**。`requires_database_context` 收敛 + `POST /sessions/{id}/messages`
  + 普通回复落库。验收语义：普通消息返回 assistant 模板回复、不创建 Run（AC1/AC3）；
  调查意图 409（AC2 的服务端判定面）。
- **S2：取消 Run + 全局提案列表（后端）**。`cancel_run` + 协作式检查点 + `GET /action-proposals`
  + 摘要资源。验收语义：AC4/AC5/AC6、AC7/AC8/AC9。
- **S3：前端工作台适配（前端）**。发送路由 + 普通回复投影 + 停止按钮 + 待审批页 +
  提案详情进入。验收语义：AC10、AC2 前端回退面、AC11 前端回归。

涉及门禁项：**新增公开 API**（3 个端点）⇒ 本 Design 经 arch-review PASS + 用户确认后方可开发；
无迁移、无 Connector、无凭据、无权限/审批能力扩大（审批交互复用既有固定动作闭环）。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 协作式取消的「下一个检查点」前，单次 LLM 调用仍会跑完 | 文档与 UI 如实标注「取消在安全点生效」；事件以 `run_cancelled` 收尾，不伪造「立即终止」 |
| cancel 与 execute_run 并发竞争（claim 先 / cancel 先） | `transition_status` 为 CAS 语义，任一分支都收敛到唯一终态；`_complete_*` 对终态短路，不覆盖 |
| 普通消息端点无幂等键，失败重试可能重复落库 | 前端只对「明确未知结果」提示重发；PRD 未要求幂等，列入待确认决策 5 |
| 前端把调查消息误走普通通道 | 服务端权威判定：调查意图一律 409 回退，前端不自行改写服务端意图 |
| 提案列表聚合查询规模 | cursor 分页 + limit 上限 100，复用既有分页基建；不做全量扫描 |
| 会话投影改造回归（普通回复 vs 调查输出） | `conversation-turns.ts` 单测锁定两类消息的投影路径；前端 `test` 全量回归 |

- 回滚：移除 3 个新端点与前端入口即回退（无迁移、无配置、无 Connector）。
- 门禁项清单：新增公开 API（`POST /sessions/{id}/messages`、`POST /runs/{id}/cancel`、
  `GET /action-proposals`）⇒ Design → Review → 用户确认；未新增迁移/凭据/权限/审批执行能力。

## 6. 待用户确认的设计决策

1. **普通消息的发送语义**：新增 `POST /sessions/{id}/messages` 端点、服务端权威判定，
   调查意图返回 409 由前端回退到 Run 主链路（而非在 `/messages` 内直接建 Run）——是否确认？
2. **意图判定**：复用既有关键词规则收敛为公开函数 `requires_database_context`（确定性，
   不引入轻量 LLM 分类）——是否确认？
3. **「待审批」入口位置**：放会话模式第二栏 `Sidebar`（审批属会话工作台模块，不占最左
   全局模块轨的四个正式模块位）——是否确认？
4. **普通消息模板回复**：首版用确定性模板（含「未启动调查」诚实说明），不调用轻量 LLM——
   是否确认？
5. **普通消息端点不做幂等键**：失败重试可能产生重复消息（前端提示重发，不自动重试）——
   是否确认？
6. **协作式取消的诚实边界**：取消在下一个事件检查点生效、单次 LLM 调用可能跑完，不承诺
   强终止——是否确认？
