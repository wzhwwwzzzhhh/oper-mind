# P8-session-lifecycle-management · 验证证据

> 日期：2026-08-23
> 状态：实现、验证与独立代码终审 PASS；PR #97 CI 全绿，待合并

## 交付摘要

- 后端复用 `PATCH /api/v1/sessions/{id}` 实现 archived → active 原地恢复；状态 CAS 保证只有首次转换命中，
  恢复与 Run/普通消息活动时间均用单调列更新，避免旧快照或较早时间覆盖生命周期事实。
- 前端增加 active/archived 双视图、标题搜索、cursor 分页、诚实空态/错误态，以及列表和详情恢复入口；
  恢复对明确拒绝与不确定结果分别处理，并在成功后收敛详情和所有会话列表缓存。
- archived 只限制重命名、消息编辑/删除、新消息与新调查录入；Run 取消/重跑、提案和导出继续按既有规则。
- 恢复不会自动提交 archived 期间遗留在 sessionStorage 的调查或普通消息意图。

## AC 证据

| AC | 结果 | 主要证据 |
|---|---|---|
| AC1–AC3 | PASS | `Sidebar.test.tsx`：双视图状态隔离、archived 搜索无 active 回退、空/失败态、分页成功和下一页失败重试 |
| AC4–AC6 | PASS | `App.test.tsx`：archived 历史/导出基线、录入只读、终态重跑、running Run 继续展示并可取消 |
| AC7 | PASS | `SessionActions.test.tsx`：恢复确认明确“不复制内容、不创建或启动调查”，双击只有一次 PATCH |
| AC8 | PASS | `test_p2_api_v1.py`：同 id、标题、消息/Run/事件序列保持，`archived_at=null`；无迁移/副本 |
| AC9 | PASS | `App.test.tsx`：恢复后 Composer 与 active 生命周期动作重新出现；浏览器 E2E 验证同一详情恢复 |
| AC10 | PASS | `test_p2_application_services.py`：双线程并发恢复同一时间事实；重复恢复不更新时间 |
| AC11 | PASS | `SessionActions.test.tsx`：明确 4xx、network→active、network→archived、无效 2xx、错 id 回读 |
| AC12 | PASS | `SessionActions.test.tsx`：同步请求锁阻止双击；成功后详情/list 前缀取消、清除、重置与预取 |
| AC13 | PASS | API 恢复前后消息/Run/RunEvent 主键或序列集合一致；未新增生命周期事件模型或写入 |
| AC14 | PASS | 改动仅应用 SQLite 元数据与前端 UI；浏览器 E2E 使用 mock 配置，无 Connector/Tool/真实资源访问 |
| AC15 | PASS | 后端全量 570 项 + 最终关联回归 8/8、前端 196 项全量回归通过；Ruff/Mypy/typecheck/build 通过 |

## 自动化门禁

仓库根 `.venv` 指向已卸载的 Python 3.11；为完成验证，在 Git 忽略的 `.tmp/backend-py312` 使用
Codex bundled Python 3.12 和仓库锁定依赖执行，未修改 `requirements.txt`。

- 后端聚焦：`python -m pytest tests/test_p2_application_services.py tests/test_p2_repositories.py tests/test_p2_api_v1.py -q`
  → 23 passed（补充关联回归单独执行 16 passed）。
- 后端全量：`python -m pytest tests -q` → 570 passed；随后只新增关联保留测试，目标文件 8 passed。
- 后端静态：`python -m ruff check src tests` → PASS；`python -m mypy src` → 111 source files PASS。
- 前端聚焦：SessionActions + Sidebar + App → 70 passed。
- 前端全量：`npm run test` → 196 passed；`npm run typecheck` → PASS；`npm run build` → PASS。
- `git diff --check`：PASS（只有 Windows LF→CRLF 提示，无空白错误）。

## 浏览器端到端复验

使用隔离 SQLite、mock 模型配置、Vite 5174、后端 8000 和本机 headless Chrome：

1. API 创建 Session 并逻辑归档；
2. 会话侧栏切换“已归档”，从归档列表进入同一详情；
3. 确认 archived 标识与 Composer 不存在；
4. 确认恢复，等待“会话已恢复”；
5. 校验 URL/session id 不变、active 视图选中、Composer 恢复；
6. API 回读 `status=active`、`archived_at=null`，页面/API 错误列表为空。

结果：`same_resource=true`、`composer_restored=true`、`browser_errors=[]`。临时数据库、脚本和截图位于
Git 忽略的 `.tmp/`，不进入交付文件。

## 安全与范围核对

- 无数据库迁移、新端点、新配置、凭据、真实网络目标、Connector、Tool 或 Agent 改动。
- 无生命周期业务审计事件；既有通用请求日志行为未修改。
- `git diff` 未包含 `.env`、`config.local.yaml`、API Key、DSN、Prompt、CoT 或原始工具输出。
- 已提交并推送至 `codex/prd-p8-session-workbench-lifecycle`，PR #97 CI 全绿；未自动合并，
  issue #96 由 `Closes #96` 在 PR 合并后自动关闭。
