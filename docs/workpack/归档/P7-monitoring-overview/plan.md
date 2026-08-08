# P7-monitoring-overview · 工作包计划

> 关联 PRD：`docs/prd/monitor/P7-monitoring-overview-page.md`（已确认，issue #45）
> 关联 Design：`docs/design/monitor/P7服务监控概览页Design.md`（已确认）
> 分支：`feat/P7-monitoring-overview` · worktree：`D:/market-handsome/oper-mind-worktrees/P7-monitoring-overview` · 基线：`main`（b886ecd）

## 范围

### 只做

- AC1/AC2/AC4：新增只读后端聚合接口 `GET /api/v1/monitor/overview`，返回静态注册表内全部已注册服务；
  概览数据全部来自 P5 历史样本表（不调用 `health_snapshot()`、不触发目标连接）；
  连接状态来自窗口内最新样本的 `source_status`（available/unavailable/not_configured/not_sampled）。
- AC2/AC3：每个服务展示最新采样样本（`latest_sample` 复用 `MonitorSampleResource`，null 不为 0）与
  趋势摘要（`trend_summary.sample_count` / `anomaly_sample_count`，窗口 = retention_hours）。
- AC6：异常采样点计数规则与 P5 一致（PG：slow_query_count>0 或 timeout_count>0；Redis：slowlog_count>0；
  任一样本 availability 与前一个不同），前端标记"采样点异常"，不出现"正在告警/正在推送"。
- AC1/AC3/AC5/AC7/AC9：前端 `/monitor` 监控概览页——全部服务概览表格/卡片、逐状态诚实空态
  （未配置/不可用/暂无历史采样/失败可重试）、页面标注"定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录"、
  每行可点击进入 `/services/:id`。
- AC8：接口与页面只返回脱敏标量，不含 SQL、对象名、用户名、IP 或凭据。
- AC10：回归——mock 评测（S1–S4）路径不受影响；既有服务接口契约不变；
  相关后端测试、前端 typecheck/test/build 全绿。
- 前端导航与路由：`GlobalNav.monitor` 键激活并路由 `/monitor`；`App.tsx` 注册 `/monitor` 路由并纳入运维模式壳；
  `ServiceContextNav` 运维模式下新增「服务监控」入口（`/monitor` 下 active）。

### 明确不做

- 不做外部告警推送（邮件/Slack/Webhook 等），如实标注未启用。
- 不做实时/近实时监控：概览只读历史样本，不现读快照、不触发目标连接。
- 不做跨服务对比图表、历史搜索、导出、聚合报表。
- 不新增监控凭据/连接、不新增采样器/历史采集逻辑（采样由 P5 交付，只消费）。
- 不做服务管理（接入/编辑服务等，属服务中心）。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）与 S1–S4 评测路径。
- 不修改既有 `GET /services`、`GET /services/{id}/monitor/history` 契约。
- 不引入概览接口的额外进程内缓存或分页（Design §2.6）。

## 已确认设计决策（Design §6）

- 后端聚合接口 `GET /api/v1/monitor/overview`，一次请求返回全部服务，非前端多接口聚合。
- 概览数据全部来自 P5 历史样本（最新采样快照 + 窗口统计），不现读快照、不触发目标连接。
- 概览行展示主机指标摘要（CPU/内存/磁盘，来自最新样本主机标量），标注"后端所在主机 · 单主机采集"。
- 异常标记为"采样点异常"（后端返回窗口内 `anomaly_sample_count`，前端据此标记）。
- 前端 `/monitor` 纳入运维模式壳，第二栏复用服务中心上下文导航并新增「服务监控」入口。
- 概览接口不引入额外缓存与分页。
- 异常采样点判定扩展 Redis `slowlog_count>0`（与 P5 前端一致），并已同步回写 PRD 功能需求 2/AC6。
- 概览接口读库限时 3 秒；`not_sampled` 时 `availability` 取 `unavailable`。

## 切片拆分（3 个独立可验收切片）

- [ ] S1：后端概览领域模型 + 应用服务 + 单元测试。覆盖 `MonitorOverviewData` /
  `MonitorServiceOverviewData` / `MonitorTrendSummaryData`、状态判定（available/unavailable/
  not_configured/not_sampled）、最新样本透出、异常计数与 P5 一致、无样本/未配置/不可用诚实状态、
  不触发目标连接（断言无 `health_snapshot` 调用）。
