# P7 服务监控概览页 · Design

> 状态：已确认
> 更新：2026-08-08
> 关联：`docs/prd/monitor/P7-monitoring-overview-page.md`（issue #45，已确认）、
> `docs/design/monitor/P5监控历史趋势与页面告警Design.md`（历史样本/状态语义）、
> `docs/design/monitor/P6服务主机指标监控Design.md`（主机标量）、
> `docs/产品定义.md` §5.5（监控诚实性）、`docs/开发规范.md` §5（不得把一次读取伪装成实时监控）、
> `docs/路线图.md`（P7 三个已确认 PRD）、
> `backend/src/infrastructure/persistence/monitor_repositories.py`、`backend/src/application/monitoring.py`、
> `backend/src/api/v1/routes.py`、`frontend/src/features/shell/GlobalNav.tsx`、`frontend/src/app/App.tsx`。

## 1. 目标与范围

**一句话目标**：把全局导航「服务监控」死占位落地为 `/monitor` 多服务监控概览页——一张视图聚合静态注册表内全部已接入服务的连接状态、最新采样快照标量、近期趋势摘要与异常采样点标记，并可进入单个服务详情页，全程诚实标注数据来源。

### 做什么

- 新增只读**后端聚合概览接口** `GET /api/v1/monitor/overview`：一次请求返回全部已注册服务的
  连接状态、最新采样样本（脱敏标量）、窗口内趋势摘要（样本数 + 异常采样点计数）、主机指标摘要。
- 概览数据**全部来自 P5 历史样本表**（`service_monitor_samples`），不触发真实目标连接、不现读快照，
  符合"概览展示最新采样快照与历史记录，不是实时值"的 PRD 语义。
- 前端新增 `/monitor` 监控概览页：表格/卡片展示所有服务（服务名/类型/连接状态/最新延迟/慢查询/超时/
  异常标记/主机指标摘要），每行可点击进入 `/services/:id`。
- 全局导航 `monitor` 键激活并路由 `/monitor`；运维模式第二栏上下文导航新增「服务监控」入口。
- 诚实标注与降级：页面标注"定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录"；逐服务独立降级
  （未配置 → "未配置"；采样失败 → "不可用"；无样本 → "暂无历史采样"；请求失败 → 失败空态可重试）。

### 明确不做

- 不做外部告警推送（邮件/Slack/Webhook 等），如实标注未启用（与 P5 一致）。
- 不做实时/近实时监控：概览只读历史样本，不现读快照、不触发目标连接。
- 不做跨服务对比图表、历史搜索、导出、聚合报表。
- 不新增监控凭据/连接、不新增采样器/历史采集逻辑（采样由 P5 交付，本 PRD 只消费）。
- 不做服务管理（接入/编辑服务，属服务中心）。
- 不改 mock 数据源（`data/mock_db.py`、`data/scenarios.py`）与 S1–S4 评测路径。
- 不修改既有 `GET /services`、`GET /services/{id}/monitor/history` 契约。
- 概览页不展示原始 SQL、对象名、用户名、IP 或凭据；主机指标仅摘要标量，标注"后端所在主机 · 单主机采集"。

## 2. 设计决策

### 2.1 概览数据组合方式（回答 PRD 开放问题 1）

采用**后端聚合接口**，而非前端多接口聚合：

- 前端多接口聚合 = 1 次 `GET /services` + N 次 `GET /services/{id}/monitor/history`，产生 N+1 请求、
  每行独立失败/重试逻辑，且把"聚合"职责推给页面。
- 后端聚合接口单次请求返回全部服务的同构概览对象，前端只渲染一行数据结构；服务数量来自静态注册表
  （当前 4 个），无需分页，接口结构稳定、可整体限时与缓存。

### 2.2 数据来源与状态判定（回答 PRD 开放问题"是否现读快照"）

概览数据**只读应用库的 P5 历史样本表**，不调用 `health_snapshot()`、不触发任何目标连接：

- **连接状态**（`connection_status`）来自窗口内**最新一条样本**的 `source_status`：
  - 无任何样本 → `not_sampled`（前端"暂无历史采样"）；
  - 最新样本 `source_status = not_configured` → `not_configured`（前端"未配置"）；
  - 最新样本 `source_status = unavailable` → `unavailable`（前端"不可用"）；
  - 最新样本 `source_status = available` → `available`（前端展示真实标量）。
