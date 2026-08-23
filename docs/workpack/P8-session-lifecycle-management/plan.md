# P8-session-lifecycle-management · 工作包计划

> PRD：`docs/prd/session/P8-session-lifecycle-management.md`（已确认，issue #96）
> Design：`docs/design/session/P8会话生命周期管理Design.md`（独立 Review PASS，用户已确认）
> 基线：`main` / `origin/main` 的 PR #95（active 会话重命名与逻辑归档）
> 当前分支：`codex/prd-p8-session-workbench-lifecycle`

## 范围

### 只做

- S1 后端：复用 `PATCH /sessions/{id}` 支持 archived → active；Repository 条件更新保证首次转换才
  清空 `archived_at`、更新 `updated_at`；Session 活动时间改为单列单调 touch，避免 Run/普通消息旧
  快照覆盖生命周期；重复/并发恢复幂等；保留消息、Run、提案、审计和服务关联。
- S2 前端：侧栏 active/archived 双视图、标题搜索、cursor 分页、空态/失败态；列表与详情恢复确认；
  不确定结果回读；全会话缓存收敛；恢复后 active 录入控件重新出现。
- S2 回归修正：archived 只限制会话录入，不再统一隐藏 Run 取消/重跑和提案操作；运行中 Run 继续刷新。

### 明确不做

- 不新增端点、迁移、会话副本、生命周期业务审计事件或真实外部访问。
- 不做永久/批量删除、批量恢复、保留期限、标签/文件夹/置顶、消息全文搜索。
- 不改变 Run/提案/消息/导出/审计的服务端既有语义。

## 切片拆分

- [x] S1：后端 CAS 恢复 + 单列 touch + API/Repository/Application/竞态测试 → AC6、AC8、AC10、AC11、AC13、AC14
- [x] S2：前端双视图/分页/恢复/事实回读 + archived 只读边界修正 → AC1–AC7、AC9、AC12、AC15

## 改动面

- 后端：`src/domain/repositories.py`、`src/infrastructure/persistence/repositories.py`、
  `src/infrastructure/persistence/plain_message_writer.py`、`src/application/services.py`、
  `src/application/contracts.py`、`src/api/v1/{routes,schemas}.py` 与相关测试。
- 前端：`app/App.tsx`、`features/shell/Sidebar.tsx`、`features/session/SessionActions.tsx`、
  `features/session/SessionNavigationContext.tsx`、
  `features/workbench/WorkbenchPage.tsx`、`api/v1/queries.ts`、样式、MSW 与交互测试。
- 文档：Design、workpack 三件套、接口清单、完善清单、路线图；完成后同步 PRD/索引状态。

## 验证方法

后端（`backend/`）：

- `..\.venv\Scripts\python.exe -m pytest tests/test_p2_repositories.py tests/test_p2_application_services.py tests/test_p2_api_v1.py tests/test_session_search.py tests/test_plain_message_api.py tests/test_run_rerun.py -q`
- Issue 新增生命周期 API 测试文件聚焦执行。
- `..\.venv\Scripts\python.exe -m pytest tests -q`

前端（`frontend/`）：

- 聚焦：`npm run test -- src/features/session/SessionActions.test.tsx src/features/shell/Sidebar.test.tsx src/app/App.test.tsx`
- 全量：`npm run typecheck`、`npm run test`、`npm run build`

门禁与复核：

- `git diff --check`
- 独立代码 Review 核对 AC1–AC15、SQLite/PostgreSQL 并发条件更新、Run touch 竞态、错误后新 GET、
  旧详情 GET 取消、多状态/关键词/分页缓存立即收敛、共享导航 context、unknown/refetch 生命周期动作、
  Run/提案边界及敏感信息。
- 不连接真实资源；检查改动不含凭据、DSN、`sk-`、原始工具输出、Prompt 或 CoT。

## 文档状态流

- 用户确认 Design/plan 后：Design → 已确认；PRD 与两级索引 → 进行中；workpack README → 进行中。
- 实现与测试完成：回写 `evidence.md`，独立代码 Review 写 `review.md`；PASS 后收口接口清单/完善清单/路线图。
- 用户未明确要求前不提交、不推送、不建 PR、不关闭 Issue。

## 状态

- [x] 修订后独立 Design Review PASS（第三轮终审，无 P0–P2）
- [x] 用户确认 7 项设计决策与本计划
- [x] 进入实现
- [x] 实现、全量门禁与本地浏览器端到端复验完成
- [x] 独立代码终审 PASS，进入待提交交付态
