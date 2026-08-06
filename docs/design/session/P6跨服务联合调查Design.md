# P6 跨服务联合调查——会话多服务 + 多 Run 聚合 Design

> 状态：已确认
> 更新：2026-08-06
> 关联：`docs/prd/session/P6-cross-service-investigation.md`（已确认决策：会话多服务 + 多 Run 聚合 / 触发方式：会话多选服务 / sessions.service_id 列保留兼容方案一）、
> `docs/产品定义.md` §2.1/§4、`docs/开发规范.md` §2/§3/§6、
> `backend/src/domain/records.py`、`backend/src/domain/services.py`、`backend/src/application/services.py`、
> `backend/src/api/v1/schemas.py`、`backend/src/api/v1/resources.py`、`backend/src/api/v1/routes.py`、
> `frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/features/shell/WelcomePanel.tsx`、
> `frontend/src/features/workbench/send-intent.ts`、`frontend/src/features/workbench/conversation-turns.ts`、
> `frontend/src/features/services/ServiceCenterPage.tsx`。

## 1. 目标与范围

在现有「会话 → Run → 单服务调查链路」之上，把服务上下文从**单值**扩展为**多值**：
一个会话可关联多个已接入服务；会话内一次提问对每个选中服务各建一个 Run（复用既有单服务 `create_run`
与执行链路，不改变 Run 为多服务）；前端在同一个对话线程内按服务分组聚合展示各 Run 的结果。
整个过程纯只读，各服务独立降级，不跨服务推理。

### 做什么

- **会话层多服务关联**：新增 `session_services` 关联表（会话 ↔ 服务，多对多）+ 数据库迁移；
  `sessions.service_id` 单值列**保留兼容**（方案一）。
- **会话创建接受 `service_ids`**：`POST /sessions` 可携带 `service_ids: string[]`（0 个或多个）；
  `POST /services/{id}/sessions` 单服务快捷入口保留，仍写单值列 + 关联表。
- **多 Run 发起**：`POST /sessions/{id}/runs` 请求可携带 `service_id`，为多服务会话指定该 Run 的目标服务；
  前端对一个会话内的多服务调查，为每个服务各提交一次 Run（顺序发起）。
- **前端多选**：会话工作台欢迎页服务选择从单选 `select` 改为多选 checkbox 列表；支持勾选 0 个或多个。
- **按服务分组聚合展示**：对话线程内一个用户问题对应 N 个 Run，按服务分组展示各自结论/Trace/证据。
- **会话页服务集合展示**：会话页展示本次调查涉及的服务集合（多服务标识），不伪造单服务。
- **服务中心多选发起**：服务中心「发起调查」支持多选服务，创建关联多服务的会话并跳转联合调查。

### 明确不做

- 不做单 Run 跨服务：不把 `DiagnosisRunData` / DBAgent / 工具的 service_id 改成多值集合；Run 仍单服务。
- 不做多服务证据的自动交叉归因/关联分析（各服务独立调查，前端分组展示）。
- 不做服务选择权限管理、多租户、并行度控制框架（首版固定顺序发起）。
- 不做单 Run 内多 Agent 跨服务联合取证。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）、S1–S4 评测路径、既有 `GET /services` 契约。
- 不修改 `DiagnosisRunData` 结构、DBAgent/工具链 service_id 语义（保持单值）。
- 不做会话中途切换/编辑服务上下文。

## 2. 设计决策

### 2.1 数据模型：`session_services` 关联表

新增关联表，会话与服务多对多；`sessions.service_id` 单值列保留（方案一兼容）。

| 列 | 类型 | 约束 |
|---|---|---|
| `session_id` | UUID | FK → `sessions.id`（`ondelete=RESTRICT`） |
| `service_id` | String(64) | NOT NULL；复合主键之一 |
| `created_at` | DateTime(timezone=True) | NOT NULL |

- 复合主键 `(session_id, service_id)`；追加 `service_id` 索引（服务 → 会话反向查询，供服务中心活动/关联检索）。
- CHECK 约束沿用既有 `sessions.service_id` 白名单模式：
  `service_id IN ('postgres-production', 'postgres-staging')`（与静态注册表一致；注册表是唯一事实源，迁移内白名单与现有模型保持一致）。
- 迁移 `upgrade` 只建表，不动既有数据；`downgrade` 在有数据时拒绝回滚（沿用 P4.3 迁移的安全回滚模式）。
- 既有旧会话（仅 `sessions.service_id` 列有值、无关联行）读取时自动兜底为单服务集合（见 2.2），既有数据不受影响。

