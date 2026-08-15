# P8-message-edit-delete · 工作包计划

> PRD：`docs/prd/session/P8-message-edit-delete.md`（已确认，issue #75）
> Design：`docs/design/session/P8消息编辑与删除Design.md`（已确认，arch-review PASS + 用户确认 6 项决策）
> 基线：`backend/src/domain/records.py`、`backend/src/domain/repositories.py`、
> `backend/src/infrastructure/persistence/{models,repositories}.py`、`backend/src/application/plain_messages.py`、
> `frontend/src/features/workbench/{WorkbenchPage.tsx,conversation-turns.ts}`、`frontend/src/api/v1/{client,queries}.ts`
> 专用分支：`feat/P8-message-edit-delete`（基线 `origin/main` 8a644f3）
> worktree：`D:/market-handsome/oper-mind-worktrees/P8-message-edit-delete`

## 范围

### 只做

- S1（AC1–AC8，后端）：领域层 `MessageData` 增 `edited_at`/`archived_at`；`MessageRepository` 端口增
  `update_content`/`archive`；`SqlAlchemyMessageRepository` 实现 + `list_by_session` 过滤已删除；
  迁移新增两列（upgrade/downgrade）；`MessageEditingApplicationService`（编辑/删除用例，含成对普通
  回复随删）；`V1Services` 装配；`PATCH`/`DELETE /sessions/{id}/messages/{message_id}` 路由与
  404/422 错误语义；`MessageResource.edited_at`；后端 API 测试 + repository 测试 +
  删除输入消息后 `_claim_run`/重跑仍可读的回归测试（arch-review P2 落地）。
- S2（AC9 前端基础）：`client.ts` method union 加 `'PATCH'` + 两个新方法；`queries.ts` 两个 mutation
  hooks；`generated.ts` 重新生成（禁手编）；`conversation-turns.ts` 读 `edited_at`、输入缺失的 Run
  卡片保留（含 adjacent-dedup 对 null input 的 `?.` 守卫，arch-review P2 落地）；投影测试。
- S3（AC9 前端交互闭环）：`WorkbenchPage.tsx` user 气泡编辑/删除操作、编辑态、已编辑标注、
  删除确认与「该问题已有调查回答，删除问题不删除回答记录」提示、Run 卡片输入占位
  「（问题已删除）」；MSW handlers 增 PATCH/DELETE；交互测试；AC10 全量回归。

### 明确不做

- 不编辑/删除 assistant/system 消息；不删除 Run/结果/证据/提案/审批与留痕。
- 不自动重跑；不做消息历史版本表；不新增审批/权限模型。
- 不新增 Tool/Connector/Agent/配置项/服务类型；不动 Trace/SSE/监控/审批链路。
- 不暴露证据原文/工具输出/CoT/Prompt/凭据。

## 切片拆分（3 个独立可验收切片）

- [ ] S1: 后端编辑/删除接口 + 软删除迁移 + 错误语义 → AC1–AC8
- [ ] S2: 前端 API 客户端 + 投影层适配（edited_at / 缺失输入保留卡片）→ AC9 前置
- [ ] S3: 前端编辑/删除交互闭环 + 已编辑标注 + 占位展示 + 交互测试 → AC9、AC10

## 改动面（文件级）

后端（新增 2，修改 8）：
- `backend/src/domain/records.py`（修改）：`MessageData` 加 `edited_at`/`archived_at`。
- `backend/src/domain/repositories.py`（修改）：`MessageRepository` 加 `update_content`/`archive`。
- `backend/src/infrastructure/persistence/models.py`（修改）：`MessageRecord` 加两列。
- `backend/src/infrastructure/persistence/repositories.py`（修改）：实现两方法；`list_by_session` 过滤。
- `backend/src/application/errors.py`（修改）：`MessageNotFoundError`/`MessageNotEditableError`/`MessageNotDeletableError`。
- `backend/src/application/message_editing.py`（新增）：用例服务（编辑/删除 + 成对普通回复随删）。
- `backend/src/api/v1/dependencies.py`（修改）：`V1Services` 装配。
- `backend/src/api/v1/schemas.py`（修改）：`MessageResource.edited_at`/`EditMessageRequest`/`MessageResponse`。
- `backend/src/api/v1/resources.py`（修改）：`message_resource` 透传。
- `backend/src/api/v1/routes.py`（修改）：PATCH/DELETE 路由。
- `backend/migrations/versions/20260814_13_p8_message_edit_delete.py`（新增）：两列迁移。
- `backend/tests/test_message_edit_delete_api.py`（新增）：AC1–AC8。
- `backend/tests/test_p2_repositories.py`（修改）：新方法/过滤测试。
- `backend/tests/test_p2_application_services.py`（修改，如适用）：删除输入消息后 `_claim_run`/重跑仍可读。

