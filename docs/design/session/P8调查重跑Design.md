# P8 调查重跑——重新生成并关联原 Run · Design

> 状态：已确认
> 更新：2026-08-12
> 关联：`docs/prd/session/P8-rerun-investigation.md`（已确认，issue #65）、
> `docs/产品定义.md`（§2.1 会话主入口、§5 安全边界）、`docs/开发规范.md`（§2/§5/§6/§7.2）、
> `docs/架构与开发路径.md`（一条主脊、能力即插件、只读投影）、
> `docs/接口清单.md`（第一大模块缺表：重跑/重新生成）、
> `docs/design/session/P8会话管理Design.md`（已确认 #64，全局 Run 列表——重跑关联关系在此可见）、
> `backend/src/application/services.py`（`accept_run` / `_accept_run_in_transaction` / `_query_fingerprint` / 幂等链路）、
> `backend/src/domain/records.py`（`DiagnosisRunData`）、
> `backend/src/infrastructure/persistence/models.py`（`DiagnosisRunRecord`）、
> `backend/src/infrastructure/persistence/repositories.py`（run/message/idempotency repository）、
> `backend/migrations/versions/20260811_11_p8_service_registration.py`（迁移与 SQLite batch 先例）、
> `frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/features/workbench/conversation-turns.ts`、
> `frontend/src/features/runs/RunsPage.tsx`、`frontend/src/api/v1/queries.ts`、`frontend/src/api/v1/client.ts`。

## 1. 目标与范围

### 一句话目标

对已结束的调查 Run 提供「重新生成」入口：复用原问题的 query 与 service 上下文发起新 Run，
新 Run 显式记录来源（`rerun_of_run_id`），原 Run 的「已被重跑」在会话时间线可追溯，
全程复用既有受理链路与幂等纪律。

### 做什么

1. **重跑端点**：新增 `POST /runs/{run_id}/rerun`（带 `Idempotency-Key` 头，202），
   仅对 `succeeded` / `failed` / `cancelled` 的 Run 可用；复用原 Run 的 session /
   query（经 `input_message_id` 读取）/ service_id 发起新 Run。
2. **来源字段**：`diagnosis_runs` 新增 `rerun_of_run_id`（自引用 UUID，NULL 兼容历史 Run）；
   新 Run 记录来源；`DiagnosisRunResource` / `GlobalRunSummaryResource` 兼容扩展该字段。
3. **关联展示**：新 Run 展示「重跑自 Run X」（直接字段）；原 Run 展示「已被重跑为 Run Y」
   （前端会话时间线纯前端推导，不做后端反查）；全局 Run 列表（#64 已交付）行内展示来源标记。
4. **前端重跑入口**：终态 Run 的答复区提供「重新生成」按钮（loading 防重复点击），
   成功进入新 Run 的跟踪（时间线自动投影）。

### 明确不做

- 不做「编辑后重跑」（改问题再跑 = 普通创建，不走重跑语义）。
- 不做并发重跑限制策略（同 Run 多次重跑靠幂等键防重复提交，不限制不同键的多次重跑）。
- 不做重跑历史的独立页面（关联关系在既有会话时间线 / 全局 Run 列表表达，不新建页面）。
- 不改变既有 `POST /sessions/{id}/runs` 创建行为与 `GET /sessions/{id}/runs` /
  `GET /runs` / `GET /runs/{run_id}` 既有契约（`rerun_of_run_id` 是兼容扩展，历史 Run 为 null）。
- 不做原 Run「已被重跑」的后端反查字段/端点（`rerun_by_run_id`、`GET /runs/{id}/reruns`）——
  前端时间线推导即满足 AC5，避免 N+1 与新增端点。
- 重跑不暴露证据原文、工具输出、CoT/Prompt、凭据/DSN/`sk-`；query 不进响应
  （`DiagnosisRunResource` 既有契约无 query 字段，不新增）。

### 与「一条主脊，能力即插件」硬规则的关系（显式声明）

`docs/架构与开发路径.md` 硬规则 1 禁止「新端点、新流程、新独立脚本/页面」。本 Design 新增
1 个公开端点（`POST /runs/{run_id}/rerun`）——与 #64 全局 Run 列表同型论证：这是
`docs/接口清单.md` 已登记欠账的**既有创建链路的参数化复用接线**，不是新能力：

- 重跑不新增 Tool / Connector / Agent 装配，不触碰工具网关、凭据、审批/执行白名单；
- 重跑复用 `RunApplicationService._accept_run_in_transaction` 的既有受理核心（消息落库 →
  Run 创建 → 幂等键写入 → queued 事件 → touch session），仅增加「来源字段记录」与
  「原 Run 终态预校验」两个参数化挂点；
