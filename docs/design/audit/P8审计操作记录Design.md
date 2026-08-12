# P8 审计操作记录 —— 跨服务跨会话的活动检索 · Design

> 状态：已确认
> 更新：2026-08-12
> 用户已确认（2026-08-12）：§6 决策 1–4 全部拍板。
> 关联：`docs/prd/audit/P8-audit-activity-log.md`（已确认 PRD，issue #62）、
> `docs/产品定义.md` §2.3/§4（服务中心责任含"留痕"、安全治理层含"审计"）、
> `docs/开发规范.md`（只读/脱敏/诚实降级）、`docs/架构与开发路径.md`（一条主脊、Trace 安全投影）、
> `docs/接口清单.md` 第五部分（审计建议）、`docs/design/service-center/P8服务注册Design.md`（同批 P8，审计覆盖其注册/移除/测试连接动作）、
> `docs/prd/approval/P5-controlled-action-real.md`（受控动作闭环）

## 1. 目标与范围

一句话目标：在既有 `GET /services/{id}/activities` 安全摘要先例之上，新增跨服务跨会话的全局审计检索 `GET /audit/activities`——运维可按时间窗、服务、动作类型、结果过滤审计活动（调查 Run + 受控动作事件），满足合规审查与安全留痕；无新增持久化、无迁移、无凭据。

### 做什么
- 新增 `GET /audit/activities`：跨会话跨服务审计活动安全摘要分页列表，支持 from/to 时间窗、service_id、action_type、result 过滤，cursor 分页。
- 覆盖两类活动：调查 Run（读时状态派生的安全摘要）与受控动作里程碑事件（提案/审批/执行完成/验证完成/拦截/失败）。
- 复用 `service_center.list_activities` 的脱敏收敛纪律（限长、白名单字段、不含原始证据/工具输出/异常/凭据）。
- 前端新增"审计操作记录"入口页（列表 + 过滤 + 详情跳转），空态/失败态诚实展示。

### 明确不做（对齐 PRD）
- 不做身份/审批人模型；审批人字段如实标注"未记录"，不伪造、不暴露演示占位身份。
- 不做日志/Trace 原始事件检索；不暴露 CoT/Prompt/原始 SQL/原始工具输出/异常详情/凭据/DSN/`sk-`。
- 不做告警通知 / 导出 / 报表。
- 不新增持久化、不迁移（复用 `diagnosis_runs` / `action_proposals` / `action_events` 既有表）。
- 不改变既有 `GET /services/{id}/activities` 行为与契约。
- 审计检索纯只读，不触发任何目标服务连接。

## 2. 设计决策

### D1 · 统一审计流：双源有界归并 + 统一 (time, id) 键集游标

**两个事实源按统一行投影**（PRD 明令无迁移 → 不物化统一视图，改为读时归并）：

| 源 | 行 | 审计类型（读时派生/原样） | 时间锚点 |
|---|---|---|---|
| A · `diagnosis_runs`（JOIN `sessions` 取标题） | 每条 Run 一行 | queued→`run_created`、running→`run_running`、succeeded→`run_completed`、failed→`run_failed`、cancelled→`run_cancelled` | `created_at` |
| B · `action_events`（JOIN `action_proposals`→`diagnosis_runs`→`sessions`） | 每条事件一行 | 事件类型原样（6 类收敛子集，见 D2） | `occurred_at` |

- **统一排序键** `(time desc, id desc)`：游标 `AuditActivityCursor(created_at, id)`。id 为 uuid4（run_id 或 action 事件 id），**跨表全局唯一**，因此 `(time, id)` 比较在两侧 SQL 中无歧义；两侧以同一游标做键集过滤（`time < c OR (time = c AND id < c)`）。
- **每页有界归并**：两侧各取 `limit+1` 行，Python 按 (time desc, id desc) 归并取前 `limit`，next_cursor 取末项；`has_more ⟺ 归并后行数 > limit`（可证明：每侧取 min(侧总行数, limit+1)，两侧之和 > limit 当且仅当剩余总量 > limit）。
- **时间锚点语义**（与既有 `list_activities` 先例一致）：Run 项恒用 `created_at`，类型反映读时当前状态；终态不改变活动时间锚点。窗口过滤对 A 侧作用于 `created_at`、B 侧作用于 `occurred_at`。
- **服务归属取 `DiagnosisRunRecord.service_id`**（Run 权威归属列），比 `SessionRecord.service_id` 更准——P6 跨服务联合调查的会话承载多服务、每服务一个 Run，服务过滤必须以 Run 的 service_id 为准；action 侧经 proposal → run 取同一列。