- **最新快照标量**：窗口内最新一条样本（含 PG/Redis 专用标量与主机标量）作为 `latest_sample`，
  保持 null 不为 0；`availability` 字段供前端做"正常/需关注"状态。
- **趋势摘要**：窗口（`now - retention_hours` 至 `now`）内样本数与异常采样点计数，按时间升序判定；
  判定规则与 P5 前端一致（见 §2.3）。

> 说明：P5 历史查询接口会把 `not_configured` 样本过滤掉（返回空序列），而概览接口需要读到状态样本才能
> 区分"未配置/不可用/无样本"。因此概览应用服务**直接复用 `SqlAlchemyMonitorSampleRepository.list_between()`**
> 读取窗口内原始样本（含状态样本），自行计算状态与最新样本，不复用历史查询接口的过滤逻辑。

### 2.3 异常采样点计数

窗口内样本（排除 `not_configured` 空标量样本）中，满足以下任一条件即计为异常采样点：

- PG：`slow_query_count > 0` 或 `timeout_count > 0`；
- Redis：`slowlog_count > 0`（与 P5 前端已实现的 Redis 异常判定一致，见
  `frontend/src/features/services/ServiceDetailPage.tsx` 的 `is_redis` 分支）；
- 任一样本 `availability` 与前一个样本不同（可用性状态变化）。

后端返回窗口内 `anomaly_sample_count`，前端对 `anomaly_sample_count > 0` 的行标记为"采样点异常"，
**不出现"正在告警/正在推送"表述**（对齐 P5 语义与 PRD AC6）。
> 说明：PRD AC6/功能需求 2 的枚举未显式列 Redis `slowlog_count>0`，但 P5 已交付的前端异常判定
> 对 Redis 使用该规则，本设计与其保持一致；该扩展列入 §6 待用户确认决策，并同步回写 PRD。

### 2.4 主机指标摘要（回答 PRD 开放问题 2）

P6 历史样本已携带 `host_cpu_percent / host_memory_percent / host_memory_bytes / host_disk_used_percent`
四个主机标量（P6 Design：同一轮所有服务样本主机标量相同）。概览行直接展示最新样本的这三个百分比标量
（CPU/内存/磁盘）作为摘要，并标注"后端所在主机 · 单主机采集"，不重复进程/网络明细（明细仍在服务详情页）。

### 2.5 接口契约

```text
GET /api/v1/monitor/overview
```

无查询参数，返回静态注册表内全部已注册服务（顺序同注册表），响应结构：

```json
{
  "items": [
    {
      "service_id": "postgres-production",
      "title": "生产 PostgreSQL 主库",
      "kind": "postgres",
      "connection_status": "available | unavailable | not_configured | not_sampled",
      "availability": "healthy | unhealthy | unavailable | not_configured",
      "latest_sample": {
        "id": "…",
        "observed_at": "…",
        "availability": "…",
        "p50_ms": 12.5, "p95_ms": 28.0,
        "slow_query_count": 0, "timeout_count": 0,
        "memory_bytes": null, "client_connections": null, "slowlog_count": null,
        "host_cpu_percent": 42.5, "host_memory_percent": 61.0,
        "host_memory_bytes": null, "host_disk_used_percent": 70.0,
        "performance_signal": "…",
        "source_status": "available"
      },
      "trend_summary": {
        "sample_count": 12,
        "anomaly_sample_count": 2
      }
    }
  ],
  "source": "scheduled_sampling",
  "sample_interval_seconds": 300,
  "retention_hours": 24,
  "meta": { "request_id": "…", "trace_id": null }
}
```

- `latest_sample` 为 `null` 当且仅当窗口内无样本（`connection_status=not_sampled`），
  此时 `availability` 统一取 `unavailable`（前端据此显示"暂无历史采样"，不伪造健康结论）。
- `latest_sample` 结构复用 `MonitorSampleResource` 字段（含 P6 主机标量），映射走 `sample.model_dump()`。
- 接口只返回脱敏标量与状态，不含 SQL、对象名、用户名、IP 或凭据。
- 响应顶部携带 `source=scheduled_sampling`、`sample_interval_seconds`、`retention_hours`，前端据此诚实标注。
- **读库超时预算**：概览接口每服务一次 `list_between()` 只读应用库，不触发目标连接；整体给 3 秒
  读库限时（复用网关超时模式），超时返回 `INTERNAL_ERROR` 安全错误，不影响既有接口。
