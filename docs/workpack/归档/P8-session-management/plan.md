# P8-session-management · 工作包计划

> 关联 PRD：`docs/prd/session/P8-session-management.md`（已确认，issue #64）
> 关联 Design：`docs/design/session/P8会话管理Design.md`（草稿 → 本工作包确认后置「已确认」）
> 分支：`feat/p8-session-management`（基线 `main`）
> worktree：`D:/market-handsome/oper-mind-worktrees/p8-session-management`

## 范围

### 只做

- AC1–AC4（全局 Run 列表，Design §2.1）：新增 `GET /runs`，跨会话跨服务 Run 安全摘要，
  cursor 分页 + status / service_id 过滤；错误经 `_safe_run_error` 白名单。
- AC5–AC7（会话搜索，Design §2.2）：`GET /sessions` 增加可选 `q` 参数（标题字面匹配，
  转义 LIKE 通配符；超长/控制字符/空串 → 422 明确错误）；无 `q` 行为不变。
- AC8（前端侧栏搜索 + Ctrl K，Design §2.3）：搜索框（300ms debounce 服务端搜索）+
  document 级 `Ctrl+K` 聚焦（preventDefault 阻止浏览器默认）；Esc 清空。
- AC9（最近调查入口与页，Design §2.3）：Sidebar「最近调查」入口 → `/workbench/runs`，
  RunsPage 状态标签 + 服务下拉过滤 + cursor 分页 + 点击行进既有 Run 详情。
- AC10（回归）：既有 `test_api.py` / `test_p2_api_v1.py` 相关全绿；前端
  `typecheck`/`test`/`build` 通过。
- 文档：`docs/接口清单.md` 缺表两行标记已交付 + 补 `GET /runs` 行；
  `docs/完善清单.md` P1-12 标 ✅（端到端复验后）；`docs/路线图.md` 当前阶段登记本工作包。

### 明确不做

- 消息编辑/删除、重跑/重新生成、会话导出（接口清单欠账，另行排期）。
- 不改变既有 `GET /sessions` / `GET /sessions/{id}/runs` / `GET /services/{id}/activities`
  契约与行为；不改 SSE 与 Run 执行链路。
- 不做跨会话消息全文搜索（只搜会话标题）。
- 不暴露证据原文、工具输出、CoT/Prompt、凭据/DSN/`sk-` 或原始错误文本。
- 不做命令面板；`Ctrl K` 首版只聚焦搜索框。
- 无数据库迁移、无配置项、无 Connector/凭据、无权限/审批/执行能力变化。

## 切片拆分（3 个独立可验收切片）

- [ ] S1：全局 Run 列表（后端）——`GlobalRunData` + `list_page` + `GET /runs` 路由/资源/测试。
  验收语义：AC1（跨会话跨服务摘要分页）、AC2（状态过滤）、AC3（service_id 过滤，
  不存在值空列表）、AC4（摘要无未脱敏内容）。
- [ ] S2：会话搜索（后端）——`list_page` 增加 `q` + 路由校验与透传/测试。
  验收语义：AC5（标题匹配）、AC6（无 `q` 契约不变）、AC7（非法 `q` 明确错误）。
- [ ] S3：前端适配——侧栏搜索框 + Ctrl K + 最近调查页 + client/queries/路由接线/测试。
  验收语义：AC8、AC9、AC10（前端回归）。

## 改动面（文件级）

### 后端（修改）

- `backend/src/domain/records.py`：新增 `GlobalRunData`。
- `backend/src/infrastructure/persistence/repositories.py`：
  `SqlAlchemyDiagnosisRunRepository.list_page`（跨会话 + join 会话标题 + status/service_id
  过滤）；`SqlAlchemySessionRepository.list_page` 增加 `q` 过滤（LIKE 字面转义）。
- `backend/src/api/v1/routes.py`：新增 `GET /runs`；`GET /sessions` 增加 `q` 校验与透传。
- `backend/src/api/v1/schemas.py`：新增 `GlobalRunSummaryResource`、`GlobalRunListResponse`。
- `backend/src/api/v1/resources.py`：新增 `global_run_summary_resource`（复用 `_safe_run_error`）。
- 后端测试（新增）：`tests/test_runs_list.py`（AC1–AC4 服务端面）、
  `tests/test_session_search.py`（AC5–AC7）。

### 前端（修改 + 新增）

- `frontend/src/api/v1/generated.ts`（`npm run generate:api` 重新生成，禁止手编）。
- `frontend/src/api/v1/client.ts`：`list_runs`；`list_sessions` 透传 `q`。
- `frontend/src/api/v1/queries.ts`：`runs_list` query key / query；`sessions` key 含 `q`。
- `frontend/src/features/runs/RunsPage.tsx`（**新增**）：最近调查页。
- `frontend/src/features/shell/Sidebar.tsx`：搜索框 + Ctrl K + 最近调查入口。
- `frontend/src/app/App.tsx`：`/workbench/runs` 路由。
- 前端测试（新增/修改）：RunsPage 列表/过滤/空态/跳转；侧栏搜索交互与 Ctrl K 聚焦。

### 文档

- `docs/接口清单.md`、`docs/完善清单.md`（P1-12）、`docs/路线图.md`。

### 明确无改动

- 无数据库迁移（复用 sessions/runs 既有表）；无配置项/环境变量；无 Connector/凭据；
  SSE 与 Run 执行链路不动；`data/`、`demo/` 不动；`docs/prd/` 不动。

## 验证方法

- 后端（在 worktree `backend/` 下执行，使用 worktree 内重建的 venv）：
  - 聚焦：`..\.venv\Scripts\python.exe -m pytest tests/test_runs_list.py tests/test_session_search.py -q`
  - 回归：`..\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_p2_api_v1.py -q`
    （提交前再跑全量 `tests -q`）
- 前端（在 worktree `frontend/` 下执行）：`npm run typecheck`、`npm run test`、`npm run build`。
- API 契约：后端起 8000 → `npm run generate:api` 重新生成 generated.ts。
- 门禁：`git diff --check`；只暂存本工作包文件，禁止 `git add .`。

## 提交计划

- S1 后端 Run 列表：
  `feat: 全局 Run 列表——跨会话跨服务调查检索（P8，issue #64）`
- S2 后端会话搜索：
  `feat: 会话搜索——GET /sessions 标题关键词 q 参数（P8，issue #64）`
- S3 前端：
  `feat: 侧栏会话搜索、Ctrl K 与最近调查页（P8，issue #64）`
- 每个切片完成后集中 Test → 独立子代理 Review → 提交；全部完成后经
  `dev-deliver`（fetch+merge main → push → PR → 合并 → 归档）。