- 数据变更仅 `diagnosis_runs` 一列自引用来源字段 + 索引，无新表、无新流程。

## 2. 设计决策

### 2.1 重跑端点与幂等（后端）

- **端点形态**：`POST /runs/{run_id}/rerun`（202，响应 `RunResponse`），
  `Idempotency-Key` 头必填（复用 `parse_idempotency_key`）——PRD 开放问题 1/3 推荐方案。
  路径与既有 `POST /runs/{run_id}/cancel`（204）同族；`/runs/{run_id}/rerun` 与
  既有 `/runs/{run_id}` GET、`/runs/{run_id}/events` GET 并存无冲突（方法+路径形状不同）。
- **幂等作用域**：新增常量 `RUN_RERUN_ENDPOINT = "/api/v1/runs/{run_id}/rerun"`，
  幂等键表 `(session_id, endpoint, idempotency_key)` 唯一约束天然隔离「普通创建」与「重跑」，
  同一键不会跨端点碰撞；`IDEMPOTENCY_RETENTION`（24h）复用。
- **重跑指纹**：新增 `_rerun_fingerprint(run_id, query, service_id)`——
  指纹必须包含 `run_id`，否则「相同 query + 相同 service 的两个不同原 Run」用同一幂等键
  重跑会因指纹相同错误重放（防误用，AC4 的纵深）。
- **实现接线**：`RunApplicationService` 新增 `rerun_run(run_id, idempotency_key)`：
  - 单事务内：读原 Run（不存在 → `RunNotFoundError` 404）→ 校验终态
    （`succeeded`/`failed`/`cancelled` 之外 → 新增 `RunNotTerminalError` 409）→
    读原 input message（`SqlAlchemyMessageRepository.get_by_id`，校验
    `session_id` 一致 + `role == user`，异常 → 复用 `RunInputMessageInvalidError` 409，纵深防御）→
    构造 `CreateRunCommand(session_id=原.session_id, query=原消息内容, service_id=原.service_id,
    idempotency_key=输入键)` → 复用 `_accept_run_in_transaction(session, command, fingerprint,
    rerun_of_run_id=run_id)`。
  - 归档会话：`_accept_run_in_transaction` 既有 `SessionArchivedError`（409）自动生效，
    重跑不单独处理——归档会话只读，重跑明确拒绝（PRD 边界「明确错误」）。
  - 唯一键竞争：`IntegrityError` → 复用 `_load_idempotency_after_conflict` 重读路径
    （参数化 `endpoint`，普通创建行为不变）；冲突重读前重新构造 `CreateRunCommand`
    （原 run_id 是输入，可重入）。
  - `_accept_run_in_transaction` 增加可选参数 `rerun_of_run_id: UUID | None = None`
    与 `endpoint: str = RUN_CREATE_ENDPOINT`：**幂等检查（既有 L294）与幂等记录写入
    （既有 L320）两处硬编码 `RUN_CREATE_ENDPOINT` 必须同步改为使用该参数**——
    否则重跑幂等记录落入 CREATE 作用域，同 session 同键的普通创建与重跑互相误判
    IDEMPOTENCY_KEY_REUSED，且竞争走 IntegrityError 时 RERUN 作用域查无记录会 re-raise；
    普通创建不传（行为不变，AC 兼容），重跑传 `RUN_RERUN_ENDPOINT` 与 `rerun_of_run_id=run_id`。
- **状态码与错误**：202（受理）/ 404 `RUN_NOT_FOUND` / 409 `RUN_NOT_TERMINAL` /
  409 `SESSION_ARCHIVED` / 409 `RUN_INPUT_MESSAGE_INVALID` / 409 `IDEMPOTENCY_KEY_REUSED`；
  错误码表 `routes.py` 的 `APPLICATION_ERROR_STATUS` 新增 `"RUN_NOT_TERMINAL": 409` 一行。

### 2.2 数据模型与迁移

- **`DiagnosisRunRecord`** 新增 `rerun_of_run_id: Mapped[UUID | None]`
  （Uuid 列，自引用外键 `ForeignKey("diagnosis_runs.id", ondelete="RESTRICT")`，NULL 兼容历史 Run）。
  - 自引用 FK 理由：来源关系在领域层是硬约束（重跑必须指向真实存在的原 Run），
    与既有全部 FK 的 `RESTRICT` 风格一致；不建新表（PRD 不要求重跑历史独立建模）。
  - 索引：`Index("ix_diagnosis_runs_rerun_of_id", "rerun_of_run_id")`——
    供「原 Run 被哪些 Run 重跑」的前端推导加速（低频查询，成本极低）。