### D2 · 动作类型收敛子集 + 结果枚举映射

- **审计类型枚举（11 类，PRD 开放问题 Q2 收敛子集）**：
  - Run 派生 5 类：`run_created` / `run_running` / `run_completed` / `run_failed` / `run_cancelled`
  - action 里程碑 6 类：`proposal_created` / `approval_recorded` / `execution_completed` / `verification_completed` / `action_blocked` / `action_failed`
  - **排除 4 类瞬时事件**：`execution_requested` / `execution_started` / `precondition_checked` / `verification_started`（对审计审阅无信息增益，与终态/决策事件重复表达）
- **结果枚举 AuditOutcome（10 值）与映射**：

| 审计类型 | 结果 |
|---|---|
| run_created / run_running | `running` |
| run_completed | `succeeded` |
| run_failed / action_failed | `failed` |
| run_cancelled | `cancelled` |
| proposal_created | `pending_approval` |
| approval_recorded | `approved`（事件 data.status=approved）/ `rejected`（=rejected） |
| execution_completed | `succeeded` |
| verification_completed | `verified` |
| action_blocked | `blocked` |
| action_failed（data.status=expired） | `expired`（批准过期未执行，`action_services.py` 以 ACTION_FAILED 事件 + status=expired 落库，见 `_request_execution_in_transaction`） |

- 派生规则：approval_recorded / action_failed 按事件 `data.status` 派生结果（approved/rejected/expired），其余类型按上表固定映射——保证过期提案如实显示"expired"而非"failed"。

- 过滤参数 `action_type` / `result` 用 FastAPI 枚举 Query 参数，非法值自动 422 `VALIDATION_ERROR`（PRD"过滤参数非法时返回明确错误"）。

### D3 · 安全摘要收敛纪律（复用既有先例，绝不整包透传）

- **Run 项**复用 `service_activity` 收敛字段：`summary`（`DiagnosisResultRecord.summary` ≤800）、`severity`、`confidence`、`proposal_status`、`verification_status`（修复闭环状态）。
- **Action 项**从事件 `data` 显式提取白名单字段（`_safe_action_event_data` 落库时已收敛，资源层**二次限长/类型校验兜底**）：`summary`（字符串 ≤500）、`mode`（mock/target）、`status`（受控枚举）、`action_id`（固定动作 ID）。**绝不整包 dump 事件 data JSON**——防未来字段漂移把未审查内容漏进审计接口。
- **审批人字段**（AC7）：仅 `approval_recorded` 项的 `approval_actor` 恒为字面量 `"未记录"`——事件类型本身就是"审批已记录"的声明（无需再 join `action_approvals` 表）；`action_approvals.actor='local_operator'` 是演示占位身份（`产品定义.md` §7 未决），不得冒充真人审批人；审批决策（approved/rejected）与审批时间（事件 occurred_at）如实展示。
- **无服务绑定 Run**（`service_id` NULL，普通对话调查）计入审计流，service_id 过滤时自然排除；被移除服务的历史活动保留（前端服务标题映射失败时诚实回退显示 service_id 原文）。
- 全链路只读：不触发目标服务连接、不读取 DSN/凭据、错误按既有 `APPLICATION_ERROR_STATUS` 收敛。

### D4 · 接口契约（新增公开 API）

`GET /api/v1/audit/activities`

| Query 参数 | 类型 | 说明 |
|---|---|---|
| `from` / `to` | datetime | 时间窗（可选）；`from > to` → 422 |
| `service_id` | str ≤64 | 服务过滤（可选）；未知 service_id → 200 空列表，不抛错（AC3，**不做 registry 校验**） |
| `action_type` | 11 值枚举 | 审计类型过滤（可选） |
| `result` | 10 值枚举 | 结果过滤（可选） |
| `cursor` | 不透明 | `AuditActivityCursor` 编解码；非法 → 400 `INVALID_CURSOR` |
| `limit` | 1–100，默认 20 | 分页大小 |

响应 `AuditActivityListResponse`（结构对齐 `ServiceActivityListResponse`）：

