# P8 消息编辑与删除——会话消息更正 Design

> 状态：已确认（arch-review PASS，用户确认 6 项设计决策）
> 更新：2026-08-14
> 关联：`docs/prd/session/P8-message-edit-delete.md`（已确认，issue #75）、
> `docs/产品定义.md`（§2.1 会话主入口）、`docs/开发规范.md`（§2/§4/§6）、
> `docs/架构与开发路径.md`（一条主脊、Trace 安全投影、历史留痕）、
> `docs/接口清单.md`（第一大模块：消息编辑/删除欠账）、
> `backend/src/domain/records.py`、`backend/src/domain/repositories.py`、
> `backend/src/infrastructure/persistence/models.py`、`backend/src/infrastructure/persistence/repositories.py`、
> `backend/src/application/plain_messages.py`、`backend/src/api/v1/routes.py`、`backend/src/api/v1/schemas.py`、
> `backend/src/api/v1/resources.py`、`backend/src/api/v1/dependencies.py`、
> `frontend/src/features/workbench/WorkbenchPage.tsx`、`frontend/src/features/workbench/conversation-turns.ts`、
> `frontend/src/api/v1/client.ts`、`frontend/src/api/v1/queries.ts`。

## 1. 目标与范围

### 一句话目标

用户能编辑 / 删除自己在会话里发出的普通消息（user 角色），更正打错的内容、清理错发消息，
编辑如实标注「已编辑」，删除不影响 Run、结果与历史留痕——让「会话即主入口」的消息更正闭环成立。

### 做什么（对齐 PRD）

1. **编辑消息**：新增 `PATCH /sessions/{id}/messages/{message_id}`，仅 `user` 角色；更新内容并记录
   `edited_at`；时间线位置不变。
2. **删除消息**：新增 `DELETE /sessions/{id}/messages/{message_id}`，仅 `user` 角色；软删除
   （`archived_at`），会话消息列表不再展示；重复删除幂等 204。
3. **已编辑标注**：`MessageResource` 新增可空 `edited_at`；既有 `GET/POST` 消息契约不变（列表返回
   `edited_at`）；前端如实展示「（已编辑）」。
4. **前端适配**：user 消息气泡提供编辑（编辑态 → 保存 → 替换展示）与删除（确认 → 移除）操作；
   删除带调查回复的消息时如实提示「该问题已有调查回答，删除问题不删除回答记录」；
   被删输入消息的 Run 调查卡片保留，输入位置显示「（问题已删除）」占位。
5. **数据库迁移**：`messages` 表新增可空 `edited_at`、`archived_at` 两列（迁移显式执行）。

### 明确不做（对齐 PRD「不做什么」）

- 不编辑 / 删除 `assistant`（AI 回答）与 `system` 消息；只允许 user 消息编辑/删除。
- 不删除 Run、结果、证据、提案、审批与留痕；不删除 `DiagnosisRunData.input_message_id` 关联关系。
- 不做「编辑后自动重跑」：编辑已产生 Run 的输入消息不触发重新调查（重跑是 `POST /runs/{id}/rerun`
  的语义，见 `P8-rerun-investigation.md`）。
- 不新增审批 / 权限模型（无登录体系，`docs/产品定义.md` §7 未决）。
- 不暴露证据原文、工具输出、CoT/Prompt 或凭据；编辑/删除接口不触碰 Run 结果与证据。
- 不做消息历史版本表（编辑覆盖原内容，仅保留 `edited_at` 时间戳标注；PRD 未要求版本历史）。
- 不新增 Tool / Connector / Agent / 配置项 / 服务类型——纯会话资源点操作，不触碰工具网关与外部访问。

### 与「一条主脊，能力即插件」硬规则的关系（显式声明）

本 Design 新增 2 个公开端点与 1 个数据库迁移，这是补齐 `docs/接口清单.md` 已登记欠账的
**主入口体验接线**，不是新能力插件：编辑/删除只作用于会话消息表（用户自己的文本），
不触碰工具网关、凭据、审批/执行白名单、Run 执行链与证据链；调查仍 100% 走既有 Run 主脊。
若确认，需同步把该工作包登记到 `docs/路线图.md` 当前阶段。

## 2. 设计决策