前端（修改 6，生成 1）：
- `frontend/src/api/v1/client.ts`（修改）：method union 加 `'PATCH'`；`patch_session_message`/`delete_session_message`。
- `frontend/src/api/v1/queries.ts`（修改）：`update_message_mutation`/`delete_message_mutation`。
- `frontend/src/api/v1/generated.ts`（重新生成，禁手编）：`MessageResource.edited_at` 等。
- `frontend/src/features/workbench/conversation-turns.ts`（修改）：`edited_at`、缺失输入保留卡片、null 守卫。
- `frontend/src/features/workbench/WorkbenchPage.tsx`（修改）：编辑/删除交互、已编辑标注、占位。
- `frontend/src/features/workbench/conversation-turns.test.ts`（修改）：投影新语义。
- `frontend/src/test/handlers.ts`（修改）+ 交互测试文件（新增，沿用 App.test.tsx 模式）。

文档：
- `docs/design/session/P8消息编辑与删除Design.md`（新增，已确认）。
- `docs/workpack/P8-message-edit-delete/{plan,review,evidence}.md`（本文件 + 执行产出）。
- `docs/workpack/README.md`（修改）：活跃表登记。
- `docs/prd/session/P8-message-edit-delete.md`（修改，S1 前）：frontmatter `status: 进行中`（用户确认计划后）。
- `docs/prd/README.md` 与 `docs/prd/session/README.md`（修改）：PRD 状态索引同步「进行中」。
- `docs/接口清单.md`（修改，收尾）：消息编辑/删除欠账 → 已交付。
- `docs/路线图.md`（修改，收尾）：登记工作包完成。

## 验证方法

- 后端（worktree 内 `backend/`，Python 用仓库根 `.venv`）：
  - `..\.venv\Scripts\python.exe -m pytest tests/test_message_edit_delete_api.py -q`
  - 回归子集：`..\.venv\Scripts\python.exe -m pytest tests/test_plain_message_api.py tests/test_p2_repositories.py tests/test_p2_application_services.py tests/test_run_rerun.py tests/test_p2_recovery_closure.py -q`
  - 迁移验证：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`（临时库由测试 fixture 执行）；`downgrade` 验证在迁移测试中覆盖。
  - 全量：`..\.venv\Scripts\python.exe -m pytest tests -q`
- 前端（worktree 内 `frontend/`）：先 `npm install`；
  - `npm run typecheck`、`npm run test`、`npm run build`
  - `npm run generate:api` 需要后端在 8000 提供 OpenAPI：迁移 + `..\.venv\Scripts\python.exe -m uvicorn src.app:app --port 8000`（后台）→ 生成 → 核对 `generated.ts` diff 只含本工作包字段
- 门禁：`git diff --check`；确认无凭据/`sk-`/DSN/证据原文进入日志、Trace、响应、截图、文档

## 提交计划

- 按切片提交（每切片一个，外加 docs 前置提交）：
  1. `docs: P8 消息编辑与删除 Design 与工作包计划（issue #75）`（Design + plan + workpack README 登记 + PRD 状态进行中双写）
  2. `feat: P8 消息编辑删除后端——编辑/删除接口与软删除迁移（AC1-AC8）`
  3. `feat: P8 消息编辑删除前端基础——API 客户端与投影层适配（AC9 前置）`
  4. `feat: P8 消息编辑删除前端交互——编辑态/已编辑标注/删除确认（AC9）`
  5. `docs: P8 消息编辑删除收尾——接口清单与路线图登记（issue #75）`（随 PR 收尾）

## 状态

- [x] Design 已确认（arch-review PASS + 用户确认 6 项决策）
- [x] 专用 worktree 已建（分支 `feat/P8-message-edit-delete`，基线 `origin/main` 8a644f3）
- [ ] 计划待用户确认后进入 dev-execute