```
AuditActivityResource
├─ id: UUID            # run_id（kind=run）或 action 事件 id（kind=action）——统一游标锚
├─ kind: run | action
├─ type: 11 值枚举
├─ occurred_at: datetime
├─ service_id: str | null
├─ session_id: UUID, session_title: str
├─ outcome: 10 值枚举
├─ summary: str | null      # 脱敏摘要
├─ run 项：run_id, severity, confidence, proposal_status, verification_status
└─ action 项：proposal_id, action_id: str|null, mode: str|null, approval_actor: "未记录"|null
```

- 注：action 项 `action_id` / `mode` **可空**——`approval_recorded` 事件 data 只有 status/summary（`action_services.py` 写事件时不携带 action_id/mode），诚实置空而非伪造。

响应整体 `AuditActivityListResponse`（结构对齐 `ServiceActivityListResponse`）：`items` + `page: {next_cursor, has_more}` + `meta: {request_id, trace_id}`。

- **详情跳转锚**：run 项 → 既有 `/workbench/sessions/:session_id/runs/:run_id`；action 项 → 既有 `/workbench/approvals/:proposal_id`（P8 会话工作台闭环已提供全局提案详情页，均可定位）。
- 前端 API 类型由 `npm run generate:api` 生成（`frontend/src/api/v1/generated.ts`），禁止手改。

### D5 · 前端入口与页面

- **入口**：服务中心第二栏子导航（`ServiceContextNav`）与"服务监控"并列新增"审计操作记录"；路由 `/audit`，走运维模式壳（`ProductShell` `is_operations`），最左轨"服务中心"图标在 `/audit` 点亮（与 `/monitor` 同款先例）。
- **页面**（`frontend/src/features/audit/AuditPage.tsx`）：过滤条（from/to 时间窗、服务下拉、类型下拉、结果下拉）+ cursor 分页列表；列表项展示类型徽标、结果、服务、会话标题、时间、脱敏摘要与详情跳转；空态/失败态诚实展示；服务标题由既有 services 查询映射，未知服务回退显示 service_id。
- 与既有页面共用 MSW/Vitest 交互测试模式。

## 3. 文件改动面

### 后端（backend/）
- **新增** `src/domain/audit.py` —— `AuditActivityData`、`AuditActivityKind`（run/action）、`AuditActivityType`（11 值）、`AuditOutcome`（10 值 + 类型→结果映射表）、`AuditActivityCursor`（created_at, id）。
- **新增** `src/domain/audit_repositories.py` —— `AuditActivityRepository` 只读协议。
- **新增** `src/infrastructure/persistence/audit_repositories.py` —— `SqlAlchemyAuditActivityRepository`：A/B 双查询（各自应用时间窗/service_id/类型/结果过滤 + 键集游标，各取 limit+1）+ Python 归并 + `_activity_data` 安全收敛（复用 `service_repositories.py` 的 `_as_*` 映射纪律）。
- **新增** `src/application/audit_service.py` —— `AuditApplicationService.list_activities(query)`：窗口校验（from > to → 明确错误）、过滤组装、归并结果返回。
- **修改** `src/api/v1/schemas.py` —— `AuditActivityResource` / `AuditActivityListResponse`。
- **修改** `src/api/v1/resources.py` —— `audit_activity_resource()`（run/action 分型收敛，事件 data 白名单提取 + 二次限长）。
- **修改** `src/api/v1/cursors.py` —— `AuditActivityCursor` 纳入 encode/decode 与 `__all__`。
- **修改** `src/api/v1/routes.py` —— `GET /audit/activities` 路由（`parse_page_cursor` + `APPLICATION_ERROR_STATUS` 错误收敛）。
- **修改** `src/api/v1/dependencies.py` —— `V1Services` 装配 `audit_service`（仅依赖 `session_factory`，无外部依赖，非可选）。
- **新增** `backend/tests/test_audit_api.py` —— 含双源交错数据的分页/过滤测试（同秒多行、跨表 id 序、窗口边界、未知 service_id 空列表、非法参数 422）。

### 前端（frontend/）
- **新增** `src/features/audit/AuditPage.tsx` + `AuditPage.test.tsx`。
- **修改** `src/app/App.tsx`（`/audit` 路由 + `is_operations`）、`src/features/shell/GlobalNav.tsx`（`/audit` 点亮服务中心）、`src/features/shell/ServiceContextNav.tsx`（"审计操作记录"入口项）。
- **修改** `src/api/v1/client.ts` + `queries.ts`；`generated.ts` 由 `npm run generate:api` 生成。