- **迁移**：`backend/migrations/versions/20260812_12_p8_run_rerun.py`：
  - upgrade：`op.add_column`（PostgreSQL）/ `batch_alter_table`（SQLite，加 FK 必须重建表，
    对齐 `20260811_11` 先例）+ 自引用 FK + 索引；
  - downgrade：存在 `rerun_of_run_id` 非 NULL 历史行时**拒绝回滚**
    （对齐 service_registration 迁移的防御式 downgrade 先例），否则删索引/FK/列。
- **领域记录与 mapper**：`DiagnosisRunData` 加 `rerun_of_run_id: UUID | None = None`；
  `SqlAlchemyDiagnosisRunRepository.add` / `_diagnosis_run_data` mapper 同步字段；
  `list_by_session` / `list_page`（#64）select 列补 `rerun_of_run_id`；
  全局列表的 `GlobalRunData`（domain/records.py）与 `_global_run_data` mapper
  （repositories.py）同步加字段。
- 历史 Run（NULL）按普通 Run 处理（AC9），`DiagnosisRunResource` 校验器不受影响
  （新字段可选，终态校验语义不变）。

### 2.3 接口契约

| 方法 | 路径 | 说明 | 状态码 |
|---|---|---|---|
| POST | `/runs/{run_id}/rerun` | 对已结束 Run 发起重跑（Idempotency-Key 必填），返回新 Run | 202 / 404 / 409 |

- `DiagnosisRunResource` 兼容扩展 `rerun_of_run_id: UUID | None`（会话 Run 列表 /
  Run 详情共享同一资源）。
- `GlobalRunSummaryResource` 兼容扩展 `rerun_of_run_id: UUID | None`（#64 全局列表，
  `list_page` select 补一列，零额外查询）。
- **不做**原 Run 反查字段（`rerun_by_run_id`）与反查端点：原 Run 的「已被重跑」
  由前端在会话时间线推导（见 2.4），避免列表 N+1 与新增端点。
- 生成契约：`frontend/src/api/v1/generated.ts` 经 `npm run generate:api` 重新生成，禁止手编。

### 2.4 关联展示（前端）

- **会话时间线（原 Run 的「已被重跑」）**：`project_conversation_turns` 已接收
  会话的 runs 数据（`useInfiniteQuery` 按需加载、按 `created_at` 倒序——原 Run 已加载时，
  其重跑 Run 的 `created_at` 必然更晚、必在已加载前缀内，推导前提成立）。新增投影逻辑：
  由所有 investigation 的 `rerun_of_run_id` 构建「原 Run → 最新重跑 Run」映射
  （纯前端推导，零后端反查、零 N+1）；`ConversationInvestigation` 增加 `rerun_of_run_id`
  字段（资源直接读）。时间线上：
  - 新 Run（`rerun_of_run_id` 有值）：显示「重跑自 Run X」标记（X 为原 run_id 短形式）；
  - 原 Run（映射命中）：显示「已被重跑为 Run Y」标记。
- **全局 Run 列表（AC6）**：`RunsPage` 行内当 `rerun_of_run_id` 有值时显示
  「重跑」来源标记（短 run_id）。全局列表为跨会话分页，**不做**「原 Run 被重跑」
  的跨页推导（诚实：只展示当前页可见的来源关系；原 Run 侧标记在会话时间线表达）。
- **重跑入口（AC8）**：终态 Run（succeeded / failed / cancelled）的答复区
  （`AssistantReply` 三个终态分支底部）新增 `RerunButton` 组件：
  - 点击 → `rerun_run(run_id, { idempotency_key: crypto.randomUUID() })`
    （**每次点击生成新键**：重跑语义是「新的一次重跑」，复用旧键会命中 24h 内幂等记录
    重放第一次重跑；同键保护的是「同一重跑请求的重复提交」——按钮 loading 同步阻断双击）；
  - loading 态「正在重新生成…」防重复点击；失败如实展示错误（复用 `safe_error`）；
  - 成功 → invalidate `session_runs` / `session_messages` 查询
    （新 Run + 新 user message 自动投影进时间线，进入新 Run 跟踪）。
- **接线**：`client.ts` 加 `rerun_run` 方法与类型；`queries.ts` 加 `rerun_run_mutation`；
  `conversation-turns.ts` / `RunsPage.tsx` / `WorkbenchPage.tsx` 如上。