### 2.2 会话领域模型与读写

- `SessionData` 新增字段：`service_ids: tuple[str, ...] = ()`（有序去重后的服务集合）。保留既有 `service_id` 单值字段。
- **写路径**：
  - `POST /sessions` 普通会话：解析 `service_ids`（合法、去重、保持传入顺序），只写关联表，`sessions.service_id` 列保持 `NULL`；
  - `service_id` 单值参数（旧前端/旧测试兼容）：视为单服务，写单值列 + 关联表，保证旧行为回归（AC6）；
  - `POST /services/{id}/sessions` 单服务快捷入口：写单值列 + 关联表。
- **读路径**：`session_service_ids = 关联表集合 if 非空 else ([service_id] if service_id else [])`，
  旧会话无需数据迁移即能正确展示服务集合（AC10）。
- Repository（`SqlAlchemySessionRepository`）：`add` 同时写 SessionRecord 与关联行；`get_by_id`/`list_page` 读取并组装
  `service_ids`；`save` 不修改服务上下文（本 PRD 不做会话内服务编辑）。
- `SessionResource`（API 资源）新增 `service_ids: list[str]`；`service_id` 单值字段保留（向后兼容）。

### 2.3 会话创建校验

`CreateSessionCommand` / `CreateSessionRequest` 新增 `service_ids`：

- `service_ids` 为空 → 不关联服务（行为与现状一致，AC5）。
- 每个 id 必须属于静态注册表（复用 `ServiceRegistry.service_ids()`）；未注册 → `ServiceNotFoundError`（404）。
- 重复 id → 拒绝（去重后数量不一致即报错，返回 422 VALIDATION_ERROR）。
- `service_id` 与 `service_ids` 同时提供时以 `service_ids` 为准；仅 `service_id` 时按单服务处理（兼容）。

### 2.4 多 Run 发起：复用 `create_run` + 显式 `service_id`

- `CreateRunRequest` / `CreateRunCommand` 新增可选 `service_id: str | None`。
- `_accept_run_in_transaction` 服务绑定解析：
  1. 显式 `command.service_id` 提供 → 校验属于会话服务集合（关联表 ∪ 单值列兜底），否则拒绝；
  2. 未显式提供：
     - 会话服务集合恰有 1 个 → 沿用该服务（既有单服务会话零改动，AC6 回归）；
     - 会话服务集合为空，且 query 需要数据库上下文 → `ServiceContextRequiredError`（与现状一致）；
     - 会话服务集合 > 1 且 query 需要数据库上下文 → 拒绝并提示指定目标服务（诚实，不猜服务）；
     - query 不需要数据库上下文（server/log）→ service_id 保持 `None`（不依赖服务上下文）。
- Run 仍单服务：`DiagnosisRunData.service_id` 单值不变，执行链路（Coordinator → DBAgent → Tool）不变。
- **前端编排**：一个多服务调查对每个选中服务各提交一次 `POST /sessions/{id}/runs`（各自幂等键），
  **顺序发起**（简单可控，避免一次压垮；每次受理后由既有 BackgroundTasks 后台执行，天然低并发）。
- **独立降级**：每个 Run 独立执行、独立终态；单个失败只影响该服务的展示，不牵连其他服务（AC7）。
- 证据归因：Run 资源 `service_id` 单值已携带目标服务；前端按 Run 的 `service_id` 分组展示即可。

### 2.5 前端：欢迎页多选

- `WelcomePanel` 服务选择从单选 `select` 改为**多选 checkbox 列表**（PRD 开放问题 #2 建议形态）。
- Props 从 `selected_service_id?: string` / `on_service_change?: (id) => void`
  改为 `selected_service_ids: string[]` / `on_service_change: (ids: string[]) => void`。
- 未勾选 → 空数组，行为与现状一致（不绑定服务）。
- `ConversationHome` 持有 `selected_service_ids: string[]`，创建会话时传 `service_ids`。

### 2.6 前端：多 Run 提交与恢复（send-intent 升级 v2）

- 现有 `SessionRunSendIntent`（单 Run：一个幂等键 + accepted_run_id + input_message_id）扩展为支持 N 个 Run：
  - `send-intent.ts` 升级为 v2：单个 intent 内携带 `runs: Array<{ service_id?, idempotency_key, accepted_run_id?, input_message_id?, phase }>`，
    统一一次调查的 N 个目标；版本升级并兼容读取 v1（旧 intent 视为单 Run）。
  - `WorkbenchPage` 自动提交逻辑按 `runs` 遍历顺序提交 N 个 `create_run`；恢复/对账逻辑校验 N 个 Run 均已受理。
  - 每个 Run 独立幂等键，恢复时按各 Run 的 accepted_run_id/input_message_id 校验（沿用既有对账协议）。