### 2.1 领域层：消息模型与 Repository 端口扩展

- `MessageData`（`backend/src/domain/records.py`）新增两个可空字段，复用 `TimestampedRecord`
  的 UTC aware 校验（`*_at` 自动覆盖）：
  - `edited_at: datetime | None = None`——首次编辑时间，编辑后非空。
  - `archived_at: datetime | None = None`——软删除标记，删除后非空。
- `MessageRepository` 端口（`backend/src/domain/repositories.py`）新增两个方法：
  - `update_content(message_id: UUID, content: str, edited_at: datetime) -> MessageData | None`——
    仅更新内容与编辑时间（不动 `created_at`，时间线位置不变）；返回更新后的消息，未找到返回 None。
  - `archive(message_id: UUID, archived_at: datetime) -> bool`——软删除标记；
    返回是否真的执行了标记（已删除/不存在返回 False，供幂等语义区分）。
  - `list_by_session` 增加**默认过滤已删除消息**（`archived_at IS NULL`）：删除后消息不再出现在
    `GET /sessions/{id}/messages`（AC5）；游标分页语义不变（过滤条件与 `(created_at, id)` 排序兼容）。
- 实现（`backend/src/infrastructure/persistence/repositories.py` 的 `SqlAlchemyMessageRepository`）：
  - `update_content` / `archive` 用 `update(MessageRecord)` 条件更新（`WHERE id = ? AND archived_at IS NULL`），
    单语句点操作，符合 PRD「不引入额外查询放大」；`update_content` 更新后回读返回完整对象。
  - `list_by_session` 的 statement 增加 `MessageRecord.archived_at.is_(None)` 过滤。

### 2.2 应用层：消息编辑用例服务（独立模块）

- 新增 `backend/src/application/message_editing.py`（镜像 `plain_messages.py` 的模块风格）：
  - `EditMessageCommand(content: str)`（1..4000，strip 归一化，与创建消息同约束）。
  - `MessageEditingApplicationService`，构造注入 `SessionFactory`（与既有服务一致，短事务内操作）：
    - `edit_message(session_id, message_id, command) -> MessageData`：
      1. 短事务内读消息：不存在 / 不属于该会话 / 已删除 → `MessageNotFoundError`（404）。
      2. 角色非 `user` → `MessageNotEditableError`（422，AC2）。
      3. `update_content(content, now)` 并提交，返回更新后消息（AC1）。
    - `archive_message(session_id, message_id) -> None`：
      1. 短事务内读消息：不存在 / 不属于该会话 → `MessageNotFoundError`（404）。
      2. 角色非 `user` → `MessageNotDeletableError`（422，AC6）。
      3. 已删除（`archived_at` 非空）→ 幂等直接返回（204，AC8，对齐既有
         `DELETE /sessions/{id}` 幂等语义）。
      4. `archive(now)`；**同事务**按 §2.5 配对规则软删除紧随的普通回复（若有）。
  - 错误类新增到 `backend/src/application/errors.py`：
    `MessageNotFoundError`（404 `MESSAGE_NOT_FOUND`）、`MessageNotEditableError`
    （422 `MESSAGE_NOT_EDITABLE`）、`MessageNotDeletableError`（422 `MESSAGE_NOT_DELETABLE`）。
    归属校验（会话归属、角色、已删除）全部在应用层完成——PRD 降级策略「无身份模型下为资源归属校验」。
- 装配：`V1Services`（`backend/src/api/v1/dependencies.py`）新增
  `message_editing_service: MessageEditingApplicationService | None = None` 字段，
  `build_v1_services_for_runtime` 显式装配（与 `plain_message_service` 同层），不新增全局单例。

### 2.3 API 层：PATCH / DELETE 路由与错误语义

- `PATCH /sessions/{session_id}/messages/{message_id}`（`routes.py`）：
  - 请求体 `EditMessageRequest {content: str}`（1..4000，strip 归一化）；
    空内容 / 超长由 Pydantic 约束返回 422（AC4，与既有 `POST /runs` query 校验行为一致）。
  - 先 `_load_session` 校验会话存在（404），再调 `edit_message`。
  - 成功 200，返回 `MessageResponse {message: MessageResource, meta}`（含 `edited_at`）。
  - 错误：`SESSION_NOT_FOUND` / `MESSAGE_NOT_FOUND` → 404；`MESSAGE_NOT_EDITABLE` → 422。