### 2.5 安全与脱敏

- **写操作纪律**：重跑是创建操作（写），但**不新增任何执行能力**——新 Run 走既有
  受理 → 后台执行链路，模型/Agent 权限边界不变；不触碰工具网关、审批/执行白名单。
- **脱敏**：响应复用既有 `RunResponse` 收敛（result/error 既有白名单，`_safe_run_error`
  不变）；新字段仅 run_id 引用，不含证据原文、工具输出、CoT/Prompt、凭据/DSN/`sk-`（AC7）。
  query 复用原 Run 的 input message，不进入任何响应字段（既有契约）。
- **参数校验**：`run_id` 路由级 UUID 校验（422 自动）；`Idempotency-Key` 复用
  `parse_idempotency_key`（非法 422）。
- **诚实降级**：重跑失败 → 明确错误，原 Run 与已记录关联不受影响；原 Run 不存在 /
  会话归档 / 未终态 → 明确 404/409；前端按钮失败如实提示，不伪造成功。

## 3. 文件改动面

### 后端（修改 + 新增）

- `backend/migrations/versions/20260812_12_p8_run_rerun.py`（**新增迁移**）：
  `diagnosis_runs` 加 `rerun_of_run_id` 自引用列 + 索引；downgrade 防御检查。
- `backend/src/infrastructure/persistence/models.py`（修改）：`DiagnosisRunRecord` 加列。
- `backend/src/domain/records.py`（修改）：`DiagnosisRunData` 加 `rerun_of_run_id`。
- `backend/src/infrastructure/persistence/repositories.py`（修改）：
  `add` / `_diagnosis_run_data` mapper / `list_by_session` / `list_page` 同步字段。
- `backend/src/application/services.py`（修改）：`rerun_run` +
  `_rerun_fingerprint` + `_accept_run_in_transaction` 可选参数（`rerun_of_run_id` + `endpoint`，
  幂等检查/写入两处同用）+ `_load_idempotency_after_conflict` endpoint 参数化 +
  `RUN_RERUN_ENDPOINT` 常量。
- `backend/src/application/errors.py`（修改）：新增 `RunNotTerminalError`。
- `backend/src/api/v1/routes.py`（修改）：`APPLICATION_ERROR_STATUS` 加
  `RUN_NOT_TERMINAL: 409`；新增 `POST /runs/{run_id}/rerun`。
- `backend/src/api/v1/schemas.py`（修改）：`DiagnosisRunResource` / `GlobalRunSummaryResource`
  加 `rerun_of_run_id`。
- `backend/src/api/v1/resources.py`（修改）：`run_resource` / `global_run_summary_resource` 透传字段。
- 后端测试（新增）：`test_run_rerun.py`（AC1–AC5 服务端面 / AC7 / AC9 + 归档 / 指纹冲突）；
  回归：`test_api.py` / `test_p2_application_services.py` / `test_p5_controlled_action.py`。

### 前端（修改）