- 未多选的单服务调查退化为单 Run intent，行为与现状一致（AC6）。

### 2.7 前端：按服务分组聚合展示

- `ConversationInvestigation` 补充 `service_id`（取自 Run 资源），供分组与服务标识。
- `conversation-turns.ts` 投影升级：对**连续出现的相同 query 用户消息**（同一轮多服务调查产生的 N 条用户消息）
  合并为一个对话轮次，收集其下全部 Run 作为该轮的多服务调查集合；单服务场景保持现状。
- 渲染：一个用户问题气泡 + N 个「服务调查结果区」（服务名/logo/类型标识 + 各自 DiagnosisResultPanel + TraceCard + 独立降级提示）。
- 恢复/刷新后同样从 messages + runs 数据重建分组（确定性，不依赖本地状态）。

### 2.8 前端：会话页服务集合展示

- `SessionWorkspace` 顶部服务上下文从单服务改为服务集合：按 `session.service_ids` 展示服务列表；
  单服务时展示该服务，多服务时展示列表，未关联时不展示（AC8，不伪造）。

### 2.9 前端：服务中心多选发起

- `ServiceCenterPage` 每行服务增加多选 checkbox + 顶部/批量「发起调查」入口；
  选中 ≥1 个服务后创建关联这些服务的会话（`POST /sessions` + `service_ids`），跳转会话工作台并预填联合调查。
- 保留单行「发起调查」快捷入口（走 `POST /services/{id}/sessions`，AC5 回归）。

### 2.10 安全、脱敏与诚实

- 纯只读：不新增任何写路径；各服务仍按既有单服务链路鉴权/脱敏。
- 无凭据/DSN/env 名进入聚合展示、Trace、日志或接口响应（沿用 `_safe_event_data` 白名单与网关脱敏兜底）。
- 诚实：未选服务如实；每个服务结果独立展示，不做跨服务关联推理暗示；失败服务独立降级。
- 前端只读恢复：不从本地状态伪造服务端事实。

## 3. 文件改动面

### 后端

- `backend/migrations/versions/20260806_06_p6_session_services.py`：新增（建 `session_services` 表，upgrade/downgrade）。
- `backend/src/infrastructure/persistence/models.py`：新增 `SessionServiceRecord`。
- `backend/src/domain/records.py`：`SessionData` 新增 `service_ids: tuple[str, ...]`。
- `backend/src/domain/services.py`：无改动（复用 `ServiceRegistry.service_ids()`）。
- `backend/src/infrastructure/persistence/repositories.py`：`SqlAlchemySessionRepository` 读写关联表，组装 `service_ids`。
- `backend/src/application/contracts.py`：`CreateSessionCommand` 加 `service_ids`；`CreateRunCommand` 加 `service_id`。
- `backend/src/application/services.py`：`create_session` 校验/持久化多服务；`_accept_run_in_transaction` 服务绑定解析。
- `backend/src/application/service_center.py`：`create_service_session` 同时写单值列 + 关联表。
- `backend/src/api/v1/schemas.py`：`CreateSessionRequest.service_ids`、`CreateRunRequest.service_id`、`SessionResource.service_ids`。
- `backend/src/api/v1/resources.py`：`session_resource` 映射 `service_ids`。
- `backend/src/api/v1/routes.py`：`create_session` 传递 `service_ids`；`create_run` 传递 `service_id`。
- 测试：`backend/tests/test_p6_cross_service.py`（新增），以及
  `test_p43_service_context.py`、`test_p4_service_center.py`、`test_postgres_connector.py`、`test_agent_gateway.py`、
  `test_p2_schema.py`、`test_p2_api_v1.py` 等回归。

### 前端