- `DELETE /sessions/{session_id}/messages/{message_id}`（`routes.py`）：
  - 先 `_load_session` 校验会话存在，再调 `archive_message`。
  - 成功 / 幂等重复删除 204（沿用既有 204 模式，`X-Request-Id` 头）。
  - 错误：404 / `MESSAGE_NOT_DELETABLE` → 422。
- `MessageResource`（`backend/src/api/v1/schemas.py`）新增 `edited_at: datetime | None = None`；
  `message_resource`（`resources.py`）透传；历史消息无 `edited_at` 正常返回（可空，兼容性满足）。
- OpenAPI 变更 → `frontend/src/api/v1/generated.ts` 由 `npm run generate:api` 重新生成（禁止手编）。

### 2.4 数据层：迁移

- `MessageRecord`（`backend/src/infrastructure/persistence/models.py`）新增两列：
  - `edited_at: Mapped[datetime | None]`、`archived_at: Mapped[datetime | None]`（均可空，`DateTime(timezone=True)`）。
- 新增迁移 `backend/migrations/versions/20260814_13_p8_message_edit_delete.py`：
  - `upgrade`：`op.add_column` × 2（可空，无数据回填）。
  - `downgrade`：`op.drop_column` × 2。
  - 迁移显式执行（`alembic upgrade head`），不随后端启动自动迁移。

### 2.5 删除的成对可见性处理（PRD 开放问题 3）

- **规则**：仅 `user` 消息可删；`assistant` / `system` 消息不可单独删除。
- **普通回复随删**：删除 user 消息时，在**同一短事务**内软删除「与该 user 消息成对的普通回复」——
  即该 user 消息之后、**下一条 user 消息之前**、`role=assistant AND run_id IS NULL` 的首条消息
  （普通消息通道写入时保证 assistant 时间戳严格晚于其 user，`plain_messages.py` 既有约束）。
  规则按 `(created_at, id)` 顺序扫描会话消息确定，确定性、无歧义；找不到配对（无回复）则不删任何
  assistant 消息。Run 关联的 assistant 输出（`run_id` 非空）绝不删除。
- **Run 调查卡片保留**：删除与 Run 关联的输入消息时，Run、结果、事件、提案、审批全部不动
  （AC7）；消息列表不再出现该消息；前端时间线仍展示该 Run 调查卡片，输入位置显示
  「（问题已删除）」占位——「删除问题不删除回答记录」如实落地。

### 2.6 前端

- **API 客户端**（`frontend/src/api/v1/client.ts`）：`request_json` 的 method union 增加 `'PATCH'`
  （当前只允许 GET/POST/PUT/DELETE，是硬性前置改动）；新增
  `patch_session_message(session_id, message_id, content)` 与
  `delete_session_message(session_id, message_id)` 方法。
- **查询层**（`frontend/src/api/v1/queries.ts`）：新增 `update_message_mutation` /
  `delete_message_mutation`（沿用 `send_plain_message_mutation` 的 hook 模式）；
  成功后 `invalidateQueries` 会话消息查询（复用 `invalidate_session_queries` 的既有刷新路径）。
- **投影层**（`frontend/src/features/workbench/conversation-turns.ts`）：
  - `ConversationMessage` 增加 `edited_at?: string`（读取 `resource_optional_string`）。
  - **语义变更**：`RUN_INPUT_MESSAGE_MISSING` 不再整条丢弃调查卡片——输入消息缺失（已删除）时
    该 investigation 保留展示（占位输入），issue 记录仍写入（不伪造缺失原因）。
    类型上 `ConversationTurn.input` 允许缺失（`input: ConversationMessage | null`）。
  - 普通回复配对逻辑不变（后端已按 §2.5 随删，刷新后列表即一致）。