- `frontend/src/api/v1/generated.ts`（重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`（修改）：`rerun_run` 方法 + 类型导出。
- `frontend/src/api/v1/queries.ts`（修改）：`rerun_run_mutation`。
- `frontend/src/features/workbench/conversation-turns.ts`（修改）：
  `rerun_of_run_id` 字段 + 原 Run「已被重跑」前端推导映射。
- `frontend/src/features/workbench/WorkbenchPage.tsx`（修改）：`RerunButton` 组件 +
  三个终态分支接入。
- `frontend/src/features/runs/RunsPage.tsx`（修改）：行内「重跑自」来源标记。
- 前端测试：`RerunButton` 交互（点击/loading/失败/成功进入新 Run）、投影推导
  （重跑自/已被重跑标记）、RunsPage 来源标记；`frontend/src/test/handlers.ts` 补
  `/runs/{id}/rerun` handler 与 `rerun_of_run_id` fixtures。

### 文档

- `docs/接口清单.md`（修改）：缺表「重跑 / 重新生成」标记已交付，补
  `POST /runs/{id}/rerun` 行与 `rerun_of_run_id` 字段说明。
- `docs/路线图.md`（修改）：当前阶段登记本工作包（issue #65，进行中）。

### 明确无改动

- 无新表、无新流程、无新 Connector / 凭据 / 权限 / 审批 / 执行能力；
  既有 `POST /sessions/{id}/runs` 创建行为不变；SSE / Run 执行链路 / 工具网关不动；
  `data/`、`demo/`、`docs/完善清单.md` 不动（重跑不在完善清单欠账表）。

## 4. 切片与验证（指引，不写死）

建议拆 **2 片**（后端含迁移 1 片 + 前端 1 片，PRD 三个功能需求在切片内闭环）：

- **S1：重跑后端链路**。迁移 + 模型/记录/repository 字段 + `rerun_run` 应用服务 +
  `POST /runs/{run_id}/rerun` 路由/资源/错误码 + 后端测试。
  验收语义：AC1（终态可重跑、来源关联记录）、AC2（未终态明确错误）、AC3（query/service 复用）、
  AC4（幂等重放与指纹冲突）、AC7（响应无未脱敏内容）、AC9（历史 Run 兼容）；
  迁移 `upgrade` 可执行、既有测试全绿。
- **S2：前端重跑入口与关联展示**。generated 契约 + client/queries 接线 +
  `RerunButton`（三个终态分支）+ 时间线投影（重跑自/已被重跑）+ RunsPage 来源标记 + 前端测试。
  验收语义：AC8（按钮/loading/进入新 Run）、AC5（双向关联展示）、AC6（全局列表来源标记）、
  AC10（前端回归）；`npm run generate:api` 后 typecheck/test/build 通过。

涉及门禁项：**新增公开 API**（`POST /runs/{run_id}/rerun`）+ **数据库迁移**
（`diagnosis_runs.rerun_of_run_id`）⇒ 本 Design 经 arch-review PASS + 用户确认后方可开发；
无 Connector、无凭据、无权限/审批/执行能力扩大。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| SQLite 加自引用 FK 列需重建表 | `batch_alter_table`（对齐 `20260811_11` 先例），迁移前后既有测试全绿验证 |
| 相同 query+service 的原 Run 用同键重跑 → 错误重放 | `_rerun_fingerprint` 包含 `run_id`，指纹不同即 409 `IDEMPOTENCY_KEY_REUSED` |
| 前端重跑成功后时间线出现两条相同问题消息 | 如实展示（重跑语义即「新 user message + 新 Run」），符合 PRD「重跑复用原问题的 query」 |
| 双击 / 并发重跑 | 按钮 loading 同步阻断 + 每次点击新幂等键（同键重放兜底） |
| 前端推导「已被重跑」在全局列表跨页失效 | 只在会话时间线推导（全量已加载）；全局列表只显示「重跑自」来源标记，不做跨页猜测 |
| 重跑受理竞争中原 Run 状态变化 | 单事务校验 + 幂等重读路径复用（`_load_idempotency_after_conflict`） |
| 生成契约与后端漂移 | `npm run generate:api` 重新生成，禁止手编 |
| 迁移回滚破坏 | downgrade 防御检查：存在 rerun 历史行拒绝回滚（对齐 service_registration 先例） |

- 回滚：`alembic downgrade`（防御检查通过时）移除来源列；移除 `POST /runs/{run_id}/rerun`
  路由与前端按钮/标记即回退；无配置项、无 Connector。
- 门禁项清单：新增公开 API（`POST /runs/{run_id}/rerun`）+ 数据库迁移
  （`diagnosis_runs.rerun_of_run_id`）⇒ Design → Review → 用户确认；
  未新增凭据/权限/审批执行能力。

## 6. 待用户确认的设计决策

1. **重跑端点形态**：`POST /runs/{run_id}/rerun` + 复用 `Idempotency-Key` 头
   （独立幂等作用域 `RUN_RERUN_ENDPOINT`，指纹含 run_id 防误用）——是否确认？
   （PRD 开放问题 1/3 推荐方案）
2. **来源字段命名**：`rerun_of_run_id`（新 Run 指向原 Run，NULL 兼容历史 Run）——
   是否确认？（PRD 开放问题 2 推荐方案）
3. **原 Run「已被重跑」的展示方式**：不做后端反查字段/端点（`rerun_by_run_id` /
   `GET /runs/{id}/reruns`），由前端会话时间线**纯前端推导**（全量 runs 已加载，
   构建「原 Run → 最新重跑」映射）；全局列表只显示新 Run 的「重跑自」来源标记——
   是否确认？（零 N+1、零新增端点；AC5/AC6 由展示层满足）
4. **原 Run 可被多次重跑**：不限制次数（幂等键只防同一请求的重复提交，不同键的
   多次重跑各自产生新 Run；PRD「不做并发重跑限制的额外策略」）——是否确认？
5. **归档会话的重跑**：复用普通创建的 `SESSION_ARCHIVED`（409 明确拒绝，
   归档会话只读）——是否确认？（PRD 边界「原 Run 已归档/删除 → 明确错误」的落法）