- [ ] S2：概览 API 契约 + 路由 + API 测试。覆盖 `GET /api/v1/monitor/overview` 契约、脱敏、
  meta 关联、读库限时、既有服务接口回归（`GET /services`、`GET /services/{id}/monitor/history` 不变）。
- [ ] S3：前端 `/monitor` 概览页 + 导航/路由 + 交互测试。覆盖全部服务展示、逐状态空态、
  异常标记"采样点异常"、诚实标注无"实时监控"、行点击跳详情、失败重试、`GlobalNav`/`App`/`ServiceContextNav` 导航。

## 改动面（文件级）

### 后端

- `backend/src/domain/monitoring.py`：新增 `MonitorOverviewData`、`MonitorServiceOverviewData`、
  `MonitorTrendSummaryData`（Pydantic frozen + extra=forbid）。
- `backend/src/application/monitoring.py`：新增 `MonitorOverviewApplicationService.get_overview()`。
- `backend/src/api/v1/schemas.py`：新增 `MonitorOverviewResponse`、`MonitorServiceOverviewResource`、
  `MonitorTrendSummaryResource`（`latest_sample` 复用 `MonitorSampleResource`）。
- `backend/src/api/v1/resources.py`：新增 `monitor_overview_resource` mapper。
- `backend/src/api/v1/routes.py`：新增 `GET /api/v1/monitor/overview` 路由（`_monitor_overview` 与
  `_monitor_history` 同位置临时装配，读库限时 3 秒）。
- `backend/src/api/v1/dependencies.py`：装配概览应用服务（可经 `_monitor_history` 同款临时装配方式；
  实际实现采用 routes.py 内 `_monitor_overview` 临时装配，与 Design §3 允许位置一致）。
- `backend/tests/test_monitor_overview_api.py`（新增）。

### 前端

- `frontend/src/api/v1/client.ts`、`queries.ts`：新增 `get_monitor_overview` 与查询；
  `generated.ts` 仅通过 `npm run generate:api` 更新（禁止手工编辑）。
- `frontend/src/features/monitor/MonitoringOverviewPage.tsx`（新增）+ `MonitoringOverviewPage.test.tsx`（新增）。
- `frontend/src/features/shell/GlobalNav.tsx`、`ServiceContextNav.tsx`、`frontend/src/app/App.tsx`：导航与路由。
- `frontend/src/test/handlers.ts`：新增概览 MSW fixture。
- 样式复用既有 `service-detail.css` / `service-center.css`，一般不新增样式文件。

### 文档（随工作包 PR 交付）

- `docs/design/monitor/P7服务监控概览页Design.md`（已确认，随本 PR 提交）
- `docs/prd/monitor/P7-monitoring-overview-page.md`（AC6/功能需求 2 已回写 Redis 扩展）
- `docs/prd/README.md`、`docs/prd/monitor/README.md`（PRD 状态推进「进行中」）
- `docs/workpack/README.md`（工作包登记）

### 无功能改动

- 无数据库迁移、无新配置、无新 Connector、无凭据/连接改动。
- `data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径不改。

## 验证方法

- 后端：从 `backend/` 运行 `..\.venv\Scripts\python.exe -m pytest tests/test_monitor_overview_api.py -q`，
  随后运行 `..\.venv\Scripts\python.exe -m pytest tests/test_monitoring.py tests/test_monitor_history_api.py tests/test_p4_service_center.py tests/test_p2_api_v1.py -q`，
  最后运行 `..\.venv\Scripts\python.exe -m pytest tests -q`。
- 前端：worktree 内安装依赖后运行 `npm run generate:api`、`npm run typecheck`、`npm run test`、`npm run build`。
- 门禁：`git diff --check`；审查变更确认无凭据、DSN、环境变量名、原始日志、原始异常或 `sk-` 字面量；
  只暂存工作包文件。

## 提交计划

- S1：`feat: P7 监控概览后端领域与应用服务`
- S2：`feat: P7 监控概览只读 API 契约与路由`
- S3：`feat: P7 服务监控概览页与导航落地`
- 收尾：`docs: P7 服务监控概览页工作包与验收证据`

## 停审阅点

计划已就绪，待用户确认范围、切片、改动面、验证方法后进入 `dev-execute`。