- **工作台 UI**（`frontend/src/features/workbench/WorkbenchPage.tsx`）：
  - `ConversationTurnCard` 的 user 气泡增加操作区（编辑 / 删除），仅 `user` 角色消息显示；
    `system` / `assistant` 消息不显示操作。
  - 编辑态：气泡切换为输入框（复用 Composer 的输入原语）+ 保存 / 取消；保存调
    `update_message_mutation`，成功后刷新列表；`edited_at` 存在时气泡展示「（已编辑）」。
  - 删除：确认交互（复用既有 UI 原语）；该消息关联 Run（`turn.investigations.length > 0`）时
    提示「该问题已有调查回答，删除问题不删除回答记录」；确认后调 `delete_message_mutation`，
    成功后刷新列表，Run 卡片保留、输入占位「（问题已删除）」。
  - 失败态诚实展示：编辑/删除请求失败沿用 `safe_error` 的错误提示路径，不本地伪造成功。
- **测试**：
  - 交互测试：`frontend/src/test/handlers.ts` 增加 PATCH/DELETE handler；
    新增/扩展工作台交互测试（编辑保存后出现「已编辑」、删除后消息消失且 Run 卡片保留、
    失败态诚实展示），沿用 `App.test.tsx` 的 `conversation_resources` + MSW 模式。
  - 投影测试：`conversation-turns.test.ts` 增加 edited_at 读取与输入缺失保留卡片的用例。

### 2.7 安全与诚实（横切边界核对）

- **只读默认**：编辑/删除只写 `messages` 表两列，不触碰 Run、结果、证据、提案、审批、凭据。
- **内容即用户文本**：`content` 是用户自己的消息文本，不涉及脱敏边界；响应不含证据原文/
  工具输出/CoT/凭据（DoD）。
- **诚实留痕**：编辑标注 `edited_at`；删除软删除（历史可审计）；Run 详情仍可追溯；
  「编辑仅改展示，不重放上下文」——不伪造重跑关系、不伪造时间线顺序（`created_at` 不动）。
- **编辑对调查上下文的影响**（PRD 开放问题 4）：编辑已产生 Run 的输入消息 → 仅更新消息文本与
  `edited_at`；不重跑、不重放上下文；已执行 Run 不受影响（`_claim_run` 已在执行时读取 query）；
  后续新 Run 使用编辑后文本。Run 追溯时输入显示编辑后文本 + 「（已编辑）」标记——显式、不伪造。
- **并发与幂等**：`update_content` / `archive` 条件更新（`archived_at IS NULL` 守卫），
  重复删除幂等 204；已删除消息 PATCH → 404（与「不存在」同语义，避免编辑不可见资源）。

## 3. 文件改动面（真实路径）

后端（新增 2 文件，修改 8 文件）：
- `backend/src/domain/records.py`（修改）：`MessageData` 加 `edited_at` / `archived_at`。
- `backend/src/domain/repositories.py`（修改）：`MessageRepository` 端口加 `update_content` / `archive`。
- `backend/src/infrastructure/persistence/models.py`（修改）：`MessageRecord` 加两列。
- `backend/src/infrastructure/persistence/repositories.py`（修改）：实现两个新方法；
  `list_by_session` 过滤已删除。
- `backend/src/application/errors.py`（修改）：新增 3 个错误类。
- `backend/src/application/message_editing.py`（新增）：`MessageEditingApplicationService` 与命令。
- `backend/src/api/v1/dependencies.py`（修改）：`V1Services` 装配新服务。
- `backend/src/api/v1/schemas.py`（修改）：`MessageResource.edited_at`、`EditMessageRequest`、`MessageResponse`。
- `backend/src/api/v1/resources.py`（修改）：`message_resource` 透传 `edited_at`。
- `backend/src/api/v1/routes.py`（修改）：PATCH / DELETE 两个路由。
- `backend/migrations/versions/20260814_13_p8_message_edit_delete.py`（新增）：两列迁移。
- `backend/tests/test_message_edit_delete_api.py`（新增）：AC1–AC8 API 测试。
- `backend/tests/test_p2_repositories.py`（修改）：repository 层新方法/过滤测试。

前端（修改 7 文件）：
- `frontend/src/api/v1/client.ts`（修改）：method union 加 `'PATCH'`；新增两个方法。
- `frontend/src/api/v1/queries.ts`（修改）：新增两个 mutation hooks。
- `frontend/src/api/v1/generated.ts`（重新生成，禁止手编）：`MessageResource.edited_at` 等。
- `frontend/src/features/workbench/conversation-turns.ts`（修改）：`edited_at`、输入缺失保留卡片。
- `frontend/src/features/workbench/WorkbenchPage.tsx`（修改）：编辑/删除交互、已编辑标注、占位。
- `frontend/src/features/workbench/conversation-turns.test.ts`（修改）：投影新语义测试。
- `frontend/src/test/handlers.ts`（修改）+ 工作台交互测试文件（新增或扩展 `App.test.tsx` 模式）。

