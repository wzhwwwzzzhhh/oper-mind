# P8-rerun-investigation · 工作包计划

> 关联 PRD：`docs/prd/session/P8-rerun-investigation.md`（已确认，issue #65）
> 关联 Design：`docs/design/session/P8调查重跑Design.md`（草稿 → 本工作包确认后置「已确认」）
> 分支：`feat/p8-rerun-investigation`（基线 `main`）
> worktree：`D:/market-handsome/oper-mind-worktrees/p8-rerun-investigation`

## 范围

### 只做

- AC1–AC4（重跑调查，Design §2.1/§2.2）：新增 `POST /runs/{run_id}/rerun`（202，
  `Idempotency-Key` 必填）；仅终态（succeeded/failed/cancelled）可重跑，未终态 → 409
  `RUN_NOT_TERMINAL`；复用原 Run 的 session / query（经 input message）/ service_id；
  新 Run 记录 `rerun_of_run_id`；幂等复用 `(session_id, endpoint, idempotency_key)`
  作用域（`RUN_RERUN_ENDPOINT` 独立），指纹含 run_id 防同 query 误重放。
- AC5（关联展示，Design §2.4）：`DiagnosisRunResource` / `GlobalRunSummaryResource`
  兼容扩展 `rerun_of_run_id`；新 Run 展示「重跑自 Run X」；原 Run「已被重跑为 Run Y」
  由前端会话时间线纯前端推导（全量已加载 runs，倒序前提成立）。
- AC6（全局列表来源标记，Design §2.4）：`list_page` select 补 `rerun_of_run_id` 列，
  RunsPage 行内「重跑自」来源标记。
- AC7（脱敏）：重跑响应复用既有 `RunResponse` 收敛，不含证据原文/工具输出/CoT/Prompt/
  凭据/DSN/`sk-`；query 不进响应字段。
- AC8（前端入口，Design §2.4）：终态 Run 答复区 `RerunButton`「重新生成」（每次点击
  新幂等键，loading 同步阻断双击；成功 invalidate session runs/messages 进入新 Run）。
- AC9（历史兼容）：`rerun_of_run_id` NULL 历史 Run 按普通 Run 处理，契约不变。
- AC10（回归）：`test_api.py` / `test_p2_application_services.py` /
  `test_p5_controlled_action.py` 相关全绿；前端 `typecheck`/`test`/`build` 通过。
- 文档：`docs/接口清单.md` 缺表「重跑 / 重新生成」标记已交付 + 补 `POST /runs/{id}/rerun`
  行与 `rerun_of_run_id` 字段说明；`docs/路线图.md` 当前阶段登记本工作包。

### 明确不做

- 不做「编辑后重跑」（改问题再跑 = 普通创建）。
- 不做并发重跑限制策略（幂等键只防同一请求重复提交，不限制不同键的多次重跑）。
- 不做重跑历史独立页面；不做原 Run 反查字段/端点（`rerun_by_run_id` /
  `GET /runs/{id}/reruns`）——前端时间线推导即满足 AC5/AC6。
- 不改变既有 `POST /sessions/{id}/runs` 创建行为与 `GET /sessions/{id}/runs` /
  `GET /runs` / `GET /runs/{run_id}` 既有契约（来源字段是兼容扩展）。
- 不改 SSE、Run 执行链路、工具网关、审批/执行白名单；无 Connector/凭据/权限变化。
- 不暴露证据原文、工具输出、CoT/Prompt、凭据/DSN/`sk-`。

## 切片拆分（2 个独立可验收切片）

- [ ] S1：重跑后端链路——迁移（`diagnosis_runs.rerun_of_run_id` 自引用列 + 索引）+
  模型/记录/repository 字段同步 + `rerun_run` 应用服务（终态校验、幂等、
  `_accept_run_in_transaction` 参数化）+ `POST /runs/{run_id}/rerun` 路由/资源/错误码 +
  后端测试。
  验收语义：AC1（终态可重跑、来源关联记录）、AC2（未终态 409）、AC3（query/service
  复用）、AC4（幂等重放与指纹冲突）、AC7、AC9；迁移 upgrade 可执行、既有测试全绿。
- [ ] S2：前端重跑入口与关联展示——generated 契约 + client/queries 接线 +
  `RerunButton`（三个终态分支）+ 时间线投影（重跑自/已被重跑标记）+ RunsPage 来源标记 +
  前端测试。
  验收语义：AC8（按钮/loading/进入新 Run）、AC5（双向关联展示）、AC6（全局列表来源标记）、
  AC10（前端回归）。

## 改动面（文件级）