- `frontend/src/features/shell/WelcomePanel.tsx`：多选 checkbox 列表。
- `frontend/src/features/workbench/WorkbenchPage.tsx`：多选状态、多 Run 提交/恢复、服务集合展示、分组渲染。
- `frontend/src/features/workbench/send-intent.ts`：v2 多 Run intent（兼容 v1）。
- `frontend/src/features/workbench/conversation-turns.ts`：同 query 多用户消息合并为多服务调查轮次；`ConversationInvestigation.service_id`。
- `frontend/src/features/workbench/TraceCard.tsx` / `DiagnosisResultPanel.tsx`：服务标识透传（如需要）。
- `frontend/src/features/services/ServiceCenterPage.tsx`：多选 + 批量发起。
- `frontend/src/api/v1/client.ts`、`queries.ts`：`create_session`/`create_run` 携带新字段；`generated.ts` 由 `npm run generate:api` 重生成（禁止手改）。
- 测试：`WelcomePanel.test.tsx`、`send-intent.test.ts`、`conversation-turns.test.ts`、`App.test.tsx` 等更新/新增。

### 工作包文档

- `docs/workpack/P6-cross-service-investigation/plan.md`、`review.md`、`evidence.md`；`docs/workpack/README.md` 登记。

## 4. 切片与验证

### S1：后端数据模型与多服务会话关联

- 覆盖 PRD AC2、AC5、AC6（后端）、AC10、AC11（`create_session` 相关）、AC13。
- 验证：`session_services` 迁移 upgrade/downgrade；`create_session(service_ids=...)` 持久化多服务；
  未注册/重复 id 拒绝；单服务 `service_id` 参数与 `POST /services/{id}/sessions` 回归；
  旧会话读取兜底；`SessionResource.service_ids` 契约。
- 执行：`backend/` 下 `..\.venv\Scripts\python.exe -m pytest tests/test_p6_cross_service.py -q`。

### S2：后端多 Run 发起

- 覆盖 PRD AC3（后端）、AC7（后端独立降级）、AC6（Run 服务绑定回归）、AC13。
- 验证：`create_run` 显式/兜底 service_id 绑定、集合 >1 未指定时拒绝、空集合需数据库上下文时拒绝、
  每 Run 单服务链路与事件 service_id 白名单；既有单服务 Run 链路回归。
- 执行：`..\.venv\Scripts\python.exe -m pytest tests/test_p6_cross_service.py tests/test_p43_service_context.py -q`。

### S3：前端多选、多 Run 聚合展示、服务集合、服务中心多选

- 覆盖 PRD AC1、AC3（前端）、AC4、AC8、AC9、AC12、AC14（前端回归）。
- 验证：欢迎页多选创建多服务会话；多服务调查自动提交 N 个 Run；对话线程按服务分组展示；
  会话页服务集合；服务中心多选发起；未选/单服务回归；前端 `typecheck`/`test`/`build`。
- 执行：`frontend/` 下 `npm run typecheck`、`npm run test`、`npm run build`。

### 全量门禁

- 后端全量 `..\.venv\Scripts\python.exe -m pytest tests -q` 全绿（含 S1–S4 mock 评测回归）；
- `git diff --check` 通过；diff 无 DSN、密码、`sk-`、原始异常；只暂存本工作包文件。

## 5. 风险、回滚与门禁

- 风险：多 Run 恢复对账复杂度上升（send-intent v2）；同 query 连续用户消息分组可能把「不同时刻的相同提问」
  误合并。缓解：分组仅合并连续出现且 created_at 相邻的相同 query 用户消息，单服务场景不变；
  若误合并，只影响展示、不伪造服务端事实。
- 回滚：迁移 downgrade 有数据守卫；后端去掉 `service_ids`/Run `service_id` 扩展即回退；前端 send-intent v2 兼容 v1 读取。
- 本 Design 涉及**数据库迁移 + 公开 API 变更**，必须经 Review → 用户确认后方可进入 workpack 实施。
- 确认后更新本 Design 状态为「已确认」，再创建 `docs/workpack/P6-cross-service-investigation/plan.md`。

## 6. 待用户确认的设计决策

1. 多选 UI 形态：欢迎页服务选择改为 **checkbox 列表**（PRD 开放问题 #2 建议形态）——是否确认？
2. 多 Run 发起顺序：首版**顺序发起**（每个 Run 提交后再提交下一个，后台执行天然低并发）——是否确认？
3. `service_ids` 与 `service_id` 同时提供时以 `service_ids` 为准、仅 `service_id` 按单服务兼容——是否确认？
4. 旧会话（仅 `sessions.service_id` 列）读取时自动兜底为单服务集合、不迁移历史数据——是否确认？
5. send-intent 升级 v2 支持单 intent 多 Run，且兼容读取 v1——是否确认？
6. 同 query 连续用户消息合并分组（时间相邻判定）作为多服务聚合展示的数据依据——是否确认？