文档：
- `docs/design/session/P8消息编辑与删除Design.md`（本文件，随功能分支入库）。
- `docs/workpack/P8-message-edit-delete/{plan,evidence,review}.md`（dev-plan / dev-execute 产出）。
- `docs/接口清单.md`（修改）：消息编辑/删除欠账 → 已交付（随功能分支或收尾 PR 更新）。

无功能改动部分：纯后端接口点操作 + 纯前端展示，不涉及 Trace/SSE/监控/审批链路。

## 4. 切片与验证（指引，不写死）

建议拆 3 片，每片独立可验收：
- S1：后端领域 + 数据 + 迁移 + PATCH/DELETE 路由与错误语义（AC1–AC8）。
- S2：前端 client/queries/generated 重新生成 + 投影层语义（AC9 的前端基础）。
- S3：前端编辑/删除交互闭环 + 已编辑标注 + 占位展示 + 交互测试（AC9），回归（AC10）。

验证方法归 dev-plan 的 plan.md；涉及门禁项：**公开 API（2 个端点）+ 数据库迁移（2 列）**
——必须经本 Design arch-review PASS + 用户确认后才可开发。

## 5. 风险、回滚与门禁

| 风险 | 缓解 |
|---|---|
| 投影语义变更（`RUN_INPUT_MESSAGE_MISSING` 从丢弃改保留）影响既有分页边界展示 | 投影测试锁定：缺失输入消息时卡片保留 + 占位，issue 记录仍在 |
| 普通回复配对规则边界（多轮/调查穿插）误删 | 规则限定「下一条 user 消息之前」范围，应用层顺序扫描确定；API 测试覆盖多轮与穿插场景 |
| `generated.ts` 重新生成需要后端 OpenAPI | plan 内安排：迁移 + 启动 uvicorn 8000 → `npm run generate:api` → 提交生成物 |
| 游标分页与过滤条件叠加（SQLite/PostgreSQL 一致性） | `list_by_session` 过滤在语句层实现，repository 测试覆盖分页 + 删除混合场景 |
| 重复删除与已删除 PATCH 语义歧义 | 应用层统一：已删除 PATCH → 404；重复 DELETE → 幂等 204（决策 5） |

- 回滚：接口回滚即移除两个路由与 `message_editing_service` 装配；数据回滚执行 `alembic downgrade`
  （两列 drop，数据无破坏）。
- 门禁项清单：公开 API（PATCH/DELETE messages）、数据库迁移（2 列）——均已列入 §6 决策，arch-review
  PASS + 用户确认后放行。

## 6. 待用户确认的设计决策

1. **删除实现**：软删除（`archived_at`，列表过滤，历史可审计），而非物理删除。（推荐）
2. **删除范围**：允许删除已有 Run 关联的 user 消息——仅从消息列表移除，Run/结果/留痕保留，
   Run 调查卡片继续展示、输入位置显示「（问题已删除）」占位。（推荐）
3. **assistant 消息**：仅 user 消息可删/可编辑；删除 user 消息时同事务软删「紧随其后、下一条
   user 消息之前」的无 Run 普通回复（成对不再展示）；Run 关联的 assistant 输出绝不删除。（推荐）
4. **编辑对调查上下文的影响**：编辑仅改展示与后续新 Run 的输入文本；不重跑、不重放上下文；
   已产生 Run 的输入消息编辑后，其 Run 追溯显示编辑后文本 + 「（已编辑）」标记，不保留原文本。
   （推荐）
5. **幂等与已删除语义**：重复删除 → 幂等 204（对齐 `DELETE /sessions/{id}`）；PATCH 已删除消息
   → 404（与「不存在」同语义）。（推荐）
6. **不做消息历史版本表**：编辑覆盖原内容，仅保留 `edited_at` 时间戳标注（PRD 未要求版本历史）。
   （推荐）