- **陈旧样本可核验**：连接状态取自窗口内最新样本，若采样器停止可能陈旧；`latest_sample.observed_at`
  已携带观测时间，前端概览行展示该时间，使"历史记录"语义可核验。

### 2.6 性能与缓存

概览接口只读应用库样本表，不触发目标连接；静态注册表服务数量有限（当前 4 个），每个服务一次
`list_between()` 窗口查询，成本低。**不引入额外进程内缓存或分页**：数据本身来自定时采样、更新频率低，
且诚实性要求展示最新采样而非被缓存拉旧；如后续服务数量增大再考虑聚合查询与缓存。

### 2.7 前端页面与导航

- `GlobalNav.tsx`：`monitor` 键 `active` 条件改为 `location.pathname.startsWith('/monitor')`，
  `go('monitor')` 路由到 `/monitor`。
- `App.tsx`：注册 `/monitor` 路由 → `MonitoringOverviewPage`；运维模式判断
  `is_operations = is_services || is_models || is_monitor`，使 `/monitor` 使用运维模式壳（第二栏）。
- `ServiceContextNav.tsx`：运维模式下新增「服务监控」入口，点击跳 `/monitor`；`/monitor` 路径下该入口
  置为 `active` 态（实现时按 `location.pathname.startsWith('/monitor')` 判定），展示文案「服务监控 · 定时采样」。
- 新增 `frontend/src/features/monitor/MonitoringOverviewPage.tsx`：
  - 使用 React Query 请求 `get_monitor_overview_query()`；
  - 渲染所有服务的概览表格/卡片：服务名、类型、连接状态、最新延迟（p50/p95，Redis 为内存/慢日志）、
    慢查询/超时计数、异常标记（`anomaly_sample_count>0` → "采样点异常"）、主机指标摘要；
  - 每行可点击进入 `/services/:id`；
  - 页面标注"定时采样 · 每 5 分钟 · 保留最近 24 小时 · 历史记录"；
  - 未配置/不可用/无样本保持诚实空态；请求失败显示失败空态并可重试，不崩溃；
  - 复用既有 `resource-readers` 与 `service-detail.css` / `service-center.css` 样式，不引入新样式体系。
- 新增 `MonitoringOverviewPage.test.tsx`（Vitest + jsdom + MSW），`handlers.ts` 增概览 fixture。

### 2.8 配置

不新增配置项。`sample_interval_seconds` / `retention_hours` 复用既有 `load_monitor_settings()`
（`OPERMIND_MONITOR_SAMPLE_INTERVAL_SECONDS` / `OPERMIND_MONITOR_RETENTION_HOURS`），与 P5 一致。

## 3. 文件改动面

### 后端

- `backend/src/domain/monitoring.py`：新增 `MonitorOverviewData`、`MonitorServiceOverviewData`、
  `MonitorTrendSummaryData` 领域模型（跨层 Pydantic，frozen + extra=forbid）。
- `backend/src/application/monitoring.py`：新增 `MonitorOverviewApplicationService`，
  注入 `session_factory`、`registry`、`sample_interval_seconds`、`retention_hours`、`query_max_hours`；
  方法 `get_overview()`：遍历注册表、按窗口读样本、判定状态/最新样本/趋势摘要。
- `backend/src/api/v1/schemas.py`：新增 `MonitorOverviewResponse`、`MonitorServiceOverviewResource`、
  `MonitorTrendSummaryResource`（`latest_sample` 复用 `MonitorSampleResource`）。
- `backend/src/api/v1/resources.py`：新增 `monitor_overview_resource` mapper。
- `backend/src/api/v1/routes.py`：新增 `GET /api/v1/monitor/overview` 路由（只读，错误走既有
  `ApiV1Error`/`raise_application_error` 语义）。
- `backend/src/api/v1/dependencies.py`：装配 `MonitorOverviewApplicationService`（可经
  `_monitor_history` 同款临时装配或加到 `V1Services`，Design 只定接口与装配位置，不写死实现）。
- `backend/tests/test_monitor_overview_api.py`（**新增**）：覆盖状态判定、最新样本、异常计数、
  空态、脱敏、失败隔离与回归。

### 前端

- `frontend/src/api/v1/client.ts`、`queries.ts`：新增 `get_monitor_overview` 与查询；
  `generated.ts` 仅通过 `npm run generate:api` 更新（禁止手工编辑）。
