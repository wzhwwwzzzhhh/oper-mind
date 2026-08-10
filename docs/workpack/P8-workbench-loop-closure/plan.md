# P8-workbench-loop-closure · 工作包计划

> 关联 PRD：`docs/prd/session/P8-workbench-loop-closure.md`（已确认，issue #54）
> 关联 Design：`docs/design/session/P8会话工作台闭环Design.md`（arch-review PASS + 用户确认，状态=已确认）
> 分支：`feat/p8-workbench-loop-closure`（worktree：`D:/market-handsome/oper-mind-worktrees/p8-workbench-loop-closure`，基线 `main` @ 88673f7）

## 范围

### 只做
- AC1/AC3：普通消息（如「谢谢」）走轻量回复，不创建 Run、不触发多 Agent 调查，回复明确说明「未启动调查」。
- AC2：调查意图消息（含调查关键词）走既有 `POST /sessions/{id}/runs` 主链路，行为不变。
- AC4/AC5/AC6：`POST /runs/{id}/cancel`——`queued`/`running` 可取消置 `cancelled` 并写 `run_cancelled` 事件、后台执行协作式停止；`succeeded`/`failed` 返回 409；已取消重复取消幂等 204。
- AC7/AC8/AC9：`GET /action-proposals` 全局提案安全摘要列表（cursor 分页 + 状态过滤），不含 evidence 原文/原始工具输出/未脱敏字段。
- AC10：前端「待审批」入口页，可进入既有提案详情/审批流程。
- AC11：回归全绿 + 前端 `typecheck`/`test`/`build` 通过。

### 明确不做
- 不做消息编辑/删除、`GET /runs`、会话搜索、重跑/重新生成、身份/审批人模型。
- 不改 `POST /sessions/{id}/runs` 主链路、不改既有消息/Run/提案详情接口契约。
- 不做数据库迁移（`CANCELLED`/`run_cancelled` 已存在）、不新增配置/凭据/Connector。
- 普通消息不做 LLM 生成、不做幂等键；不扩大审批/执行能力。

## 切片拆分（3 个独立可验收切片）

- [x] **S1（后端）：独立消息通道**。`requires_database_context` 收敛为公开函数 +
  `PlainMessageApplicationService` + `POST /sessions/{id}/messages`（普通→201 双消息、
  调查→409 回退）。验收：AC1/AC3 + AC2 服务端判定面。
- [x] **S2（后端）：取消 Run + 全局提案列表**。`cancel_run` + 协作式取消检查点 +
  `GET /action-proposals` + 摘要资源/游标/仓库分页。验收：AC4/AC5/AC6 + AC7/AC8/AC9。
- [x] **S3（前端）：工作台适配**。发送路由（普通→轻量/调查→回退）、普通回复投影、
  停止按钮、待审批入口 + 列表页 + 提案详情进入。验收：AC10 + AC2 前端回退面 + AC11 前端回归。

## 改动面（文件级）

### S1 后端
- `backend/src/application/message_routing.py`（新增）：`requires_database_context` 公开函数。
- `backend/src/application/plain_messages.py`（新增）：`SendPlainMessageCommand`、`PlainMessageApplicationService`。
- `backend/src/application/services.py`（修改）：`_requires_database_context` 改引公开函数（`test_p43_service_context.py` 断言迁移）。
- `backend/src/application/errors.py`（修改）：`InvestigationRequiredError`。
- `backend/src/api/v1/routes.py`（修改）：`POST /sessions/{session_id}/messages` + `APPLICATION_ERROR_STATUS` 映射。
- `backend/src/api/v1/schemas.py`（修改）：`PlainMessageResponse` 等。
- `backend/src/api/v1/dependencies.py`（修改）：`V1Services` 装配 `PlainMessageApplicationService`。
- 测试：`backend/tests/test_plain_message_api.py`（新增）、`test_p43_service_context.py`（迁移断言）。

### S2 后端
- `backend/src/application/services.py`（修改）：`cancel_run`；`execute_run` 事件循环协作式取消检查点。
- `backend/src/infrastructure/persistence/repositories.py`（修改）：`is_cancelled` 轻量状态查询。
- `backend/src/application/action_services.py`（修改）：`list_proposals` 只读用例。
- `backend/src/domain/records.py`（修改）：`ActionProposalCursor`。
- `backend/src/infrastructure/persistence/action_repositories.py`（修改）：`list_page`。
- `backend/src/api/v1/cursors.py`（修改）：注册 `ActionProposalCursor` 编解码。
- `backend/src/api/v1/routes.py`（修改）：`POST /runs/{run_id}/cancel`、`GET /action-proposals`。
- `backend/src/api/v1/schemas.py`（修改）：`ActionProposalSummaryResource`、`ActionProposalListResponse`。
- `backend/src/api/v1/resources.py`（修改）：`action_proposal_summary_resource`。
- 测试：`backend/tests/test_run_cancel.py`、`test_action_proposal_list.py`（新增）。

### S3 前端
- `frontend/src/api/v1/generated.ts`（`npm run generate:api` 重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`（修改）：`send_plain_message` / `cancel_run` / `list_action_proposals`。
- `frontend/src/api/v1/queries.ts`（修改）：query key / query / mutation。
- `frontend/src/features/workbench/WorkbenchPage.tsx`（修改）：`submit_text` 发送路由、停止按钮。
- `frontend/src/features/workbench/conversation-turns.ts`（修改）：普通回复（`run_id=null`）投影。
- `frontend/src/features/workbench/ActionProposalPanel.tsx`（修改）：支持按 `proposal_id` 取数。
- `frontend/src/features/approvals/ApprovalsPage.tsx`（新增）：提案列表页。
- `frontend/src/app/App.tsx`（修改）：`/workbench/approvals`、`/workbench/approvals/:proposal_id` 路由。
- `frontend/src/features/shell/Sidebar.tsx`（修改）：「待审批」入口。
- 前端测试：发送路由、普通回复投影、停止按钮、提案列表页。

### 文档
- `docs/design/session/P8会话工作台闭环Design.md`（随分支提交，已确认）。
- `docs/接口清单.md`（修改）：会话工作台模块三个缺表项标记交付 + 新端点。
- `docs/workpack/README.md`、`docs/workpack/P8-workbench-loop-closure/{plan,review,evidence}.md`。
- `docs/路线图.md`（修改）：当前阶段登记 P8 工作包（按 Design §1 张力声明）。

## 验证方法

- 后端（在 worktree `backend/` 内）：`..\.venv\Scripts\python.exe -m pytest tests -q`（全量回归，
  重点 `test_plain_message_api.py`、`test_run_cancel.py`、`test_action_proposal_list.py`、
  `test_p43_service_context.py`、`test_p2_application_services.py`、`test_api.py`、`test_p5_controlled_action.py`）。
- 前端（在 worktree `frontend/` 内）：`npm run typecheck`、`npm run test`、`npm run build`。
- API 类型生成：后端起在 8000 后 `npm run generate:api`。
- 门禁：`git diff --check`；只暂存本工作包文件，禁止 `git add .`；提交信息 `<类型>: <中文描述>`。

## 提交计划

- S1 后：`feat: 独立消息通道——普通消息轻量回复，调查意图回退 Run 主链路`
- S2 后：`feat: 取消运行中 Run 与全局提案安全摘要列表`
- S3 后：`feat: 会话工作台闭环前端适配（发送路由/停止按钮/待审批入口）`
- 收尾：`docs: P8 会话工作台闭环接口清单与工作包归档`