### 后端（修改 + 新增）

- `backend/migrations/versions/20260812_12_p8_run_rerun.py`（**新增迁移**）：
  `diagnosis_runs` 加 `rerun_of_run_id`（Uuid NULL，自引用 FK RESTRICT）+ 索引
  `ix_diagnosis_runs_rerun_of_id`；SQLite 用 `batch_alter_table`；downgrade 防御检查
  （存在 rerun 历史行拒绝回滚）。
- `backend/src/infrastructure/persistence/models.py`：`DiagnosisRunRecord` 加列。
- `backend/src/domain/records.py`：`DiagnosisRunData` 加 `rerun_of_run_id`；
  `GlobalRunData` 加同名字段。
- `backend/src/infrastructure/persistence/repositories.py`：`add` /
  `_diagnosis_run_data` / `_global_run_data` mapper / `list_by_session` / `list_page`
  同步字段。
- `backend/src/application/services.py`：`rerun_run` + `_rerun_fingerprint` +
  `_accept_run_in_transaction` 可选参数（`rerun_of_run_id` + `endpoint`，幂等检查/写入
  两处同用）+ `_load_idempotency_after_conflict` endpoint 参数化 +
  `RUN_RERUN_ENDPOINT` 常量。
- `backend/src/application/errors.py`：新增 `RunNotTerminalError`。
- `backend/src/api/v1/routes.py`：`APPLICATION_ERROR_STATUS` 加 `RUN_NOT_TERMINAL: 409`；
  新增 `POST /runs/{run_id}/rerun`（Idempotency-Key 头必填，202 RunResponse）。
- `backend/src/api/v1/schemas.py`：`DiagnosisRunResource` / `GlobalRunSummaryResource`
  加 `rerun_of_run_id`。
- `backend/src/api/v1/resources.py`：`run_resource` / `global_run_summary_resource` 透传。
- 后端测试（新增）：`tests/test_run_rerun.py`（AC1–AC5 服务端面 / AC7 / AC9 +
  归档会话 409 + 指纹冲突 409 + 竞争重读）。

### 前端（修改）

- `frontend/src/api/v1/generated.ts`（`npm run generate:api` 重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`：`rerun_run` 方法与类型导出。
- `frontend/src/api/v1/queries.ts`：`rerun_run_mutation`。
- `frontend/src/features/workbench/conversation-turns.ts`：`rerun_of_run_id` 字段 +
  「原 Run → 最新重跑」推导映射。
- `frontend/src/features/workbench/WorkbenchPage.tsx`：`RerunButton` 组件 + 三个终态
  分支接入。
- `frontend/src/features/runs/RunsPage.tsx`：行内「重跑自」来源标记。
- 前端测试（新增/修改）：RerunButton 交互；投影推导标记；RunsPage 来源标记；
  `frontend/src/test/handlers.ts` 补 `/runs/{id}/rerun` handler 与 `rerun_of_run_id`
  fixtures。

### 文档

- `docs/接口清单.md`、`docs/路线图.md`。

### 明确无改动

- 无新表（仅 `diagnosis_runs` 一列）；无配置项/环境变量；无 Connector/凭据；
  SSE 与 Run 执行链路不动；`data/`、`demo/` 不动；`docs/prd/` 不动；
  `docs/完善清单.md` 不动（重跑不在完善清单欠账表）。

## 验证方法

- 后端（在 worktree `backend/` 下执行，使用 worktree 内重建的 venv）：
  - 迁移：`..\.venv\Scripts\python.exe -m alembic -c alembic.ini upgrade head`
    （worktree 内应用库，验证 upgrade；downgrade 防御检查在测试中覆盖）
  - 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_run_rerun.py -q`
  - 回归：`..\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_p2_application_services.py tests/test_p5_controlled_action.py -q`
    （提交前再跑全量 `tests -q`）
- 前端（在 worktree `frontend/` 下执行）：`npm run typecheck`、`npm run test`、`npm run build`。
- API 契约：后端起 8000 → `npm run generate:api` 重新生成 generated.ts。
- 门禁：`git diff --check`；只暂存本工作包文件，禁止 `git add .`。

## 提交计划

- S1 后端重跑链路（含迁移）：
  `feat: 调查重跑——POST /runs/{id}/rerun 与来源关联（P8，issue #65）`
- S2 前端重跑入口与关联展示：
  `feat: 前端重新生成入口与重跑关联展示（P8，issue #65）`
- 每个切片完成后集中 Test → 独立子代理 Review → 提交；全部完成后经
  `dev-deliver`（fetch+merge main → push → PR → 合并 → 归档）。