- `frontend/src/features/monitor/MonitoringOverviewPage.tsx`（**新增**）+ `MonitoringOverviewPage.test.tsx`（**新增**）。
- `frontend/src/features/shell/GlobalNav.tsx`、`ServiceContextNav.tsx`、`frontend/src/app/App.tsx`：导航与路由。
- `frontend/src/test/handlers.ts`：新增概览 MSW fixture。
- 样式复用既有 `service-detail.css` / `service-center.css`，一般无需新增样式文件。

### 无功能改动部分

- 无数据库迁移、无新配置、无新 Connector、无凭据/连接改动。
- `data/mock_db.py`、`data/scenarios.py`、S1–S4 评测路径不改。
- 既有 `GET /services`、`GET /services/{id}/monitor/history` 契约不变。

## 4. 切片与验证（指引，不写死）

建议拆 3 片（切片拆解、验证命令、提交计划归 `dev-plan` 的 plan.md）：

- S1：后端概览领域模型 + 应用服务（状态判定/最新样本/趋势摘要）+ 单元测试。
  验收语义：状态枚举正确、最新样本透出、异常计数与 P5 一致、无样本/未配置/不可用诚实状态、不触发连接。
- S2：概览 API 契约 + 路由 + API 测试。验收语义：`GET /api/v1/monitor/overview` 契约、脱敏、
  服务键边界、meta 关联、既有服务接口回归。
- S3：前端 `/monitor` 概览页 + 导航/路由 + 交互测试。验收语义：全部服务展示、逐状态空态、
  异常标记"采样点异常"、诚实标注无"实时监控"、行点击跳详情、失败重试。

涉及门禁项：**新增公开 API、前端页面（产品主脊监控聚合）**——必须经本 Design → Review → 用户确认后进入 dev-plan。
> 说明：新增 `GET /api/v1/monitor/overview` 端点与 `/monitor` 页面为**已确认 PRD（issue #45）明示授权的
> 监控消费视图落地物**，不是绕过工具网关的新流程/新模式；概览只读应用库样本表，不直连目标服务，
> 与「架构与开发路径.md」硬规则「禁止新端点/新独立页面」的意图不冲突。

## 5. 风险、回滚与门禁

- **风险**：概览与历史接口的状态语义可能被误用（历史接口过滤 not_configured 而概览需要状态样本）→
  概览应用服务独立读取原始样本，测试锁定；采样器未运行 → 概览全为"暂无历史采样"诚实空态，不崩；
  误触发真实连接 → 概览只读样本表，测试断言无 `health_snapshot` 调用。
- **回滚**：移除概览 API 注册与前端 `/monitor` 路由即回滚；无迁移、无持久化改动、无既有契约破坏。
- **门禁**：本 Design `arch-review` PASS + 用户确认 + 状态改为「已确认」后，才放行 dev-plan。

## 6. 待用户确认的设计决策

1. 是否确认概览采用**后端聚合接口** `GET /api/v1/monitor/overview`（一次请求返回全部服务），而非前端多接口聚合？
2. 是否确认概览数据**全部来自 P5 历史样本**（最新采样快照 + 窗口统计），不现读快照、不触发目标连接；
   采样器未运行或无样本时如实显示"暂无历史采样"？
3. 是否确认概览行展示**主机指标摘要**（CPU/内存/磁盘，来自最新样本主机标量），标注"后端所在主机 · 单主机采集"，
   不重复进程/网络明细？
4. 是否确认异常标记为**"采样点异常"**（后端返回窗口内 `anomaly_sample_count`，前端据此标记），
   不出现"正在告警/正在推送"表述？
5. 是否确认前端 `/monitor` 纳入运维模式壳（第二栏复用服务中心上下文导航并新增「服务监控」入口），
   新增 `MonitoringOverviewPage` 页面与导航/路由改动？
6. 是否确认概览接口**不引入额外缓存与分页**（服务数量有限、只读样本表成本低，数据来自定时采样更新频率低）？
7. 是否确认异常采样点判定在 PRD AC6 枚举之外**扩展 Redis `slowlog_count>0`** 触发"采样点异常"
   （与 P5 已交付的前端 Redis 异常判定一致），并**同步回写 PRD** 功能需求 2/AC6？
8. 是否确认概览接口的读库限时取 **3 秒**（复用网关超时模式），且 `not_sampled` 时
   `availability` 取 `unavailable` 的契约取值？