### 无功能改动部分
- 多 Agent 内核、审批执行链、Trace/SSE、服务中心既有接口、知识库、模型设置、会话工作台交互（本设计不触碰）。

## 4. 可独立验收的改动单元（指引，不写死）

> Design 只给改动单元的验收语义；正式切片拆解、验证命令与提交计划归 `dev-plan` 的 `plan.md`。

建议拆 **2 个独立可验收单元**：
- **U1 后端审计检索 API**：领域模型 + 双源归并仓储 + 应用服务 + `/audit/activities` 路由 + API 测试。验收语义：跨服务跨会话列表（AC1）、时间窗（AC2）、service_id 过滤与未知 ID 空列表（AC3）、类型过滤覆盖两类（AC4）、结果过滤（AC5）、脱敏纪律（AC6）、审批人"未记录"（AC7）、空态不抛错（AC8）、既有 activities 契约不变（AC9）、回归（AC11）。
- **U2 前端审计入口页**：client/queries + AuditPage + 导航入口 + 交互测试。验收语义：入口可访问、过滤可用、空态/失败态诚实、typecheck/test/build 通过（AC10）。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 双源归并分页正确性（同秒多行、跨表 id 序） | 归并算法可证明等价（每侧取 min(侧行数, limit+1)，和 > limit ⟺ 余量 > limit）；测试覆盖交错数据集 |
| 事件 data JSON 未来字段漂移漏进接口 | 资源层只提取白名单字段 + 类型/长度二次校验，**绝不整包 dump data** |
| 时间窗查询无裸时间索引（A 侧 `diagnosis_runs.created_at` 既有索引带 session_id/service_id 前缀，B 侧 `action_events.occurred_at` 无索引） | 应用库数据量受产品使用规模约束，每页有界读取 2×(limit+1)；如需加裸时间索引属后续迁移（本 PRD 禁止迁移） |
| 被移除服务的活动标题不可映射 | 前端回退显示 service_id 原文，诚实不伪造 |
| Run 项时间锚点用 created_at（终态事件时间可能晚于窗口） | 与既有 `list_activities` 先例一致；文档明示"类型反映读时状态、时间锚点恒为创建时间" |

- **回滚**：移除 `/audit/activities` 路由注册 + 前端页面/导航项即完全回退；无迁移、无凭据、无既有契约破坏（纯追加）。
- **门禁项清单**：新增公开 API（`GET /audit/activities`，本 Design 覆盖）；无迁移、无凭据、无 Connector、无真实连接、无写能力（纯只读检索）。

## 6. 待用户确认的设计决策

1. **审计入口放服务中心第二栏子导航**：`ServiceContextNav` 与"服务监控"并列新增"审计操作记录"（路由 `/audit`，运维模式壳，最左轨服务中心图标点亮）。依据：`产品定义.md` §2.3/§4 把"留痕/审计"列为**服务中心责任**；第二栏已有"服务监控"子页先例；避免最左轨加第 5 个图标。备选：最左轨全局第 5 入口（跨模块可见性更强，但轨上多一个正式模块）。**（PRD 开放问题 Q1）**
2. **动作类型收敛为 11 类**：5 类 Run 派生（run_created/run_running/run_completed/run_failed/run_cancelled）+ 6 类里程碑 action 事件（proposal_created/approval_recorded/execution_completed/verification_completed/action_blocked/action_failed），排除 4 类瞬时事件（execution_requested/execution_started/precondition_checked/verification_started）。**（PRD 开放问题 Q2，默认收敛子集）**
3. **审批人字段如实标注"未记录"**：审批存在时 `approval_actor` 恒为"未记录"，不暴露演示占位身份 `local_operator`、不伪造真人；审批决策与时间如实展示。**（PRD 开放问题 Q3，推荐前者）**
4. **无服务绑定 Run 计入审计流**（service_id=null 正常展示，服务过滤时自然排除）；被移除服务的历史活动保留（标题映射失败回退显示 service_id 原文）。理由：审计是全局留痕，缺服务归属的 Run 也是系统活动；服务过滤语义不受影响。

> 用户确认后，将本文件顶部 `> 状态：草稿` 改为 `> 状态：已确认`，再放行到 dev-plan。
